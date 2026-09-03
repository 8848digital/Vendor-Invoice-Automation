"""Shared primitives for every validation module: the audit row, the severity and
result vocabularies, and the tunables.

Nothing here touches the database.
"""

PASS, FAIL, SKIP = "Pass", "Fail", "Skipped"
INFO, WARN, ERROR = "Info", "Warning", "Error"

# ponytail: constants, not a Settings DocType — the API is stateless and stores nothing.
# Move to a Single doctype when someone actually needs to tune these per site.
MAX_INVOICE_AGE_DAYS = 180
MONETARY_AGREEMENT_TOLERANCE = 1.0
AUTO_CREATE_ON_YELLOW = False


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
	}


def verdict(ok):
	"""A check that ran: Pass or Fail. Never use this for a check that could not run —
	that is SKIP, and the distinction is the point (see VALIDATION_API_MAP.md §2)."""
	return PASS if ok else FAIL
