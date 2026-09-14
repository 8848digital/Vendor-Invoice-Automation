"""Requirement 7 — Duplicate invoice validation.

Reject when the same **GSTIN + invoice number + invoice date + invoice amount**
has already been seen, and separately compare IRN / QR / file hash.

The history arrives as `context["existing_invoices"]` — every Purchase Invoice already
carrying this bill number for this supplier, fetched on the caller's own site. The hits are
classified here in Python, because the useful answer is not a boolean: "same number,
different amount" is a different problem from "same everything", and collapsing them loses
the signal a reviewer needs.

Cancelled invoices count. The caller must query **without** a `docstatus` filter — a
cancelled document was still seen, and re-uploading it is exactly the behaviour this block
exists to catch. That requirement now lives in CONTEXT.md, since the query does.
"""

from frappe.utils import flt, getdate

from .base import ERROR, PASS, SKIP, UNSET, WARN, row, unchecked, verdict

STAGE = "duplicate"

# ponytail: Purchase Invoice is the only history we have, so dedup by QR payload or
# file hash (V-DUP-05/06) is not built — the held decision is recorded in
# VALIDATION_API_MAP.md rather than as a Skipped row in every single response.


def run(p, c):
	hits = c.get("existing_invoices", UNSET)
	if hits is UNSET:
		rows = [
			unchecked("V-DUP-01", STAGE, ERROR, "existing_invoices"),
			unchecked("V-DUP-07", STAGE, WARN, "existing_invoices"),
		]
	else:
		hits = hits or []
		rows = [_exact(p, hits), _same_number_different_amount(p, hits)]

	# Only worth a row when there is an IRN to compare. Most invoices carry none.
	if p.get("irn"):
		rows.append(_irn(p, c))
	return rows


def _matches(p, hit):
	"""Which of the four key fields agree. `supplier_gstin` blank on the booked
	invoice is not a disagreement — it is an absent value, so it does not clear a
	duplicate that matches on everything else."""
	hit_gstin = hit.get("supplier_gstin")
	hit_date = hit.get("bill_date")
	return {
		"gstin": not hit_gstin or hit_gstin == p.get("supplier_gstin"),
		"invoice_no": True,  # the caller's query already keyed on it
		"invoice_date": bool(p.get("invoice_date") and hit_date)
			and getdate(hit_date) == getdate(p["invoice_date"]),
		"amount": abs(flt(hit.get("grand_total")) - flt(p.get("grand_total"))) <= 0.01,
	}


def _exact(p, hits):
	"""V-DUP-01 — all four fields agree. This is requirement 7's reject condition."""
	if not (p.get("invoice_no") and (p.get("supplier") or p.get("supplier_gstin"))):
		return row("V-DUP-01", STAGE, ERROR, SKIP,
			"No invoice number and party to dedupe on.", "invoice_no + supplier", None)

	dupes = [h.get("name") for h in hits if all(_matches(p, h).values())]
	return row("V-DUP-01", STAGE, ERROR, verdict(not dupes),
		f"Already booked as {', '.join(dupes)} — same GSTIN, number, date and amount." if dupes
		else "No invoice with the same GSTIN, number, date and amount.",
		"no existing Purchase Invoice", dupes or None)


def _same_number_different_amount(p, hits):
	"""V-DUP-07 — the number was seen but something else moved. Not a duplicate to
	reject; a document to look at, so Warning."""
	near = []
	for h in hits:
		differ = [k for k, ok in _matches(p, h).items() if not ok]
		if differ:
			near.append(f"{h.get('name')} ({', '.join(differ)} differ)")
	if not hits:
		return row("V-DUP-07", STAGE, WARN, PASS, "Invoice number not seen before.")
	return row("V-DUP-07", STAGE, WARN, verdict(not near),
		"Invoice number was seen before with different details." if near
		else "Every existing invoice with this number agrees on all four fields.",
		"no partial match", near or None)


def _irn(p, c):
	"""V-DUP-02 — the IRN against GSTR-2A/2B.

	`GST Inward Supply.irn_number` is the only place an *inbound* IRN is stored:
	india_compliance puts the `irn` custom field on Sales Invoice alone
	(constants/custom_fields.py:1534), so a booked Purchase Invoice carries none.

	A 2B row for our own bill number is the supplier's filing of this very invoice, not a
	duplicate — so the caller must exclude it, and `context["irn_hits"]` holds only rows
	belonging to a *different* bill number.
	"""
	others = c.get("irn_hits", UNSET)
	if others is UNSET:
		return unchecked("V-DUP-02", STAGE, ERROR, "irn_hits")
	others = others or []
	bill_nos = [o.get("bill_no") for o in others]
	return row("V-DUP-02", STAGE, ERROR, verdict(not others),
		f"IRN already reported against a different invoice: {bill_nos}" if others
		else "IRN is not attached to any other invoice.",
		"IRN unique to this invoice", bill_nos or None)
