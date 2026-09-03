"""Stage 3 — GST. SPEC §5.

Every rule here belongs to `india_compliance`; this module only turns its answers into
audit rows. SPEC §8's rule governs the status checks: **a GSTIN whose status we cannot
determine is unknown, not invalid** — Skipped, never Fail. Rejecting a legitimate
supplier because GSTN was unreachable is the worse failure.
"""

import frappe
from frappe.utils import flt

from india_compliance.gst_india.doctype.gstin.gstin import validate_gstin_status
from india_compliance.gst_india.utils import get_state

from .base import ERROR, FAIL, INFO, PASS, SKIP, WARN, row, verdict
from .gst_utils import gstin_doc, gstin_error, pan_of

STAGE = "gst"
COMPOSITION = "Registered Composition"


def run(p):
	doc_gstin = p.get("supplier_gstin")
	invoice_date = p.get("invoice_date")

	err = gstin_error(doc_gstin, "Supplier GSTIN")
	out = [row("V-GST-01/02", STAGE, ERROR, verdict(not err),
		err or "Supplier GSTIN is well-formed.", "valid GSTIN", doc_gstin)]

	out += _status_checks(doc_gstin, invoice_date, skip=bool(err))
	out.append(_composition(p))
	out.append(_supplier_pan(p, doc_gstin))
	out.append(_place_of_supply(p, doc_gstin))
	out.append(_hsn_registered(p))
	out.append(row("V-GST-11a", STAGE, ERROR, SKIP,
		"E-invoice mandate check needs a per-supplier turnover flag; no such field on Supplier."))
	out.append(row("V-GST-15", STAGE, ERROR, SKIP,
		"Reverse charge needs `is_reverse_charge` on the payload; not in the contract yet."))
	out.append(_gstr_2b(p))
	return out


def _status_checks(doc_gstin, invoice_date, skip=False):
	"""V-GST-03 (active now) and V-GST-04a (active as on the invoice date).

	V-GST-04a is a *call*, not an implementation: india_compliance's
	`validate_gstin_status` already compares against registration_date / cancelled_date.
	SPEC §5 Stage 3 claims we must build this. It is wrong.
	"""
	doc = None if skip else gstin_doc(doc_gstin, invoice_date)
	if not doc:
		return [
			row(cid, STAGE, ERROR, SKIP,
				f"No GSTIN record for {doc_gstin}, so its {what} is unknown — not invalid. "
				"Enable the GSTN API in GST Settings to populate it.")
			for cid, what in (("V-GST-03", "current status"),
				("V-GST-04a", "status as on the invoice date"))
		]

	out = [row("V-GST-03", STAGE, ERROR, verdict(doc.status == "Active"),
		f"Supplier GSTIN status is {doc.status}.", "Active", doc.status)]
	try:
		validate_gstin_status(doc, transaction_date=invoice_date, throw=True)
		out.append(row("V-GST-04a", STAGE, ERROR, PASS,
			"Supplier GSTIN was active as on the invoice date.",
			f"active on {invoice_date}", doc.status))
	except Exception as e:
		out.append(row("V-GST-04a", STAGE, ERROR, FAIL, frappe.utils.strip_html(str(e)),
			f"active on {invoice_date}",
			f"registered {doc.registration_date}, cancelled {doc.cancelled_date}"))
	return out


def _composition(p):
	"""V-GST-05: a composition supplier may not charge GST."""
	category = frappe.db.get_value("Supplier", p.get("supplier"), "gst_category") if p.get("supplier") else None
	if category != COMPOSITION:
		return row("V-GST-05", STAGE, ERROR, PASS,
			"Supplier is not under the composition scheme.", found=category)
	taxes = sum(flt(p.get(k)) for k in ("cgst", "sgst", "igst", "cess"))
	return row("V-GST-05", STAGE, ERROR, verdict(not taxes),
		"Composition supplier has charged GST.", "zero tax", f"{taxes:.2f}")


def _supplier_pan(p, doc_gstin):
	"""V-GST-07."""
	master_pan = frappe.db.get_value("Supplier", p.get("supplier"), "pan") if p.get("supplier") else None
	doc_pan = pan_of(doc_gstin)
	if not (doc_pan and master_pan):
		return row("V-GST-07", STAGE, ERROR, FAIL,
			"Could not read a PAN from both the document GSTIN and the Supplier master.",
			master_pan, doc_pan)
	return row("V-GST-07", STAGE, ERROR, verdict(doc_pan == master_pan),
		"PAN embedded in the invoice GSTIN differs from the supplier's.", master_pan, doc_pan)


def _place_of_supply(p, doc_gstin):
	"""V-GST-12/13: the state code is real, and intra-state carries CGST+SGST while
	inter-state carries IGST."""
	pos = str(p.get("place_of_supply") or "")[:2]
	supplier_state = doc_gstin[:2] if doc_gstin and len(doc_gstin) >= 2 else None

	if not (pos.isdigit() and get_state(pos)):
		return row("V-GST-12/13", STAGE, ERROR, FAIL,
			"Place of supply is missing or is not a real state code.",
			"NN-State Name", p.get("place_of_supply"))
	if not supplier_state:
		return row("V-GST-12/13", STAGE, ERROR, FAIL,
			"Cannot read the supplier's state from its GSTIN.", "NN", doc_gstin)

	intra_expected = pos == supplier_state
	intra_found = bool(flt(p.get("cgst")) or flt(p.get("sgst")))
	inter_found = bool(flt(p.get("igst")))
	ok = (intra_expected and intra_found and not inter_found) or (
		not intra_expected and inter_found and not intra_found
	)
	return row("V-GST-12/13", STAGE, ERROR, verdict(ok),
		f"Tax type does not match the place of supply ({get_state(pos)}).",
		"CGST+SGST" if intra_expected else "IGST",
		"CGST+SGST" if intra_found else ("IGST" if inter_found else "no tax"))


def _hsn_registered(p):
	"""V-GST-14: every HSN/SAC exists in the GST HSN Code master."""
	codes = {str(line.get("hsn_sac")) for line in (p.get("items") or []) if line.get("hsn_sac")}
	if not codes:
		return row("V-GST-14", STAGE, WARN, SKIP, "No HSN/SAC codes on the invoice to check.")
	known = set(frappe.get_all("GST HSN Code", filters={"name": ("in", list(codes))}, pluck="name"))
	missing = sorted(codes - known)
	# ponytail: existence only. Rate-vs-HSN needs a per-HSN rate the master does not
	# carry; that half of V-GST-14 arrives with Stage 4a's PO tax comparison.
	return row("V-GST-14", STAGE, WARN, verdict(not missing),
		f"HSN/SAC not found in the GST HSN Code master: {missing}" if missing
		else "Every HSN/SAC is a registered code.",
		"registered HSN/SAC", missing or None)


def _gstr_2b(p):
	"""V-GST-16: non-blocking by design. Stamps whether the supplier has filed this
	invoice; absence before the filing date is normal, not a defect."""
	gstin, bill_no = p.get("supplier_gstin"), p.get("invoice_no")
	if not (gstin and bill_no):
		return row("V-GST-16", STAGE, INFO, SKIP, "No supplier GSTIN or bill number to reconcile.")
	hit = frappe.db.exists("GST Inward Supply", {"supplier_gstin": gstin, "bill_no": bill_no})
	return row("V-GST-16", STAGE, INFO, PASS,
		"Matched in GSTR-2A/2B." if hit else "Not yet in GSTR-2A/2B — normal before the supplier files.",
		"a GST Inward Supply row", hit or "none")
