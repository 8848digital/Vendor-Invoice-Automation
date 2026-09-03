"""Stage 1 — Extraction validations. SPEC §5.

Extraction itself happens in the caller. What lives here is the discipline SPEC states
as non-negotiable: **the model extracts, it never computes.** Every total is recomputed
in Python from the raw line values, and a reported total is only ever something to
check against, never something to trust.
"""

import frappe
from frappe.utils import flt, getdate

from india_compliance.gst_india.constants import VALID_HSN_LENGTHS

from .base import ERROR, FAIL, MONETARY_AGREEMENT_TOLERANCE, PASS, SKIP, WARN, row, verdict

STAGE = "extraction"


def run(p):
	tol = MONETARY_AGREEMENT_TOLERANCE
	lines = p.get("items") or []
	return [
		_line_arithmetic(lines, tol),
		_header_arithmetic(p, tol),
		_tax_split(p),
		_declared_vs_extracted(p, tol),
		_hsn_shape(lines),
		_fiscal_year(p),
		_company_gstin(p),
	]


def _line_arithmetic(lines, tol):
	"""V-EXT-03: qty x rate = amount, per line."""
	bad = [
		i for i, line in enumerate(lines, start=1)
		if abs(flt(line.get("qty")) * flt(line.get("rate")) - flt(line.get("amount"))) > tol
	]
	return row("V-EXT-03", STAGE, ERROR, verdict(not bad and bool(lines)),
		"No lines supplied." if not lines else
		(f"Line arithmetic broken on row(s): {bad}" if bad else "Line arithmetic holds."),
		"qty x rate = amount", f"{len(bad)} bad of {len(lines)}")


def _header_arithmetic(p, tol):
	"""V-EXT-04: the grand total is rebuilt from its parts, not read off the document."""
	taxes = sum(flt(p.get(k)) for k in ("cgst", "sgst", "igst", "cess"))
	computed = flt(p.get("taxable_value")) + taxes + flt(p.get("round_off"))
	claimed = flt(p.get("grand_total"))
	ok = abs(computed - claimed) <= tol
	return row("V-EXT-04", STAGE, ERROR, verdict(ok),
		"Header total reconciles with taxable value + tax + round off." if ok
		else "Header total does not reconcile with taxable value + tax + round off.",
		f"{computed:.2f}", f"{claimed:.2f}")


def _tax_split(p):
	"""V-EXT-05: CGST+SGST xor IGST, never both."""
	taxes = sum(flt(p.get(k)) for k in ("cgst", "sgst", "igst", "cess"))
	intra = flt(p.get("cgst")) or flt(p.get("sgst"))
	inter = flt(p.get("igst"))
	coherent = not (intra and inter) and (bool(intra) != bool(inter) or not taxes)
	return row("V-EXT-05", STAGE, ERROR, verdict(coherent),
		"Tax split is coherent." if coherent
		else "Tax split is incoherent: CGST/SGST and IGST cannot both carry value.",
		"CGST+SGST xor IGST", f"cgst={p.get('cgst')} sgst={p.get('sgst')} igst={p.get('igst')}")


def _declared_vs_extracted(p, tol):
	"""V-EXT-07: SPEC is explicit that the mismatch is itself a signal — report it,
	do not discard it."""
	declared = (p.get("declared") or {}).get("grand_total")
	if declared is None:
		return row("V-EXT-07", STAGE, WARN, SKIP, "No declared total supplied by the uploader.")
	claimed = flt(p.get("grand_total"))
	ok = abs(flt(declared) - claimed) <= tol
	return row("V-EXT-07", STAGE, WARN, verdict(ok),
		"Uploader's declared total agrees with the invoice." if ok
		else "Uploader's declared total disagrees with the invoice.",
		f"{flt(declared):.2f}", f"{claimed:.2f}")


def _hsn_shape(lines):
	"""V-EXT-08: present and 4/6/8 digits, per india_compliance's own constant."""
	bad = [
		i for i, line in enumerate(lines, start=1)
		if not (str(line.get("hsn_sac") or "").isdigit()
			and len(str(line.get("hsn_sac"))) in VALID_HSN_LENGTHS)
	]
	return row("V-EXT-08", STAGE, WARN, verdict(not bad),
		f"HSN/SAC missing or wrong length on row(s): {bad}" if bad
		else "HSN/SAC well-formed on every line.",
		f"{' / '.join(map(str, VALID_HSN_LENGTHS))} digits", f"{len(bad)} bad of {len(lines)}")


def _fiscal_year(p):
	"""V-EXT-09."""
	from erpnext.accounts.utils import get_fiscal_year

	date = p.get("invoice_date")
	if not date:
		return row("V-EXT-09", STAGE, ERROR, FAIL, "No invoice date to place in a fiscal year.")
	try:
		fy = get_fiscal_year(getdate(date), company=p.get("company"), as_dict=True)
	except Exception as e:
		return row("V-EXT-09", STAGE, ERROR, FAIL, frappe.utils.strip_html(str(e)),
			"an open Fiscal Year", date)
	# ponytail: Period Closing Voucher is not consulted; ERPNext blocks a closed period
	# at insert() anyway, and Stage 7 will insert through ERPNext's own mapper.
	return row("V-EXT-09", STAGE, ERROR, PASS, "Invoice date falls in an open Fiscal Year.",
		found=fy.get("name"))


def _company_gstin(p):
	"""V-EXT-10: the buyer GSTIN on the document is one of ours."""
	from india_compliance.gst_india.utils import get_gstin_list

	claimed, company = p.get("company_gstin"), p.get("company")
	if not claimed:
		return row("V-EXT-10", STAGE, ERROR, FAIL,
			"Invoice carries no buyer GSTIN.", "a registered company GSTIN", None)
	if not company:
		return row("V-EXT-10", STAGE, ERROR, FAIL,
			"No company supplied, so the buyer GSTIN cannot be checked against one.",
			"a company", None)
	# ponytail: get_gstin_list enforces frappe.has_permission("Company"), which Guest
	# never has; this endpoint is guest-facing and read-only, so elevate for the lookup.
	user = frappe.session.user
	frappe.set_user("Administrator")
	try:
		registered = get_gstin_list(company, "Company") or []
	finally:
		frappe.set_user(user)
	ok = claimed in registered
	return row("V-EXT-10", STAGE, ERROR, verdict(ok),
		f"Buyer GSTIN is registered against {company}." if ok
		else f"Buyer GSTIN is not registered against {company}.",
		registered or "none on file", claimed)
