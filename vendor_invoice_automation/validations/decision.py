"""Stage 6 — Decision gate. SPEC §5.

Turns the audit rows into the one boolean a caller acts on: `auto_create_allowed`.
"""

from .base import AUTO_CREATE_ON_YELLOW, ERROR, FAIL, SKIP, WARN

# Which exception_type a failed check maps to. Ordered most specific first, and
# severity-ranked: a forged GSTIN must not be reported as an OCR problem just because
# an arithmetic check happened to fail in the same pass.
EXCEPTION_BY_CHECK = (
	("V-FAKE", "Fraud Suspected"),
	("V-DUP", "Duplicate"),
	("V-GST-03", "Suspended GST"),
	("V-GST-04a", "Suspended GST"),
	("V-GST-01/02", "Invalid GSTIN"),
	("V-GST-07", "Invalid GSTIN"),
	("V-GST-12/13", "Invalid Tax"),
	("V-GST-14", "Invalid HSN"),
	("V-GST-16", "2B Unavailable"),
	("V-PO-10", "Qty Mismatch"),
	("V-PO-11", "Price Mismatch"),
	("V-PO-12", "Price Mismatch"),
	("V-PO", "Missing PO"),
	("V-GRN", "Missing GRN"),
	("V-EXT-08", "Invalid HSN"),
	("V-EXT", "OCR Failure"),
	("V-INT", "Intake Failed"),
)


def exception_type(failed_ids):
	"""The first match in EXCEPTION_BY_CHECK order, not in failure order — so the most
	serious cause names the exception."""
	for prefix, exc in EXCEPTION_BY_CHECK:
		if any(check_id.startswith(prefix) for check_id in failed_ids):
			return exc
	return None


def gate(rows, mode):
	"""The response body, minus `checks`."""
	failed = [r["check_id"] for r in rows if r["result"] == FAIL]
	skipped = [r["check_id"] for r in rows if r["result"] == SKIP]
	errors = [r["check_id"] for r in rows if r["result"] == FAIL and r["severity"] == ERROR]
	warnings = [r["check_id"] for r in rows if r["result"] == FAIL and r["severity"] == WARN]

	if errors:
		verdict = "red"
	elif warnings:
		verdict = "yellow"
	else:
		verdict = "green"

	allowed = verdict == "green" or (verdict == "yellow" and AUTO_CREATE_ON_YELLOW)

	return {
		"ok": not errors,
		"verdict": verdict,
		"auto_create_allowed": allowed,
		"review_required": verdict != "green",
		"matching_mode": mode,
		"exception_type": exception_type(errors or warnings),
		"failed": failed,
		"skipped": skipped,
	}
