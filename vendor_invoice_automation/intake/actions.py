"""Intake Action: what the system proposes to do with a document, waiting for a person.

A matched intake proposes "Create Purchase Invoice" by itself. A person approves or rejects
it — in the desk or through Jarvis — whenever they get to it, so nothing stalls when nobody
is in chat. On approval the **server** builds the Draft Purchase Invoice from ERPNext's own
mapper and inserts it as the approver; the model never hands over document values.
"""

import frappe
from frappe.utils import fmt_money, now_datetime

from vendor_invoice_automation.intake import context as ctx
from vendor_invoice_automation.intake import purchase_invoice as pi
from vendor_invoice_automation.intake import rules
from vendor_invoice_automation.validations.base import ERROR, FAIL

ACTION = "Intake Action"
CREATE_PI = "Create Purchase Invoice"
MATCHED = ("PO Matched", "GRN Matched")
APPROVER_ROLES = {
	"Purchase Invoice": {"Accounts User", "Accounts Manager", "Purchase Manager"},
}


# --------------------------------------------------------------------------- propose / cancel


def sync(intake):
	"""Called on every Document Intake save: keep exactly one pending proposal while the
	intake is eligible, and withdraw it when a correction makes it ineligible."""
	pending = frappe.get_all(ACTION, filters={"intake": intake.name, "status": "Pending"}, pluck="name")
	eligible = (intake.document_type == "Purchase Invoice" and intake.status in MATCHED
		and not intake.created_doc)

	if eligible and not pending and not frappe.db.exists(ACTION, {"intake": intake.name, "status": "Approved"}):
		frappe.get_doc({
			"doctype": ACTION,
			"intake": intake.name,
			"action": CREATE_PI,
			"party": intake.party,
			"amount": intake.amount,
			"proposed_by": frappe.session.user,
			"summary": _summary(intake),
			"reason": _reason(intake),
		}).insert(ignore_permissions=True)
	elif not eligible:
		for name in pending:
			if name == frappe.flags.executing_intake_action:
				continue  # its own PI insert made the intake ineligible; _execute records the outcome
			frappe.db.set_value(ACTION, name, {"status": "Cancelled",
				"decision_note": f"Withdrawn: the intake moved to {intake.status}."})


def _summary(i):
	against = f" against {i.against}" if i.against else ""
	return (f"{i.party or i.tax_id} · {i.reference_no} · {i.reference_date} · "
		f"{fmt_money(i.amount, currency=i.currency or 'INR')} · {i.matching_mode or ''}{against}")


def _reason(i):
	if i.verdict == "green":
		return f"All checks passed ({i.status}); confidence {i.confidence}%."
	why = i.exception_type or "differences within tolerance"
	fields = f" Uncertain fields: {i.uncertain_fields}." if i.uncertain_fields else ""
	return f"Within tolerance but needs Buyer Review: {why}.{fields}"


# --------------------------------------------------------------------------- decide


def decide(name, decision, note=None):
	action = frappe.get_doc(ACTION, name)
	action.check_permission("read")
	if action.status != "Pending":
		frappe.throw(f"{name} is already {action.status}.")
	_require_approver(action)

	action.decided_by, action.decided_on, action.decision_note = frappe.session.user, now_datetime(), note
	if decision == "Reject":
		action.status = "Rejected"
		action.save(ignore_permissions=True)
		from vendor_invoice_automation.intake.events import _set

		_set(action.intake, status="Rejected", exception_type="Rejected by approver")
		return action

	if decision != "Approve":
		frappe.throw("decision must be Approve or Reject.")
	_execute(action)
	action.save(ignore_permissions=True)
	return action


def _require_approver(action):
	roles = set(frappe.get_roles())
	allowed = APPROVER_ROLES.get(action.document_type, set())
	if "System Manager" not in roles and not roles & allowed:
		frappe.throw(f"Approving needs one of these roles: {', '.join(sorted(allowed))}.", frappe.PermissionError)


def _execute(action):
	"""Build → check → insert, as the approver. Any failure leaves the intake untouched."""
	intake = frappe.get_doc("Document Intake", action.intake)
	if intake.created_doc:
		frappe.throw(f"{intake.name} already produced {intake.created_doc}.")

	frappe.db.savepoint("intake_action")
	frappe.flags.executing_intake_action = action.name
	try:
		method, source = mapper_call(intake)
		built = pi.fit(intake, frappe.get_attr(method)(source).as_dict())
		rows = rules.apply("Purchase Invoice", pi.check(intake, built))
		action.set("checks", [{k: r.get(k) for k in ("check_id", "stage", "severity", "result", "expected",
			"found", "message")} for r in rows])
		blocking = [r for r in rows if r["result"] == FAIL and r["severity"] == ERROR]
		if blocking:
			action.status = "Failed"
			action.error = "; ".join(f"{r['check_id']}: {r['message']}" for r in blocking)
			return
		doc = frappe.get_doc({"doctype": "Purchase Invoice", **pi.values_for_create_doc(built)}).insert()
		action.status, action.result_doctype, action.result_doc = "Approved", "Purchase Invoice", doc.name
	except Exception as e:
		frappe.db.rollback(save_point="intake_action")
		frappe.clear_messages()
		action.status = "Failed"
		action.error = frappe.utils.strip_html(str(e)) or type(e).__name__
	finally:
		frappe.flags.executing_intake_action = None


def mapper_call(intake):
	"""(mapper, source): GRN-backed when goods were received, else PO-backed."""
	if intake.matching_mode == "3-Way":
		receipts = list(dict.fromkeys(frappe.get_all("Purchase Receipt Item",
			filters={"purchase_order": intake.against, "docstatus": 1}, pluck="parent", order_by="creation")))
		# ponytail: first receipt only; an invoice spanning several receipts needs one PI per receipt.
		return ctx.mapper_path(ctx.PR_MAPPERS), receipts[0]
	return ctx.mapper_path(ctx.PO_MAPPERS), intake.against
