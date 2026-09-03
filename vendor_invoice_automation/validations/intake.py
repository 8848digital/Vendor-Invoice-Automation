"""Stage 0 — Intake. SPEC §5.

V-INT-01/02/03 are the caller's: they need the file itself, which this API never sees.
"""

import frappe
from frappe.utils import add_days, getdate, nowdate

from .base import ERROR, FAIL, MAX_INVOICE_AGE_DAYS, PASS, WARN, row, verdict

STAGE = "intake"


def run(p):
	"""Returns audit rows. If V-INT-04 fails the pipeline stops — see `pipeline.run_all`."""
	supplier = p.get("supplier")

	if not supplier or not frappe.db.exists("Supplier", supplier):
		return [row("V-INT-04", STAGE, ERROR, FAIL,
			"Uploader/context did not resolve to exactly one Supplier.", "1 Supplier", supplier)]

	out = [row("V-INT-04", STAGE, ERROR, PASS, "Supplier resolved.", found=supplier)]
	sup = frappe.db.get_value(
		"Supplier", supplier,
		["disabled", "on_hold", "hold_type", "release_date", "gstin", "pan"],
		as_dict=True,
	)
	out.append(_supplier_active(sup))
	out.append(_supplier_identified(sup))
	out.append(_invoice_age(p))
	return out


def _supplier_active(sup):
	"""V-INT-05: a released hold is not a hold."""
	released = sup.release_date and getdate(sup.release_date) <= getdate()
	blocked = sup.disabled or (sup.on_hold and not released)
	return row("V-INT-05", STAGE, ERROR, verdict(not blocked),
		"Supplier disabled or on hold." if blocked else "Supplier active.",
		"enabled, not on hold",
		f"disabled={sup.disabled} on_hold={sup.on_hold} hold_type={sup.hold_type}")


def _supplier_identified(sup):
	"""V-INT-06: GSTIN and PAN on the master, both real fields under india_compliance."""
	ok = bool(sup.gstin and sup.pan)
	return row("V-INT-06", STAGE, ERROR, verdict(ok),
		"Supplier master carries both a GSTIN and a PAN." if ok
		else "Supplier master is missing a GSTIN or PAN.",
		"GSTIN + PAN on file", f"gstin={sup.gstin} pan={sup.pan}")


def _invoice_age(p):
	"""V-INT-07: not in the future, not older than the configured window."""
	date = p.get("invoice_date")
	if not date:
		return row("V-INT-07", STAGE, WARN, FAIL, "No invoice date supplied.", "a date", None)

	floor = add_days(nowdate(), -MAX_INVOICE_AGE_DAYS)
	if getdate(date) > getdate(nowdate()):
		return row("V-INT-07", STAGE, WARN, FAIL,
			"Invoice date is in the future.", f"<= {nowdate()}", date)
	if getdate(date) < getdate(floor):
		return row("V-INT-07", STAGE, WARN, FAIL,
			f"Invoice is older than {MAX_INVOICE_AGE_DAYS} days.", f">= {floor}", date)
	return row("V-INT-07", STAGE, WARN, PASS, "Invoice date within accepted window.", found=date)
