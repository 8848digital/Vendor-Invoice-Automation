"""Stage 2 — Duplicate & fraud. SPEC §5.

SPEC is explicit: **run every layer, do not stop at the first hit.** A document that
trips one fraud signal usually trips several, and the shape of the set is what a human
reviews.
"""

import frappe

from .base import ERROR, FAIL, PASS, SKIP, row, verdict
from .gst_utils import pan_of

STAGE = "fraud"


def run(p):
	supplier, doc_gstin = p.get("supplier"), p.get("supplier_gstin")
	sup = frappe.db.get_value("Supplier", supplier, ["gstin", "pan"], as_dict=True) if supplier else None

	return [
		*_unavailable_layers(),
		_already_booked(supplier, p.get("invoice_no")),
		_gstin_is_the_suppliers(sup, doc_gstin),
		*_qr_layers(),
		_pan_matches(sup, doc_gstin),
	]


def _unavailable_layers():
	"""Layers that cannot run here. Each says why, so `skipped[]` is actionable rather
	than a silent hole."""
	out = [row("V-DUP-02", STAGE, ERROR, SKIP,
		"No `irn` field on Purchase Invoice; nothing records the IRNs we have already booked.")]
	# V-DUP-03/05/07 compare against previously *uploaded* invoices. This app keeps no
	# upload history by design.
	out += [
		row(cid, STAGE, ERROR, SKIP,
			"Requires upload history; this app is stateless. Caller must dedupe its own submissions.")
		for cid in ("V-DUP-03", "V-DUP-05", "V-DUP-07")
	]
	return out


def _qr_layers():
	"""V-FAKE-02/04 — offline JWS verification against NIC's public certificate."""
	return [
		row(cid, STAGE, ERROR, SKIP, f"{what} not implemented yet.")
		for cid, what in (
			("V-FAKE-02", "QR JWS signature verification"),
			("V-FAKE-04", "QR payload vs document header"),
		)
	]


def _already_booked(supplier, bill_no):
	"""V-DUP-04: same supplier + bill_no already on a Purchase Invoice. Cancelled
	invoices count — no docstatus filter, deliberately."""
	if not (supplier and bill_no):
		return row("V-DUP-04", STAGE, ERROR, FAIL, "No supplier or invoice number to dedupe on.")
	hits = frappe.get_all("Purchase Invoice",
		filters={"supplier": supplier, "bill_no": bill_no},
		fields=["name", "docstatus"], limit=5)
	return row("V-DUP-04", STAGE, ERROR, verdict(not hits),
		f"Already booked as {', '.join(h.name for h in hits)}." if hits
		else "No existing Purchase Invoice for this bill number.",
		"no existing Purchase Invoice", [h.name for h in hits] or None)


def _gstin_is_the_suppliers(sup, doc_gstin):
	"""V-FAKE-01: the GSTIN printed on the document must be the supplier's own."""
	if not (sup and sup.gstin):
		return row("V-FAKE-01", STAGE, ERROR, FAIL,
			"Supplier master has no GSTIN to compare the document against.",
			"supplier GSTIN on file", None)
	return row("V-FAKE-01", STAGE, ERROR, verdict(doc_gstin == sup.gstin),
		"GSTIN on the document is not the supplier's registered GSTIN.", sup.gstin, doc_gstin)


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
	return row("V-FAKE-07", STAGE, ERROR, verdict(doc_pan == sup.pan),
		"PAN embedded in the document GSTIN is not the supplier's PAN.", sup.pan, doc_pan)
