"""From check rows to what a person acts on: OCR confidence, the BRD status, and whether a
Draft Purchase Invoice may be created."""

from vendor_invoice_automation.validations.base import ERROR, FAIL, row
from vendor_invoice_automation.validations.routing import NON_PO, PO_MODES, THREE_WAY, UNKNOWN

AUTO, REVIEW, MANUAL = "auto", "review", "manual"

REQUIRED = ("supplier_gstin", "invoice_no", "invoice_date", "taxable_value", "grand_total", "items")

# check → (weight, the fields a failure casts doubt on)
SIGNALS = (
	("V-EXT-03", 20, ["items.qty", "items.rate", "items.amount"]),
	("V-EXT-04", 20, ["taxable_value", "cgst", "sgst", "igst", "cess", "grand_total"]),
	("V-GST-01/02", 10, ["supplier_gstin"]),
	("V-EXT-05", 10, ["cgst", "sgst", "igst"]),
)


def confidence(p, rows, method):
	"""(score 0-100, band, uncertain_fields).

	An LLM gives no calibrated percentage, so the score counts evidence the transcription is
	right: required fields present (40), arithmetic that ties out (40), a well-formed GSTIN
	and tax split (20). A signed source is ground truth. A QR that disagrees with the page
	caps the score, since one of the two was misread or altered.
	"""
	if method == "E-Invoice JSON":
		return 100.0, AUTO, []

	by_id = {r["check_id"]: r for r in rows}
	failed = lambda cid: (by_id.get(cid) or {}).get("result") == FAIL  # noqa: E731

	missing = [f for f in REQUIRED if not p.get(f)]
	uncertain = list(missing)
	score = 40 * (1 - len(missing) / len(REQUIRED))
	for cid, weight, fields in SIGNALS:
		if failed(cid):
			uncertain += fields
		else:
			score += weight

	if failed("V-FAKE-04"):
		score = min(score, 80)
		uncertain += ["invoice_no", "invoice_date", "grand_total"]
	elif method == "QR" and by_id.get("V-FAKE-04", {}).get("result") == "Pass" and not missing:
		score = max(score, 95)

	score = round(score, 1)
	band = AUTO if score >= 95 else REVIEW if score >= 90 else MANUAL
	return score, band, list(dict.fromkeys(uncertain))


def duplicate_upload_rows(file_hash, qr_hash, existing):
	"""V-DUP-06 / V-DUP-05 — the same file or the same signed QR already arrived.

	`existing` maps field → the Document Intake already holding that hash (or None). Only
	emitted when there is a hash to compare, matching duplicate.py's IRN rule.
	"""
	out = []
	for check_id, field, value, what in (
		("V-DUP-06", "file_hash", file_hash, "file"),
		("V-DUP-05", "qr_hash", qr_hash, "signed QR"),
	):
		if not value:
			continue
		hit = existing.get(field)
		out.append(row(check_id, "duplicate", ERROR, FAIL if hit else "Pass",
			f"The same {what} was already uploaded as {hit}." if hit
			else f"This {what} has not been uploaded before.",
			f"a new {what}", hit))
	return out


def status(result, band):
	"""(status, exception_type) from BRD §16, in pipeline order: the earliest stage that
	failed names the status, so a forged invoice never reads as a PO problem."""
	checks = result["checks"]
	errors = [r for r in checks if r["result"] == FAIL and r["severity"] == ERROR]
	exception = result.get("exception_type")
	mode = result.get("matching_mode")

	if band == MANUAL:
		return "OCR Failed", "OCR Failure"
	if any(r["check_id"].startswith(("V-DUP-01", "V-DUP-02", "V-DUP-05", "V-DUP-06", "V-DUP-08")) for r in errors):
		return "Duplicate", "Duplicate"
	if any(r["stage"] not in ("po_matching", "grn_matching") for r in errors):
		return "GST Failed", exception
	if mode == NON_PO:
		return "PO Failed", "Missing PO"
	if mode == UNKNOWN:
		return "PO Failed", "Item Not On PO"
	if any(r["stage"] == "po_matching" for r in errors):
		return "PO Failed", exception
	if any(r["stage"] == "grn_matching" for r in errors):
		return "GRN Failed", exception
	if result.get("unrun"):
		return "GST Validation", None
	return ("GRN Matched" if mode == THREE_WAY else "PO Matched"), (exception if result["verdict"] == "yellow" else None)


def may_create_purchase_invoice(result, band, state):
	"""Green or yellow, fully run, PO-backed, and the extraction trusted. Yellow still
	creates — flagged for Buyer Review — per the agreed plan."""
	return (
		state in ("PO Matched", "GRN Matched")
		and result["verdict"] in ("green", "yellow")
		and not result.get("unrun")
		and result.get("matching_mode") in PO_MODES
		and band != MANUAL
	)
