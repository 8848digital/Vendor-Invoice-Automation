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

from .base import (
	ERROR,
	FAIL,
	INFO,
	MONETARY_AGREEMENT_TOLERANCE,
	PASS,
	SKIP,
	WARN,
	row,
	verdict,
)
from .gst_2b import inward_supply
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

	# Requirement 9's remaining rules, all off the supplier's own filing. Without a 2B
	# row none of them can run, and V-GST-16 already says exactly that — so they stay
	# quiet rather than repeating it three times.
	supply = inward_supply(p)
	out.append(_reflected_in_2b(p, supply))
	if supply:
		out.append(_return_filing_status(p, supply))
		out.append(_reverse_charge(p, supply))
	return out


def _status_checks(doc_gstin, invoice_date, skip=False):
	"""V-GST-03 (active now) and V-GST-04a (active as on the invoice date).

	V-GST-04a is a *call*, not an implementation: india_compliance's
	`validate_gstin_status` already compares against registration_date / cancelled_date.
	SPEC §5 Stage 3 claims we must build this. It is wrong.
	"""
	doc = None if skip else gstin_doc(doc_gstin, invoice_date)
	if not doc:
		return [row("V-GST-03", STAGE, ERROR, SKIP,
			f"No GSTIN record for {doc_gstin}, so its status — now and as on the invoice "
			"date (V-GST-04a) — is unknown, not invalid. Enable the GSTN API in GST "
			"Settings to populate it.")]

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
		"Composition supplier has charged GST." if taxes
		else "Composition supplier has correctly charged no GST.",
		"zero tax", f"{taxes:.2f}")


def _supplier_pan(p, doc_gstin):
	"""V-GST-07."""
	master_pan = frappe.db.get_value("Supplier", p.get("supplier"), "pan") if p.get("supplier") else None
	doc_pan = pan_of(doc_gstin)
	if not (doc_pan and master_pan):
		return row("V-GST-07", STAGE, ERROR, FAIL,
			"Could not read a PAN from both the document GSTIN and the Supplier master.",
			master_pan, doc_pan)
	ok = doc_pan == master_pan
	return row("V-GST-07", STAGE, ERROR, verdict(ok),
		"PAN embedded in the invoice GSTIN matches the supplier's." if ok
		else "PAN embedded in the invoice GSTIN differs from the supplier's.",
		master_pan, doc_pan)


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
		f"Tax type matches the place of supply ({get_state(pos)})." if ok
		else f"Tax type does not match the place of supply ({get_state(pos)}).",
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


def _reflected_in_2b(p, supply):
	"""V-GST-16 — is this invoice reflected in GSTR-2B, and does it agree with ours?

	Info severity by design. Absence before the supplier's filing date is normal, not
	a defect, and holding every invoice until 2B catches up would stall the books.
	"""
	if not (p.get("supplier_gstin") and p.get("invoice_no")):
		return row("V-GST-16", STAGE, INFO, SKIP, "No supplier GSTIN or bill number to reconcile.")
	if not supply:
		return row("V-GST-16", STAGE, INFO, PASS,
			"Not yet in GSTR-2A/2B — normal before the supplier files.",
			"a GST Inward Supply row", "none")

	off = [
		f"{field}: 2B {flt(supply.get(field)):.2f} vs invoice {flt(p.get(field)):.2f}"
		for field in ("taxable_value", "cgst", "sgst", "igst", "cess")
		if abs(flt(supply.get(field)) - flt(p.get(field))) > MONETARY_AGREEMENT_TOLERANCE
	]
	return row("V-GST-16", STAGE, INFO, verdict(not off),
		"Invoice is in GSTR-2B but the values disagree with the document." if off
		else "Invoice is reflected in GSTR-2B and the values agree.",
		"2B values match the invoice", off or supply.get("name"))


def _return_filing_status(p, supply):
	"""V-GST-17 — has the supplier actually filed the return carrying this invoice?

	Two independent sources: the flags on the 2B row itself, and india_compliance's
	`get_gstr_1_filed_upto`, which answers for the supplier generally. Warning, not
	Error — an unfiled supplier is a collections problem and an ITC-timing problem,
	not an invalid invoice.
	"""
	from india_compliance.gst_india.doctype.gstin.gstin import get_gstr_1_filed_upto

	if supply and (supply.get("gstr_1_filled") or supply.get("is_supplier_return_filed")):
		return row("V-GST-17", STAGE, WARN, PASS,
			"Supplier has filed the GSTR-1 carrying this invoice.",
			"GSTR-1 filed", supply.get("gstr_1_filing_date") or supply.get("sup_return_period"))

	filed_upto = None
	try:
		filed_upto = get_gstr_1_filed_upto(p.get("supplier_gstin"))
	except Exception:
		# No GSTIN row, or the GSTN API is disabled. Unknown, not unfiled.
		pass

	return row("V-GST-17", STAGE, WARN, FAIL,
		"Invoice is in GSTR-2B but the supplier has not filed the return carrying it.",
		"GSTR-1 filed", f"filed upto {filed_upto}" if filed_upto else "not filed")


def _reverse_charge(p, supply):
	"""V-GST-15 — reverse charge, now that there is something to compare against.

	`is_reverse_charge` is a real Purchase Invoice field under india_compliance
	(PURCHASE_REVERSE_CHARGE_FIELDS), and the supplier states its own answer in 2B.
	A disagreement decides who pays the tax, so it is blocking.
	"""
	claimed = p.get("is_reverse_charge")
	theirs = bool(supply.get("is_reverse_charge"))
	if claimed is None:
		return row("V-GST-15", STAGE, WARN, PASS,
			"Invoice does not state reverse charge; taking the supplier's filing.",
			found="reverse charge" if theirs else "forward charge")

	ok = bool(claimed) == theirs
	return row("V-GST-15", STAGE, ERROR, verdict(ok),
		"Invoice and the supplier's GSTR-1 filing agree on reverse charge." if ok
		else "Invoice and the supplier's GSTR-1 filing disagree on reverse charge.",
		"reverse charge" if theirs else "forward charge",
		"reverse charge" if claimed else "forward charge")
