"""Stage 7's pre-insert half: fit ERPNext's mapped Purchase Invoice to the supplier's actual
invoice, then run V-PI-01…10 on it. Nothing is inserted — Jarvis does that, after a human
confirms."""

import frappe
from frappe.utils import flt, getdate, nowdate

from vendor_invoice_automation.validations.base import ERROR, FAIL, INFO, PASS, SKIP, WARN, row, verdict

STAGE = "purchase_invoice"
TOLERANCE = 1.0

HEADER_KEYS = (
	"supplier", "company", "currency", "conversion_rate", "buying_price_list", "price_list_currency",
	"plc_conversion_rate", "posting_date", "bill_no", "bill_date", "due_date", "credit_to",
	"taxes_and_charges", "cost_center", "project", "set_warehouse", "update_stock", "is_subcontracted",
	"supplier_address", "billing_address", "shipping_address", "supplier_gstin", "company_gstin",
	"place_of_supply", "gst_category", "is_reverse_charge", "apply_tds", "tax_withholding_category",
	"document_intake",
)
ITEM_KEYS = (
	"item_code", "item_name", "description", "qty", "uom", "stock_uom", "conversion_factor", "rate",
	"price_list_rate", "discount_percentage", "warehouse", "expense_account", "cost_center", "project",
	"purchase_order", "po_detail", "purchase_receipt", "pr_detail", "batch_no", "serial_no", "gst_hsn_code",
	"item_tax_template",
)
TAX_KEYS = ("charge_type", "account_head", "description", "rate", "tax_amount", "cost_center",
	"included_in_print_rate", "row_id", "category", "add_deduct_tax")


def fit(intake, mapped):
	"""The mapped doc bills everything still open on the PO/GRN; the supplier may bill less.
	Keep only the invoiced items, at the invoiced qty, and stamp the supplier's references."""
	data = frappe.parse_json(intake.extracted_data or "{}")
	wanted = {}
	for line in intake.items:
		if line.item_code:
			wanted[line.item_code] = wanted.get(line.item_code, 0) + flt(line.qty)

	items = []
	for item in mapped.get("items") or []:
		code = item.get("item_code")
		left = wanted.get(code, 0)
		if left <= 0:
			continue
		last = not any(i.get("item_code") == code for i in mapped["items"][mapped["items"].index(item) + 1:])
		# The last mapped row takes the remainder, so over-billing within allowance is kept, not trimmed.
		item["qty"] = left if last else min(flt(item.get("qty")), left)
		wanted[code] = left - item["qty"]
		items.append(item)
	mapped["items"] = items

	mapped.update({
		"bill_no": intake.reference_no,
		"bill_date": intake.reference_date,
		"document_intake": intake.name,
	})
	meta = frappe.get_meta("Purchase Invoice")
	for field, value in (("supplier_gstin", intake.tax_id), ("company_gstin", data.get("company_gstin")),
		("place_of_supply", data.get("place_of_supply"))):
		if value and meta.has_field(field):
			mapped[field] = value

	doc = frappe.get_doc(mapped)
	if not doc.get("billing_address"):
		from frappe.contacts.doctype.address.address import get_company_address

		doc.billing_address = get_company_address(doc.company).get("company_address")
	doc.run_method("set_missing_values")
	if not doc.get("taxes"):
		_taxes_from_invoice(doc, data)
	doc.calculate_taxes_and_totals()
	return doc


def _taxes_from_invoice(doc, data):
	"""An order raised without a tax template maps to a tax-free PI. Book the GST the supplier
	actually charged — already reconciled by V-EXT-04/05 — on the company's input GST accounts."""
	accounts = _gst_accounts(doc.company)
	for head in ("cgst", "sgst", "igst", "cess"):
		amount, account = flt(data.get(head)), accounts.get(f"{head}_account")
		if amount and account:
			doc.append("taxes", {"charge_type": "Actual", "account_head": account, "tax_amount": amount,
				"description": head.upper(), "category": "Total", "add_deduct_tax": "Add",
				"cost_center": doc.cost_center or frappe.get_cached_value("Company", doc.company, "cost_center")})


def _gst_accounts(company):
	try:
		from india_compliance.gst_india.utils import get_gst_accounts_by_type

		return get_gst_accounts_by_type(company, "Input", throw=False) or {}
	except Exception:
		frappe.clear_messages()
		return {}


def check(intake, doc):
	data = frappe.parse_json(intake.extracted_data or "{}")
	rows = [
		_grand_total(intake, doc),
		_tax_breakup(data, doc),
		_accounts(doc),
		_posting_period(doc),
		row("V-PI-05", STAGE, INFO, SKIP, "Budget is enforced by ERPNext itself at submit."),
		_dimensions(doc),
		_bill_no_unique(doc),
		row("V-PI-08", STAGE, ERROR, verdict(not doc.docstatus), "Stays a Draft — never auto-submitted.",
			0, doc.docstatus),
		_tds(doc),
		# ponytail: no standard MSME/Udyam field on Supplier in ERPNext; add when the site defines one.
		row("V-PI-10", STAGE, INFO, SKIP, "No MSME registration field on Supplier to stamp a due date from."),
	]
	return rows


def values_for_create_doc(doc):
	"""Only what `create_doc` needs; ERPNext recomputes every total on insert."""
	d = doc.as_dict()
	out = {k: d[k] for k in HEADER_KEYS if d.get(k) not in (None, "")}
	out["items"] = [{k: i[k] for k in ITEM_KEYS if i.get(k) not in (None, "")} for i in d.get("items") or []]
	if d.get("taxes"):
		out["taxes"] = [{k: t[k] for k in TAX_KEYS if t.get(k) not in (None, "")} for t in d["taxes"]]
	return out


def _grand_total(intake, doc):
	ok = abs(flt(doc.grand_total) - flt(intake.amount)) <= TOLERANCE
	return row("V-PI-01", STAGE, ERROR, verdict(ok),
		"Purchase Invoice total agrees with the supplier's invoice." if ok
		else "Purchase Invoice total differs from the supplier's invoice — check taxes and qty.",
		f"{flt(intake.amount):.2f}", f"{flt(doc.grand_total):.2f}")


def _tax_breakup(data, doc):
	accounts = _gst_accounts(doc.company)
	if not accounts:
		return row("V-PI-02", STAGE, ERROR, SKIP, "No Input GST accounts in GST Settings for this company.")

	booked = {}
	for tax in doc.get("taxes") or []:
		for head in ("cgst", "sgst", "igst", "cess"):
			if tax.account_head == accounts.get(f"{head}_account"):
				booked[head] = booked.get(head, 0) + flt(tax.tax_amount)
	off = [f"{h}: invoice {flt(data.get(h)):.2f} vs PI {booked.get(h, 0):.2f}"
		for h in ("cgst", "sgst", "igst", "cess") if abs(flt(data.get(h)) - booked.get(h, 0)) > TOLERANCE]
	return row("V-PI-02", STAGE, ERROR, verdict(not off),
		"Tax breakup differs from the supplier's invoice." if off else "CGST/SGST/IGST/Cess agree.",
		"same tax per head", off or None)


def _accounts(doc):
	bad = [i.item_code for i in doc.items if not (i.expense_account and i.cost_center)]
	return row("V-PI-03", STAGE, ERROR, verdict(bool(doc.items) and not bad),
		"No invoiced item is still billable on the order." if not doc.items
		else (f"Missing expense account or cost center: {bad}" if bad else "Every line has an account and cost center."),
		"expense account + cost center", bad or None)


def _posting_period(doc):
	from erpnext.accounts.utils import get_fiscal_year

	date = doc.posting_date or nowdate()
	try:
		get_fiscal_year(date, company=doc.company)
		return row("V-PI-04", STAGE, ERROR, PASS, "Posting date is in an open Fiscal Year.", found=date)
	except Exception:
		frappe.clear_messages()
		return row("V-PI-04", STAGE, ERROR, FAIL, "Posting date is in no open Fiscal Year.",
			"an open Fiscal Year", date)


def _dimensions(doc):
	mandatory = frappe.get_all("Accounting Dimension Detail",
		filters={"company": doc.company, "parenttype": "Accounting Dimension", "mandatory_for_pl": 1},
		fields=["parent"])
	fields = [frappe.db.get_value("Accounting Dimension", m.parent, "fieldname") for m in mandatory]
	missing = [f"{i.item_code}.{f}" for i in doc.items for f in fields if f and not i.get(f)]
	return row("V-PI-06", STAGE, ERROR, verdict(not missing),
		f"Mandatory accounting dimensions missing: {missing}" if missing else "Mandatory dimensions populated.",
		"mandatory dimensions", missing or None)


def _bill_no_unique(doc):
	hit = frappe.db.get_value("Purchase Invoice",
		{"supplier": doc.supplier, "bill_no": doc.bill_no, "docstatus": ["<", 2]}, "name")
	return row("V-PI-07", STAGE, ERROR, verdict(not hit),
		f"Bill no {doc.bill_no} is already booked as {hit}." if hit else "Bill no is still unique for this supplier.",
		"no Purchase Invoice with this bill no", hit)


def _tds(doc):
	category = frappe.db.get_value("Supplier", doc.supplier, "tax_withholding_category")
	if not category:
		return row("V-PI-09", STAGE, WARN, PASS, "Supplier carries no Tax Withholding Category.")
	doc.apply_tds = 1
	return row("V-PI-09", STAGE, WARN, PASS, f"TDS applied under {category}.", category, category)
