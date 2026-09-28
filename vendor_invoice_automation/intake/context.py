"""Server-side `context`: CONTEXT.md's fetch recipes, run against this site's own database.

The validation blocks stay context-driven, so the same `validations.validate()` serves both
the stateless `validate_invoice` API (caller sends context) and `process_invoice` (we build it).
"""

import frappe
from frappe.utils import flt

PO_MAPPERS = (
	"erpnext.buying.doctype.purchase_order.mapper.make_purchase_invoice",  # v16+
	"erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_invoice",  # v15
)
PR_MAPPERS = (
	"erpnext.stock.doctype.purchase_receipt.mapper.make_purchase_invoice",
	"erpnext.stock.doctype.purchase_receipt.purchase_receipt.make_purchase_invoice",
)


def mapper_path(paths):
	"""The mapper this ERPNext version ships — the path moved to `mapper.py` in v16."""
	for path in paths:
		try:
			frappe.get_attr(path)
			return path
		except (ImportError, AttributeError):
			continue
	raise ImportError(f"No make_purchase_invoice mapper found among {paths}")


def run_mapper(paths, source_name):
	"""(doc, error). A mapper refusal (draft, closed, fully billed) is an answer, not a crash."""
	try:
		return frappe.get_attr(mapper_path(paths))(source_name).as_dict(), None
	except Exception as e:
		frappe.clear_messages()
		return None, frappe.utils.strip_html(str(e)) or type(e).__name__


def _existing_fields(doctype, fields):
	"""india_compliance field names drift between versions; ask the meta instead of guessing."""
	meta = frappe.get_meta(doctype)
	return [f for f in fields if f == "name" or meta.has_field(f)]


def build(p):
	c = {}
	supplier, gstin = p.get("supplier"), p.get("supplier_gstin")
	invoice_no, company = p.get("invoice_no"), p.get("company")

	c["supplier"] = (
		frappe.db.get_value("Supplier", supplier,
			["name", "disabled", "on_hold", "hold_type", "release_date", "gstin", "pan", "gst_category"],
			as_dict=True)
		if supplier else None
	)

	if invoice_no:
		# No docstatus filter: a cancelled invoice was still seen (duplicate.py).
		or_filters = {"supplier": supplier} if supplier else {}
		if gstin:
			or_filters["supplier_gstin"] = gstin
		c["existing_invoices"] = frappe.get_all("Purchase Invoice",
			filters={"bill_no": invoice_no}, or_filters=or_filters or None,
			fields=["name", "docstatus", "supplier_gstin", "bill_date", "grand_total"])
	else:
		c["existing_invoices"] = []

	if p.get("irn"):
		c["irn_hits"] = frappe.get_all("GST Inward Supply",
			filters={"irn_number": p["irn"], "bill_no": ["!=", invoice_no or ""]},
			fields=["name", "bill_no"], limit=5)

	c["inward_supply"] = None
	if gstin and invoice_no:
		rows = frappe.get_all("GST Inward Supply",
			filters={"supplier_gstin": gstin, "bill_no": invoice_no},
			fields=_existing_fields("GST Inward Supply", [
				"name", "bill_no", "bill_date", "supplier_gstin", "company_gstin",
				"taxable_value", "cgst", "sgst", "igst", "cess", "irn_number",
				"is_reverse_charge", "classification", "doc_type", "place_of_supply",
				"itc_availability", "reason_itc_unavailability", "gstr_1_filled",
				"gstr_1_filing_date", "is_supplier_return_filed", "sup_return_period"]),
			limit=1)
		c["inward_supply"] = rows[0] if rows else None

	codes = sorted({str(i.get("hsn_sac")) for i in p.get("items") or [] if i.get("hsn_sac")})
	c["hsn_codes"] = frappe.get_all("GST HSN Code", filters={"name": ["in", codes]}, pluck="name") if codes else []

	if company:
		from india_compliance.gst_india.utils import get_gstin_list

		c["company_gstins"] = get_gstin_list(company, "Company")

	if p.get("invoice_date"):
		from erpnext.accounts.utils import get_fiscal_year

		try:
			c["fiscal_year"] = get_fiscal_year(p["invoice_date"], company=company, as_dict=True)
		except Exception:
			frappe.clear_messages()
			c["fiscal_year"] = None

	item_codes = sorted({i["item_code"] for i in p.get("items") or [] if i.get("item_code")})
	c["items"] = {
		r.name: r for r in frappe.get_all("Item", filters={"name": ["in", item_codes]},
			fields=["name", "is_stock_item", "over_delivery_receipt_allowance", "over_billing_allowance"])
	} if item_codes else {}

	c["settings"] = _settings()

	po = p.get("po_number")
	if po:
		doc, error = run_mapper(PO_MAPPERS, po) if frappe.db.exists("Purchase Order", po) \
			else (None, f"Purchase Order {po} does not exist")
		c["po"] = {"error": error} if error else {"expected_invoice": doc}

		receipts = sorted(set(frappe.get_all("Purchase Receipt Item",
			filters={"purchase_order": po, "docstatus": 1}, pluck="parent")))
		expected, errors = [], []
		for pr in receipts:
			doc, error = run_mapper(PR_MAPPERS, pr)
			if error:
				errors.append(f"{pr}: {error}")
			else:
				expected.append(doc)
		c["grn"] = {"receipts": receipts, "expected_invoices": expected, "errors": errors}

	return c


def _settings():
	user_roles = set(frappe.get_roles())
	rate_role = frappe.db.get_single_value("Buying Settings", "role_to_override_stop_action")
	bill_role = frappe.db.get_single_value("Accounts Settings", "role_allowed_to_over_bill")
	return {
		"over_delivery_receipt_allowance": flt(
			frappe.db.get_single_value("Stock Settings", "over_delivery_receipt_allowance")),
		"over_billing_allowance": flt(frappe.db.get_single_value("Accounts Settings", "over_billing_allowance")),
		"maintain_same_rate": frappe.db.get_single_value("Buying Settings", "maintain_same_rate"),
		"maintain_same_rate_action": frappe.db.get_single_value("Buying Settings", "maintain_same_rate_action"),
		"rate_override_held": bool(rate_role and rate_role in user_roles),
		"over_bill_override_held": bool(bill_role and bill_role in user_roles),
	}
