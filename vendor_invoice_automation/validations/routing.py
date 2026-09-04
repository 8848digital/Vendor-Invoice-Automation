"""Stage 4 — Routing. SPEC §5.

Decides `matching_mode`. The non-PO branch of SPEC's routing is gone: non-PO invoices
are created independently of this pipeline, so there is nothing here to gate them on.
"""

THREE_WAY, TWO_WAY, NON_PO = "3-Way", "2-Way", "Non-PO"
UNKNOWN = "Unknown"
PO_MODES = (THREE_WAY, TWO_WAY)


def run(p, c):
	"""Returns the matching mode. No audit rows — routing is a decision, not a check."""
	if not p.get("po_number"):
		return NON_PO

	items = c.get("items")
	if not items:
		# Without `is_stock_item` per line there is no way to tell 2-Way from 3-Way, and
		# guessing either one silently changes which checks run — 2-Way would drop GRN
		# matching entirely. Say so instead, and let the matching blocks Skip.
		return UNKNOWN

	# A stock line means goods physically arrive, so a GRN must corroborate the invoice.
	has_stock = any(
		(items.get(str(line.get("item_code") or "")) or {}).get("is_stock_item")
		for line in (p.get("items") or [])
	)
	return THREE_WAY if has_stock else TWO_WAY
