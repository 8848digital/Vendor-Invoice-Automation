"""Document intake endpoints for Jarvis.

    process_invoice   checks + confidence + status, and a ref Jarvis saves with create_doc. Writes nothing.
    decide_action     approve or reject a pending Intake Action; approving makes the server
                      create the Draft Purchase Invoice as the approver

Unlike `invoice.validate_invoice`, these need a logged-in user: the context is read from this
site's own database under that user's permissions.
"""

import json
import secrets

import frappe
from frappe.utils import flt

from vendor_invoice_automation.intake import context as ctx
from vendor_invoice_automation.intake import actions, files, outcome, resolve, rules
from vendor_invoice_automation.validations import decision
from vendor_invoice_automation.validations import validate as run_checks
from vendor_invoice_automation.validations.base import ERROR, FAIL, row

from .response_formatter import api_response, handle_bad_request

REF_PREFIX = "via:intake:"
REF_TTL_SECONDS = 3600
PLACEHOLDER = "Vendor Invoice Pending Upload"


@frappe.whitelist(methods=["POST"])
def process_invoice(invoice: dict | str | None = None, file_url: str | None = None,
	intake: str | None = None, file_name: str | None = None) -> dict:
	"""Validate one purchase invoice end to end against this site's data. Writes nothing.

	`invoice` is the model's transcription. `file_name` (or `file_url`) is the uploaded File —
	its hash, signed QR and e-invoice JSON are read here and override the transcription.
	`intake` is the Document Intake being re-processed after a correction, so it is not
	reported as its own duplicate.

	`data.save` says exactly which Jarvis write saves the result. When
	`data.proposes_purchase_invoice` is true, saving it queues an Intake Action for approval.
	"""
	invoice = frappe.parse_json(invoice) if invoice else {}
	if not isinstance(invoice, dict):
		return handle_bad_request("`invoice` must be an object.")
	if not (invoice or file_url or file_name):
		return handle_bad_request("Send `invoice`, `file_name`, or both.")

	method = invoice.pop("extraction_method", None) or "LLM"
	file_facts = files.read(file_url, file_name) if (file_url or file_name) else {}
	file_url = file_facts.get("file_url")
	if file_facts.get("einvoice"):
		invoice.update({k: v for k, v in file_facts["einvoice"].items() if v not in (None, "", [])})
		method = "E-Invoice JSON"
	if file_facts.get("qr_payload"):
		invoice["qr_payload"] = file_facts["qr_payload"]
		method = "QR" if method == "LLM" else method

	resolved = resolve.run(invoice)
	context = ctx.build(invoice)
	result = run_checks(invoice, None, context)

	file_hash, qr_hash = file_facts.get("file_hash"), files.sha256(invoice.get("qr_payload"))
	existing = {f: _other_intake({f: v}, intake) for f, v in (("file_hash", file_hash), ("qr_hash", qr_hash)) if v}
	extra = outcome.duplicate_upload_rows(file_hash, qr_hash, existing)
	placeholder, already = _same_invoice(invoice, intake)
	if already:
		extra.append(row("V-DUP-08", "duplicate", ERROR, FAIL,
			f"This invoice was already uploaded as {already}.", "a new invoice", already))
	checks = rules.apply("Purchase Invoice", result["checks"] + extra)
	result = {**decision.gate(checks, result["matching_mode"], partial=result["partial"]), "checks": checks}

	score, band, uncertain = outcome.confidence(invoice, result["checks"], method)
	state, exception = outcome.status(result, band)
	create = outcome.may_create_purchase_invoice(result, band, state)

	values = _intake_values(invoice, result, state, exception, score, uncertain, method,
		file_url, file_hash, qr_hash, (context.get("inward_supply") or {}).get("name"))
	ref = secrets.token_urlsafe(24)
	frappe.cache().set_value(REF_PREFIX + ref, values, expires_in_sec=REF_TTL_SECONDS)

	target = intake or placeholder
	save = ({"tool": "update_doc", "doctype": "Document Intake", "name": target, "values": {"intake_ref": ref}}
		if target else
		{"tool": "create_doc", "doctype": "Document Intake",
		 "values": {"document_type": "Purchase Invoice", "intake_ref": ref}})

	data = {
		**{k: result[k] for k in ("ok", "verdict", "review_required", "matching_mode", "failed", "skipped", "unrun")},
		"status": state,
		"exception_type": exception,
		"confidence": score,
		"confidence_band": band,
		"uncertain_fields": uncertain,
		"extraction_method": method,
		"resolved": resolved,
		"summary": {k: invoice.get(k) for k in ("supplier", "supplier_gstin", "invoice_no", "invoice_date",
			"po_number", "grand_total")},
		"save": save,
		"proposes_purchase_invoice": create,
		"checks": result["checks"],
	}
	return api_response(success=result["ok"], data=data, message=exception or f"{state} ({result['verdict']}).")


@frappe.whitelist(methods=["POST"])
def decide_action(action: str, decision: str, note: str | None = None) -> dict:
	"""Approve or Reject a pending Intake Action. Approving runs it as the calling user —
	for "Create Purchase Invoice", the server maps, checks (V-PI-01…10) and inserts the Draft."""
	doc = actions.decide(action, decision, note)
	return api_response(success=doc.status in ("Approved", "Rejected"), data={
		"action": doc.name, "status": doc.status, "result_doc": doc.result_doc, "error": doc.error,
		"checks": [{k: c.get(k) for k in ("check_id", "result", "severity", "message")} for c in doc.checks],
	}, message=doc.error or f"{doc.action}: {doc.status}{' → ' + doc.result_doc if doc.result_doc else ''}.")


def load_ref(ref):
	return frappe.cache().get_value(REF_PREFIX + ref)


def _other_intake(filters, exclude):
	return frappe.db.get_value("Document Intake", {**filters, "name": ["!=", exclude or ""]}, "name")


def _same_invoice(p, exclude):
	"""(placeholder to fill, an earlier real upload of this invoice)."""
	if not (p.get("supplier_gstin") and p.get("invoice_no")):
		return None, None
	hits = frappe.get_all("Document Intake",
		filters={"tax_id": p["supplier_gstin"], "reference_no": p["invoice_no"], "name": ["!=", exclude or ""],
			"status": ["not in", ["Rejected", "OCR Failed"]]},
		fields=["name", "status"], order_by="creation")
	placeholder = next((h.name for h in hits if h.status == PLACEHOLDER), None)
	already = next((h.name for h in hits if h.status != PLACEHOLDER), None)
	return placeholder, already


def _link(doctype, name):
	return name if name and frappe.db.exists(doctype, name) else None


def _intake_values(p, result, state, exception, score, uncertain, method, file_url, file_hash, qr_hash, inward):
	"""The Document Intake exactly as validated. Links are only set when the target exists, so
	the insert never fails on a misread name — the printed value stays in extracted_data."""
	po = _link("Purchase Order", p.get("po_number"))
	po_info = frappe.db.get_value("Purchase Order", po, ["owner", "set_warehouse"], as_dict=True) if po else None
	supplier = _link("Supplier", p.get("supplier"))
	itc = next((r for r in result["checks"] if r["check_id"] == "V-ITC-01"), None)

	return {
		"document_type": "Purchase Invoice",
		"profile": "intake-purchase-invoice",
		"status": state,
		"exception_type": exception,
		"verdict": result["verdict"],
		"review_required": int(bool(result["review_required"] or uncertain)),
		"company": _link("Company", p.get("company")),
		"buyer": po_info.owner if po_info else None,
		"plant": po_info.set_warehouse if po_info else None,
		"party_type": "Supplier" if supplier else None,
		"party": supplier,
		"tax_id": p.get("supplier_gstin"),
		"reference_no": p.get("invoice_no"),
		"reference_date": p.get("invoice_date"),
		"against_type": "Purchase Order" if po else None,
		"against": po,
		"matching_mode": result["matching_mode"],
		"currency": _link("Currency", p.get("currency")),
		"taxable_value": flt(p.get("taxable_value")),
		"tax_amount": sum(flt(p.get(k)) for k in ("cgst", "sgst", "igst", "cess")),
		"amount": flt(p.get("grand_total")),
		"itc_status": itc and itc.get("found"),
		"extraction_method": method,
		"confidence": score,
		"uncertain_fields": ", ".join(uncertain) or None,
		"irn": p.get("irn"),
		"file": file_url,
		"file_hash": file_hash,
		"qr_hash": qr_hash,
		"inward_supply": inward,
		"extracted_data": json.dumps(p, default=str),
		"items": [{
			"item_code": _link("Item", i.get("item_code")),
			"description": i.get("description"),
			"hsn_sac": i.get("hsn_sac"),
			"qty": flt(i.get("qty")),
			"uom": _link("UOM", i.get("uom")),
			"rate": flt(i.get("rate")),
			"amount": flt(i.get("amount")),
			"gst_rate": flt(i.get("gst_rate")),
			"tax_amount": flt(i.get("tax_amount")),
			"warehouse": _link("Warehouse", i.get("warehouse")),
			"batch_no": i.get("batch_no"),
			"serial_no": i.get("serial_no"),
		} for i in p.get("items") or []],
		"checks": [{k: r.get(k) for k in ("check_id", "stage", "severity", "result", "expected", "found", "message")}
			for r in result["checks"]],
	}
