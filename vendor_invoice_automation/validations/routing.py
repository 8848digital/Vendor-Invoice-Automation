"""Stage 4 — Routing. SPEC §5.

Decides `matching_mode`. The non-PO branch of SPEC's routing is gone: non-PO invoices
are created independently of this pipeline, so there is nothing here to gate them on.
"""

import frappe

THREE_WAY, TWO_WAY, NON_PO = "3-Way", "2-Way", "Non-PO"
PO_MODES = (THREE_WAY, TWO_WAY)


def run(p):
	"""Returns the matching mode. No audit rows — routing is a decision, not a check."""
	if not p.get("po_number"):
		return NON_PO

	# A stock line means goods physically arrive, so a GRN must corroborate the invoice.
	has_stock = any(
		line.get("item_code") and frappe.db.get_value("Item", line["item_code"], "is_stock_item")
		for line in (p.get("items") or [])
	)
	return THREE_WAY if has_stock else TWO_WAY
