"""Requirement 7 — Duplicate invoice validation.

Reject when the same **GSTIN + invoice number + invoice date + invoice amount**
has already been seen, and separately compare IRN / QR / file hash.

One query does the work. It fetches every Purchase Invoice carrying this bill
number for this supplier and classifies the hits in Python, because the useful
answer is not a boolean: "same number, different amount" is a different problem
from "same everything", and collapsing them loses the signal a reviewer needs.

Cancelled invoices count. There is deliberately no `docstatus` filter — a
cancelled document was still seen, and re-uploading it is exactly the behaviour
this block exists to catch.
"""

import frappe
from frappe.utils import flt, getdate

from .base import ERROR, PASS, SKIP, WARN, row, verdict

STAGE = "duplicate"

# ponytail: Purchase Invoice is the only history we have, so dedup by QR payload or
# file hash (V-DUP-05/06) is not built — the held decision is recorded in
# VALIDATION_API_MAP.md rather than as a Skipped row in every single response. Add a
# `Vendor Invoice Log` with unique indexes and they become real checks.


def run(p):
	hits = _existing(p)
	rows = [_exact(p, hits), _same_number_different_amount(p, hits)]
	# Only worth a row when there is an IRN to compare. Most invoices carry none.
	if p.get("irn"):
		rows.append(_irn(p))
	return rows


def _existing(p):
	"""Every Purchase Invoice already carrying this bill number from this supplier.

	Matched on `supplier` OR `supplier_gstin`, not both: india_compliance's
	`supplier_gstin` is `fetch_from: supplier_address.gstin`, so it is empty on any
	invoice booked without a supplier address, and an AND would miss those.
	"""
	bill_no, supplier, gstin = p.get("invoice_no"), p.get("supplier"), p.get("supplier_gstin")
	if not bill_no or not (supplier or gstin):
		return []

	party = ["supplier", "=", supplier] if supplier else ["supplier_gstin", "=", gstin]
	return frappe.get_all(
		"Purchase Invoice",
		filters=[["bill_no", "=", bill_no], party],
		fields=["name", "docstatus", "supplier_gstin", "bill_date", "grand_total"],
	)


def _matches(p, hit):
	"""Which of the four key fields agree. `supplier_gstin` blank on the booked
	invoice is not a disagreement — it is an absent value, so it does not clear a
	duplicate that matches on everything else."""
	return {
		"gstin": not hit.supplier_gstin or hit.supplier_gstin == p.get("supplier_gstin"),
		"invoice_no": True,  # the query already keyed on it
		"invoice_date": bool(p.get("invoice_date") and hit.bill_date)
			and getdate(hit.bill_date) == getdate(p["invoice_date"]),
		"amount": abs(flt(hit.grand_total) - flt(p.get("grand_total"))) <= 0.01,
	}


def _exact(p, hits):
	"""V-DUP-01 — all four fields agree. This is requirement 7's reject condition."""
	if not (p.get("invoice_no") and (p.get("supplier") or p.get("supplier_gstin"))):
		return row("V-DUP-01", STAGE, ERROR, SKIP,
			"No invoice number and party to dedupe on.", "invoice_no + supplier", None)

	dupes = [h.name for h in hits if all(_matches(p, h).values())]
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
			near.append(f"{h.name} ({', '.join(differ)} differ)")
	if not hits:
		return row("V-DUP-07", STAGE, WARN, PASS, "Invoice number not seen before.")
	return row("V-DUP-07", STAGE, WARN, verdict(not near),
		"Invoice number was seen before with different details." if near
		else "Every existing invoice with this number agrees on all four fields.",
		"no partial match", near or None)


def _irn(p):
	"""V-DUP-02 — the IRN against GSTR-2A/2B.

	`GST Inward Supply.irn_number` is the only place an *inbound* IRN is stored:
	india_compliance puts the `irn` custom field on Sales Invoice alone
	(constants/custom_fields.py:1534), so a booked Purchase Invoice carries none.

	A 2B row for our own bill number is the supplier's filing of this very
	invoice, not a duplicate — so a hit only counts when it belongs to a
	*different* bill number.
	"""
	irn = p.get("irn")
	others = frappe.get_all("GST Inward Supply",
		filters={"irn_number": irn, "bill_no": ("!=", p.get("invoice_no") or "")},
		fields=["name", "bill_no"], limit=5)
	return row("V-DUP-02", STAGE, ERROR, verdict(not others),
		f"IRN already reported against a different invoice: {[o.bill_no for o in others]}" if others
		else "IRN is not attached to any other invoice.",
		"IRN unique to this invoice", [o.bill_no for o in others] or None)
