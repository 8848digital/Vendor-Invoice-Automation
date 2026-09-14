"""Identity checks — is this document really from this supplier?

The duplicate layers moved to `duplicate.py` (requirement 7) and the QR/IRN layers to
`einvoice.py` (requirement 8), where they are real checks rather than placeholders.
What is left is the pair that needs nothing but the Supplier master, plus V-FAKE-08.
"""

import re

from .base import ERROR, FAIL, PASS, UNSET, row, unchecked, verdict
from .gst_utils import pan_of

STAGE = "fraud"

# SPEC §5 Stage 1 requires extracted text carrying imperative instruction patterns to be
# logged as a fraud signal, not a parse error. An invoice image is untrusted input read by a
# model that holds write tools, so this is the one mitigation that cannot be talked out of:
# it runs here, deterministically, after extraction and before anything can act on it.
INJECTION_PATTERNS = (
	# Up to two filler words, so "ignore all previous instructions" and "disregard the
	# above" both land without the alternation having to enumerate determiners.
	r"ignore\s+(?:\w+\s+){0,2}(?:previous|prior|above|earlier)",
	r"disregard\s+(?:\w+\s+){0,2}(?:previous|prior|above|earlier|instructions?)",
	r"mark\s+(?:this|it)?\s*as\s+(?:approved|paid|verified)",
	r"you\s+are\s+now\s+",
	r"^\s*system\s*:",
	r"<\s*/?\s*(?:system|assistant|instructions?)\s*>",
	r"new\s+instructions?\s*:",
	r"auto[-\s]?(?:approve|create)\s+(?:this|it)",
)
_INJECTION = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE | re.MULTILINE)


def run(p, c):
	sup = c.get("supplier", UNSET)
	doc_gstin = p.get("supplier_gstin")

	if sup is UNSET:
		rows = [
			unchecked("V-FAKE-01", STAGE, ERROR, "supplier"),
			unchecked("V-FAKE-07", STAGE, ERROR, "supplier"),
		]
	else:
		rows = [_gstin_is_the_suppliers(sup, doc_gstin), _pan_matches(sup, doc_gstin)]

	rows.append(_no_injected_instructions(p))
	return rows


def _gstin_is_the_suppliers(sup, doc_gstin):
	"""V-FAKE-01: the GSTIN printed on the document must be the supplier's own."""
	if not (sup and sup.get("gstin")):
		return row("V-FAKE-01", STAGE, ERROR, FAIL,
			"Supplier master has no GSTIN to compare the document against.",
			"supplier GSTIN on file", None)
	ok = doc_gstin == sup["gstin"]
	return row("V-FAKE-01", STAGE, ERROR, verdict(ok),
		"GSTIN on the document is the supplier's registered GSTIN." if ok
		else "GSTIN on the document is not the supplier's registered GSTIN.",
		sup["gstin"], doc_gstin)


def _pan_matches(sup, doc_gstin):
	"""V-FAKE-07: PAN embedded in the document's GSTIN vs the supplier's own PAN field.

	This is not a duplicate of V-FAKE-01: a GSTIN from a different *state* carries the
	same PAN, so V-FAKE-01 catches it and this correctly does not.
	"""
	doc_pan = pan_of(doc_gstin)
	master_pan = sup.get("pan") if sup else None
	if not (master_pan and doc_pan):
		return row("V-FAKE-07", STAGE, ERROR, FAIL,
			"Could not read a PAN from both the document GSTIN and the Supplier master.",
			master_pan, doc_pan)
	ok = doc_pan == master_pan
	return row("V-FAKE-07", STAGE, ERROR, verdict(ok),
		"PAN embedded in the document GSTIN is the supplier's PAN." if ok
		else "PAN embedded in the document GSTIN is not the supplier's PAN.",
		master_pan, doc_pan)


def _no_injected_instructions(p):
	"""V-FAKE-08 — extracted text that reads as an instruction to the model.

	Blocking. A document trying to steer the pipeline that reads it is not a document to
	book on a warning; whatever else it says can no longer be taken at face value.
	"""
	hits = sorted({m.group(0).strip() for m in _INJECTION.finditer(_text_of(p))})
	return row("V-FAKE-08", STAGE, ERROR, verdict(not hits),
		"Extracted text contains instruction-like patterns aimed at the reading model." if hits
		else "No instruction-like patterns in the extracted text.",
		"no imperative instructions in document text", hits or None)


def _text_of(p):
	"""Every free-text field the extractor could have carried off the document."""
	parts = [str(p.get(k) or "") for k in ("supplier", "invoice_no", "notes", "remarks", "terms")]
	for line in p.get("items") or []:
		parts += [str(line.get(k) or "") for k in ("description", "item_name", "item_code")]
	return "\n".join(parts)
