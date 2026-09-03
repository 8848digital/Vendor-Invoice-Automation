"""The one GSTR-2A/2B lookup, shared by `gst.py` and `itc.py`.

`GST Inward Supply` is the supplier's own filing as GSTN reports it back to us — the
authoritative answer to "did this invoice really happen", "has the supplier filed",
"is the credit available". india_compliance downloads and keeps it current; nothing
here calls an API, so a validation run stays fast and deterministic and an invoice is
never rejected because GSTN was unreachable.
"""

import frappe

# Everything either caller needs, fetched once.
FIELDS = (
	"name", "bill_no", "bill_date", "supplier_gstin", "company_gstin",
	"taxable_value", "cgst", "sgst", "igst", "cess",
	"irn_number", "is_reverse_charge", "classification", "doc_type", "place_of_supply",
	"itc_availability", "reason_itc_unavailability",
	"gstr_1_filled", "gstr_1_filing_date", "is_supplier_return_filed", "sup_return_period",
)


def inward_supply(p):
	"""The 2A/2B row for this invoice, or None.

	Keyed on supplier GSTIN + bill number, which is how GSTN identifies a B2B invoice.
	Memoised per request: `gst` and `itc` both need it, and it is the same row.
	"""
	gstin, bill_no = p.get("supplier_gstin"), p.get("invoice_no")
	if not (gstin and bill_no):
		return None

	cache = frappe.local.via_2b_cache = getattr(frappe.local, "via_2b_cache", {})
	key = (gstin, bill_no)
	if key not in cache:
		rows = frappe.get_all("GST Inward Supply",
			filters={"supplier_gstin": gstin, "bill_no": bill_no},
			fields=list(FIELDS), limit=1)
		cache[key] = rows[0] if rows else None
	return cache[key]
