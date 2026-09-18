"""Server-side writes, the only ones this app makes: Document Intake status follows the
Purchase Invoice it produced, the goods receipt it was waiting for, and the payments against it.

Statuses are set with a full save, not db.set_value, so bell Notifications fire and Track
Changes records when each status was entered — the Workflow Ageing report reads that history.
"""

import frappe
from frappe.utils import flt

INTAKE = "Document Intake"
# Purchase Invoice workflow_state → intake status. Review states are all "Workflow".
WORKFLOW_STATUS = {"Approved": "Approved", "Rejected": "Rejected"}


def _set(name, **values):
	doc = frappe.get_doc(INTAKE, name)
	if all(doc.get(k) == v for k, v in values.items()):
		return
	doc.update(values)
	doc.flags.ignore_permissions = True
	doc.save()


# --------------------------------------------------------------------------- Purchase Invoice


def purchase_invoice_after_insert(doc, method=None):
	if doc.get("document_intake"):
		_set(doc.document_intake, created_doctype="Purchase Invoice", created_doc=doc.name, status="Workflow")


def purchase_invoice_on_update(doc, method=None):
	if not doc.get("document_intake") or doc.docstatus != 0 or doc.flags.in_insert:
		return
	_set(doc.document_intake, status=WORKFLOW_STATUS.get(doc.get("workflow_state"), "Workflow"))
	if doc.get("workflow_state") == "Buyer Review" and doc.has_value_changed("workflow_state"):
		_assign_buyer(doc)


def purchase_invoice_on_submit(doc, method=None):
	if doc.get("document_intake"):
		_set(doc.document_intake, status=_payment_status(doc))


def purchase_invoice_on_cancel(doc, method=None):
	if doc.get("document_intake"):
		_set(doc.document_intake, status="Rejected", exception_type="Purchase Invoice Cancelled")


def _payment_status(pi):
	outstanding = flt(frappe.db.get_value("Purchase Invoice", pi.name, "outstanding_amount"))
	if outstanding <= 0:
		return "Paid"
	return "Payment Pending" if outstanding < flt(pi.rounded_total or pi.grand_total) else "Posted"


def _assign_buyer(pi):
	"""Buyer Review goes to whoever raised the PO."""
	from frappe.desk.form.assign_to import add

	buyer = frappe.db.get_value(INTAKE, pi.document_intake, "buyer")
	if buyer:
		add({"doctype": "Purchase Invoice", "name": pi.name, "assign_to": [buyer],
			"description": f"Buyer Review for {pi.bill_no}"}, ignore_permissions=True)


# --------------------------------------------------------------------------- Payment Entry


def payment_entry_changed(doc, method=None):
	for ref in doc.get("references") or []:
		if ref.reference_doctype != "Purchase Invoice":
			continue
		pi = frappe.get_doc("Purchase Invoice", ref.reference_name)
		if pi.get("document_intake") and pi.docstatus == 1:
			_set(pi.document_intake, status=_payment_status(pi))


# --------------------------------------------------------------------------- Purchase Receipt


def purchase_receipt_on_submit(doc, method=None):
	"""A held invoice was waiting for these goods: re-run its checks and tell the uploader."""
	orders = sorted({i.purchase_order for i in doc.items if i.purchase_order})
	if orders and frappe.db.exists(INTAKE, {"status": "GRN Failed", "against": ["in", orders]}):
		frappe.enqueue(recheck_waiting_invoices, orders=orders, enqueue_after_commit=True)


def recheck_waiting_invoices(orders):
	from vendor_invoice_automation.api.v1.intake import process_invoice

	for name in frappe.get_all(INTAKE, filters={"status": "GRN Failed", "against": ["in", orders]}, pluck="name"):
		intake = frappe.get_doc(INTAKE, name)
		owner = intake.uploaded_by or intake.owner
		# Re-check as the uploader, so permissions and override roles are theirs, not the worker's.
		frappe.set_user(owner)
		try:
			invoice = {**frappe.parse_json(intake.extracted_data), "extraction_method": intake.extraction_method}
			result = process_invoice(invoice=invoice, intake=name)["data"]
			intake.intake_ref = result["save"]["values"]["intake_ref"]
			intake.flags.ignore_permissions = True
			intake.save()
		finally:
			frappe.set_user("Administrator")
		if intake.status == "GRN Matched":
			_notify(owner, intake, f"Goods received: {intake.reference_no} now matches its GRN. "
				"Ask Jarvis to create the Purchase Invoice.")


def _notify(user, intake, subject):
	frappe.get_doc({
		"doctype": "Notification Log",
		"for_user": user,
		"type": "Alert",
		"document_type": INTAKE,
		"document_name": intake.name,
		"subject": subject,
	}).insert(ignore_permissions=True)
