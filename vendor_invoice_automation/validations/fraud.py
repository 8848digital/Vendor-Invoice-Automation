"""Identity checks — is this document really from this supplier?

The duplicate layers moved to `duplicate.py` (requirement 7) and the QR/IRN layers to
`einvoice.py` (requirement 8), where they are real checks rather than placeholders.
What is left is the pair that needs nothing but the Supplier master.
"""

import frappe

from .base import ERROR, FAIL, row, verdict
from .gst_utils import pan_of

STAGE = "fraud"


def run(p):
	supplier, doc_gstin = p.get("supplier"), p.get("supplier_gstin")
	sup = frappe.db.get_value("Supplier", supplier, ["gstin", "pan"], as_dict=True) if supplier else None
	return [_gstin_is_the_suppliers(sup, doc_gstin), _pan_matches(sup, doc_gstin)]


def _gstin_is_the_suppliers(sup, doc_gstin):
	"""V-FAKE-01: the GSTIN printed on the document must be the supplier's own."""
	if not (sup and sup.gstin):
		return row("V-FAKE-01", STAGE, ERROR, FAIL,
			"Supplier master has no GSTIN to compare the document against.",
			"supplier GSTIN on file", None)
	ok = doc_gstin == sup.gstin
	return row("V-FAKE-01", STAGE, ERROR, verdict(ok),
		"GSTIN on the document is the supplier's registered GSTIN." if ok
		else "GSTIN on the document is not the supplier's registered GSTIN.",
		sup.gstin, doc_gstin)


def _pan_matches(sup, doc_gstin):
	"""V-FAKE-07: PAN embedded in the document's GSTIN vs the supplier's own PAN field.

	This is not a duplicate of V-FAKE-01: a GSTIN from a different *state* carries the
	same PAN, so V-FAKE-01 catches it and this correctly does not.
	"""
	doc_pan = pan_of(doc_gstin)
	if not (sup and sup.pan and doc_pan):
		return row("V-FAKE-07", STAGE, ERROR, FAIL,
			"Could not read a PAN from both the document GSTIN and the Supplier master.",
			sup.pan if sup else None, doc_pan)
	ok = doc_pan == sup.pan
	return row("V-FAKE-07", STAGE, ERROR, verdict(ok),
		"PAN embedded in the document GSTIN is the supplier's PAN." if ok
		else "PAN embedded in the document GSTIN is not the supplier's PAN.",
		sup.pan, doc_pan)
