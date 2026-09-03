"""Stage 4a / 5 — PO and GRN matching. SPEC §5.

Not built. This module exists so the gap is explicit and **fails closed**: a PO invoice
returns an Error-severity Fail rather than coming back green on checks that never ran.
Deleting these rows without implementing the real ones would silently turn every
unmatched PO invoice into an auto-createable one.
"""

from .base import ERROR, FAIL, row
from .routing import THREE_WAY


def run(mode):
	out = [row("V-PO-PENDING", "po_matching", ERROR, FAIL,
		"PO matching (V-PO-01..16) is not implemented yet — held by design, never auto-created.")]
	if mode == THREE_WAY:
		out.append(row("V-GRN-PENDING", "grn_matching", ERROR, FAIL,
			"GRN matching (V-GRN-02..11) is not implemented yet — held by design."))
	return out
