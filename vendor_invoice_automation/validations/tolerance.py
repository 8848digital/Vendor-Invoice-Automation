"""Stage 4b — Tolerance. SPEC §5 V-PO-10/11/12.

ERPNext already owns these limits and enforces them itself inside
`Purchase Invoice.validate()`. This module reads the **same** fields, so a pre-check
verdict and the eventual insert cannot disagree. There are deliberately no tolerances
of our own here — no `Vendor Invoice Tolerance Rule` lookup:

    rate    Buying Settings.maintain_same_rate / _action / role_to_override_stop_action
            — an exact match with ERPNext's own 0.01 threshold, not a percentage band
    amount  Item.over_billing_allowance, else Accounts Settings.over_billing_allowance,
            waived by role_allowed_to_over_bill — cumulative per ordered row
    qty     no Purchase Invoice equivalent exists in ERPNext; see `_qty`

The payload is pre-insert OCR data, so it carries no `po_detail` row ids. `item_code`
is the only key available, and PO rows are folded onto it.
"""

import frappe
from frappe.utils import flt

from .base import ERROR, FAIL, INFO, PASS, SKIP, WARN, row, verdict
from .routing import PO_MODES

STAGE = "tolerance"
CHECKS = ("V-PO-10", "V-PO-11", "V-PO-12")

# ERPNext's own threshold — utilities/transaction_base.py:validate_rate_with_reference_doc.
RATE_EPSILON = 0.01


def run(p, mode):
	"""Returns audit rows. Empty for Non-PO — there is no order to compare against."""
	if mode not in PO_MODES:
		return []

	po = p.get("po_number")
	ordered = _ordered_by_item(po)
	if not ordered:
		return _all_skipped(f"No submitted Purchase Order Item rows for {po}.")

	billed = [(line, ordered[code]) for line in (p.get("items") or [])
		if (code := str(line.get("item_code") or "")) in ordered]
	if not billed:
		return _all_skipped(f"No invoice line resolves to an item on {po}; line matching is V-PO-PENDING's job.")

	return [_qty(), _rate(billed), _amount(billed)]


def _all_skipped(why):
	return [row(cid, STAGE, ERROR, SKIP, why) for cid in CHECKS]


def _ordered_by_item(po):
	"""Submitted PO rows folded by item_code. Amounts add up; rates stay a set, because
	the same item may sit on the order twice at two prices and either one is legitimate."""
	rows = frappe.get_all("Purchase Order Item", filters={"parent": po, "docstatus": 1},
		fields=["item_code", "rate", "amount", "billed_amt"]) if po else []

	out = {}
	for r in rows:
		agg = out.setdefault(r.item_code, frappe._dict(rates=set(), amount=0.0, billed=0.0))
		agg.rates.add(flt(r.rate))
		agg.amount += flt(r.amount)
		agg.billed += flt(r.billed_amt)
	return out


def _qty():
	"""V-PO-10. ERPNext has no qty allowance between a Purchase Invoice and its order —
	`Stock Settings.over_delivery_receipt_allowance` governs the *receipt*, so it belongs
	to GRN matching. Skipped rather than invented here."""
	return row("V-PO-10", STAGE, ERROR, SKIP,
		"ERPNext has no Purchase Invoice qty allowance. Over-receipt is checked on the "
		"Purchase Receipt via Stock Settings.over_delivery_receipt_allowance.")


def _rate(billed):
	"""V-PO-11: Buying Settings decides whether the rate may move at all, and whether a
	move stops the document or only warns."""
	enforced, action, override_role = frappe.get_cached_value("Buying Settings", None,
		["maintain_same_rate", "maintain_same_rate_action", "role_to_override_stop_action"])
	if not enforced:
		return row("V-PO-11", STAGE, INFO, PASS,
			"Buying Settings does not maintain the same rate through the purchase cycle.")

	off = [f"{line['item_code']}: {flt(line.get('rate'))} vs ordered {sorted(po.rates)}"
		for line, po in billed
		if all(abs(flt(line.get("rate")) - r) >= RATE_EPSILON for r in po.rates)]

	# "Warn" and a held override role are both non-blocking in ERPNext; mirror that here
	# rather than turning a document ERPNext would accept red.
	blocking = action == "Stop" and override_role not in frappe.get_roles()
	return row("V-PO-11", STAGE, ERROR if blocking else WARN, verdict(not off),
		"Invoice rate differs from the ordered rate." if off else "Every billed rate matches the order.",
		"the ordered rate", off or None)


def _amount(billed):
	"""V-PO-12 (and SPEC's V-PO-14): ERPNext's over-billing rule — what is already billed
	against the ordered row, plus this invoice, against the row's allowance."""
	allowances = frappe.get_cached_value("Accounts Settings", None,
		["over_billing_allowance", "role_allowed_to_over_bill"])
	global_allowance, override_role = flt(allowances[0]), allowances[1]
	epsilon = 1 / (10 ** frappe.get_precision("Purchase Order Item", "amount"))

	over = []
	for line, po in billed:
		item_allowance = frappe.get_cached_value("Item", line["item_code"], "over_billing_allowance")
		max_allowed = po.amount * (100 + (flt(item_allowance) or global_allowance)) / 100
		total = po.billed + flt(line.get("amount"))
		if total - max_allowed > epsilon:
			over.append(f"{line['item_code']}: {total:.2f} billed against a {max_allowed:.2f} ceiling")

	if over and override_role in frappe.get_roles():
		return row("V-PO-12", STAGE, WARN, FAIL,
			f"Over-billed, but the {override_role} role waives it — ERPNext would accept this.",
			"cumulative billing within the allowance", over)
	return row("V-PO-12", STAGE, ERROR, verdict(not over),
		"Cumulative billing exceeds the ordered amount plus its allowance." if over
		else "Cumulative billing is within the ordered amount plus its allowance.",
		"cumulative billing within the allowance", over or None)
