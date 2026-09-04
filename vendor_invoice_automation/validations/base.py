"""Shared primitives for every validation module: the audit row, the severity and
result vocabularies, and the tunables.

Nothing here touches the database. Nothing in `validations/` does any more: every
comparison value now arrives in the request as `context`, assembled by the caller on its
own site. See CONTEXT.md for the contract.
"""

PASS, FAIL, SKIP = "Pass", "Fail", "Skipped"
INFO, WARN, ERROR = "Info", "Warning", "Error"

# ponytail: constants, not a Settings DocType — the API is stateless and stores nothing.
# Move to a Single doctype when someone actually needs to tune these per site.
MAX_INVOICE_AGE_DAYS = 180
MONETARY_AGREEMENT_TOLERANCE = 1.0
AUTO_CREATE_ON_YELLOW = False


def nic_public_certificate():
	"""NIC's public certificate (PEM), for verifying signed e-invoice QR codes.

	The one tunable that is not a constant: it is per-deployment and belongs in
	`site_config.json` as `via_nic_public_certificate`, never in source. Absent is a
	normal state — V-FAKE-02 reports Skipped rather than passing.
	"""
	import frappe

	return (frappe.conf.get("via_nic_public_certificate") or "").strip()


class _Unset:
	"""Sentinel for "the caller did not supply this context key".

	The distinction this exists to preserve: `context["supplier"] = None` means the caller
	looked and found no Supplier — a real V-INT-04 failure. A *missing* `supplier` key means
	the caller never looked, which is Skipped. Collapsing the two would turn "I could not
	fetch it" into "it does not exist", and red-flag every invoice a caller under-populated.
	"""

	def __repr__(self):
		return "UNSET"


UNSET = _Unset()


def unchecked(check_id, stage, severity, key):
	"""A check that could not run because its context key was not supplied.

	Skipped, never Fail — and `decision.gate` suppresses `auto_create_allowed` when an
	Error-severity check is Skipped, so an under-populated context can never read as clean.
	"""
	r = row(check_id, stage, severity, SKIP,
		f"No `context.{key}` supplied; this check did not run.", f"context.{key}", None)
	# The flag, not the severity, is what `decision.gate` keys on. A Skipped Error row is
	# not automatically a missing-context row: V-GST-03 (status unknown, SPEC §8) and
	# V-FAKE-02 (no NIC certificate) are legitimately Skipped on a fully-populated request,
	# and treating those as "unrun" would suppress auto-creation on nearly every invoice.
	r["unrun"] = True
	return r


def row(check_id, stage, severity, result, message="", expected=None, found=None):
	"""One audit row. `expected`/`found` are stringified so the response is JSON-safe
	whatever the caller passed in."""
	return {
		"check_id": check_id,
		"stage": stage,
		"severity": severity,
		"result": result,
		"expected": None if expected is None else str(expected),
		"found": None if found is None else str(found),
		"message": message,
		# True only on rows from `unchecked()` — the check could not run because the
		# caller did not supply its context key. Kept on every row so the response shape
		# stays uniform for consumers.
		"unrun": False,
	}


def verdict(ok):
	"""A check that ran: Pass or Fail. Never use this for a check that could not run —
	that is SKIP, and the distinction is the point (see VALIDATION_API_MAP.md §2)."""
	return PASS if ok else FAIL
