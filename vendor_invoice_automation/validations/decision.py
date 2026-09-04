"""Stage 6 — Decision gate. SPEC §5.

Turns the audit rows into the one boolean a caller acts on: `auto_create_allowed`.
"""

from .base import AUTO_CREATE_ON_YELLOW, ERROR, FAIL, SKIP, WARN

# Which exception_type a failed check maps to. Ordered most specific first, and
# severity-ranked: a forged GSTIN must not be reported as an OCR problem just because
# an arithmetic check happened to fail in the same pass.
EXCEPTION_BY_CHECK = (
	("V-FAKE", "Fraud Suspected"),
	("V-DUP-01", "Duplicate"),
	("V-DUP-02", "Duplicate"),
	("V-DUP", "Suspected Duplicate"),
	("V-GST-08", "Fraud Suspected"),
	("V-GST-09", "Fraud Suspected"),
	("V-GST-10", "Fraud Suspected"),
	("V-GST-03", "Suspended GST"),
	("V-GST-04a", "Suspended GST"),
	("V-GST-01/02", "Invalid GSTIN"),
	("V-GST-07", "Invalid GSTIN"),
	("V-GST-12/13", "Invalid Tax"),
	("V-GST-15", "Invalid Tax"),
	("V-GST-14", "Invalid HSN"),
	("V-GST-16", "2B Unavailable"),
	("V-GST-17", "Return Not Filed"),
	("V-GRN-02", "Missing GRN"),
	("V-GRN-05", "GRN Mismatch"),
	("V-GRN-07", "Qty Mismatch"),
	("V-GRN-09", "UOM Mismatch"),
	("V-GRN-10", "Qty Mismatch"),
	("V-GRN-11", "Price Mismatch"),
	("V-GRN-12", "Price Mismatch"),
	("V-GRN", "GRN Mismatch"),
	("V-PO-01", "Missing PO"),
	("V-PO-03", "Missing PO"),
	("V-PO-07", "Item Not On PO"),
	("V-PO-09", "UOM Mismatch"),
	("V-PO-10", "Qty Mismatch"),
	("V-PO-11", "Price Mismatch"),
	("V-PO-12", "Price Mismatch"),
	("V-PO", "Missing PO"),
	("V-ITC", "ITC Unavailable"),
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


def gate(rows, mode, partial=False):
	"""The response body, minus `checks`.

	`unrun` is the load-bearing addition. Every comparison value now arrives as `context`
	the caller assembled, and a caller that supplies none produces zero failures — which
	without this would read as `verdict: green, auto_create_allowed: true`, i.e. an empty
	request looking like a flawless invoice. The same hole opens whenever a single block is
	run on its own, since every other block is then unrun.

	`partial` closes the same hole from the other side. `unrun` can only count checks that
	produced a row, so a caller running one block gets an empty `unrun` — every other block
	emitted nothing at all rather than emitting a Skipped row. A per-block caller must
	still never see `auto_create_allowed: true`, so a subset of the sequence suppresses it
	outright.

	`unrun` counts only rows flagged by `base.unchecked` — a check whose *context key was
	not supplied*. It deliberately does not count every Skipped Error row: V-GST-03 (status
	unknown is not invalid, SPEC §8) and V-FAKE-02 (no NIC certificate) are Skipped even on
	a fully-populated request, and treating those as unrun would suppress auto-creation on
	essentially every invoice.

	So a blocking check that never ran suppresses auto-creation. The verdict itself stays
	green — nothing failed, and calling it red would be its own lie — but nothing may be
	created on the strength of checks that did not happen.
	"""
	failed = [r["check_id"] for r in rows if r["result"] == FAIL]
	skipped = [r["check_id"] for r in rows if r["result"] == SKIP]
	errors = [r["check_id"] for r in rows if r["result"] == FAIL and r["severity"] == ERROR]
	warnings = [r["check_id"] for r in rows if r["result"] == FAIL and r["severity"] == WARN]
	# Only missing-context skips, not every Skipped Error row — see base.unchecked.
	unrun = [r["check_id"] for r in rows if r.get("unrun") and r["severity"] == ERROR]

	if errors:
		verdict = "red"
	elif warnings:
		verdict = "yellow"
	else:
		verdict = "green"

	allowed = (
		(verdict == "green" or (verdict == "yellow" and AUTO_CREATE_ON_YELLOW))
		and not unrun
		and not partial
	)

	return {
		"ok": not errors,
		"verdict": verdict,
		"auto_create_allowed": allowed,
		"review_required": verdict != "green" or bool(unrun) or partial,
		"matching_mode": mode,
		"exception_type": exception_type(errors or warnings),
		"failed": failed,
		"skipped": skipped,
		"unrun": unrun,
		"partial": partial,
	}
