"""Stage 0 — Intake. SPEC §5.

V-INT-01/02/03 are the caller's: they need the file itself, which this API never sees.

The Supplier master arrives as `context["supplier"]`; this module never reads a database.
Absent key → Skipped; `None` → the Supplier genuinely does not exist, which is V-INT-04.
"""

from frappe.utils import add_days, getdate, nowdate

from .base import ERROR, FAIL, MAX_INVOICE_AGE_DAYS, PASS, UNSET, WARN, row, unchecked, verdict

STAGE = "intake"


def run(p, c):
	"""Returns audit rows. If V-INT-04 fails the pipeline stops — see `pipeline._intake`."""
	sup = c.get("supplier", UNSET)

	if sup is UNSET:
		# The caller never looked, so nothing here can be judged — not even the age check's
		# siblings. V-INT-07 is pure, so it still runs.
		return [
			unchecked("V-INT-04", STAGE, ERROR, "supplier"),
			unchecked("V-INT-05", STAGE, ERROR, "supplier"),
			unchecked("V-INT-06", STAGE, ERROR, "supplier"),
			_invoice_age(p),
		]

	if not sup:
		return [row("V-INT-04", STAGE, ERROR, FAIL,
			"Uploader/context did not resolve to exactly one Supplier.", "1 Supplier",
			p.get("supplier"))]

	return [
		row("V-INT-04", STAGE, ERROR, PASS, "Supplier resolved.",
			found=sup.get("name") or p.get("supplier")),
		_supplier_active(sup),
		_supplier_identified(sup),
		_invoice_age(p),
	]


def _supplier_active(sup):
	"""V-INT-05: a released hold is not a hold."""
	release_date = sup.get("release_date")
	released = release_date and getdate(release_date) <= getdate()
	blocked = sup.get("disabled") or (sup.get("on_hold") and not released)
	return row("V-INT-05", STAGE, ERROR, verdict(not blocked),
		"Supplier disabled or on hold." if blocked else "Supplier active.",
		"enabled, not on hold",
		f"disabled={sup.get('disabled')} on_hold={sup.get('on_hold')} "
		f"hold_type={sup.get('hold_type')}")


def _supplier_identified(sup):
	"""V-INT-06: GSTIN and PAN on the master, both real fields under india_compliance."""
	ok = bool(sup.get("gstin") and sup.get("pan"))
	return row("V-INT-06", STAGE, ERROR, verdict(ok),
		"Supplier master carries both a GSTIN and a PAN." if ok
		else "Supplier master is missing a GSTIN or PAN.",
		"GSTIN + PAN on file", f"gstin={sup.get('gstin')} pan={sup.get('pan')}")


def _invoice_age(p):
	"""V-INT-07: not in the future, not older than the configured window. Pure."""
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
