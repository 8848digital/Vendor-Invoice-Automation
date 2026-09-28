"""The pure decisions behind Document Intake: confidence band, BRD status, PI eligibility, and
the NIC e-invoice JSON reader. No database — the end-to-end flow needs POs and receipts."""

from frappe.tests import UnitTestCase

from vendor_invoice_automation.intake import files, outcome
from vendor_invoice_automation.validations.base import ERROR, FAIL, PASS, WARN, row


def result(rows, mode="3-Way", verdict="green", unrun=()):
	return {"checks": rows, "matching_mode": mode, "verdict": verdict, "unrun": list(unrun),
		"exception_type": "X"}


INVOICE = {"supplier_gstin": "27AAACI1195H1ZM", "invoice_no": "1", "invoice_date": "2026-09-01",
	"taxable_value": 100, "grand_total": 118, "items": [{}]}


class TestIntakeOutcome(UnitTestCase):
	def test_confidence_bands(self):
		self.assertEqual(outcome.confidence(INVOICE, [], "LLM")[:2], (100.0, outcome.AUTO))
		# one required field missing → review, and that field is named
		score, band, uncertain = outcome.confidence({**INVOICE, "invoice_no": None}, [], "LLM")
		self.assertEqual((band, uncertain), (outcome.REVIEW, ["invoice_no"]))
		# broken header arithmetic on top → manual
		rows = [row("V-EXT-04", "extraction", ERROR, FAIL)]
		self.assertEqual(outcome.confidence({**INVOICE, "invoice_no": None}, rows, "LLM")[1], outcome.MANUAL)
		self.assertEqual(outcome.confidence({}, rows, "E-Invoice JSON")[:2], (100.0, outcome.AUTO))

	def test_status_takes_the_earliest_failure(self):
		gst = row("V-GST-03", "gst", ERROR, FAIL)
		grn = row("V-GRN-02", "grn_matching", ERROR, FAIL)
		dup = row("V-DUP-01", "duplicate", ERROR, FAIL)
		self.assertEqual(outcome.status(result([grn, gst, dup]), outcome.AUTO)[0], "Duplicate")
		self.assertEqual(outcome.status(result([grn, gst]), outcome.AUTO)[0], "GST Failed")
		self.assertEqual(outcome.status(result([grn]), outcome.AUTO)[0], "GRN Failed")
		self.assertEqual(outcome.status(result([gst]), outcome.MANUAL)[0], "OCR Failed")
		self.assertEqual(outcome.status(result([], mode="Non-PO"), outcome.AUTO), ("PO Failed", "Missing PO"))
		self.assertEqual(outcome.status(result([], mode="2-Way"), outcome.AUTO)[0], "PO Matched")

	def test_purchase_invoice_only_when_matched_and_trusted(self):
		ok = result([row("V-PO-10", "po_matching", WARN, FAIL)], verdict="yellow")
		self.assertTrue(outcome.may_create_purchase_invoice(ok, outcome.AUTO, "GRN Matched"))
		self.assertFalse(outcome.may_create_purchase_invoice(ok, outcome.MANUAL, "GRN Matched"))
		self.assertFalse(outcome.may_create_purchase_invoice(result([], mode="Non-PO"), outcome.AUTO, "PO Failed"))
		self.assertFalse(outcome.may_create_purchase_invoice(result([], unrun=["V-X"]), outcome.AUTO, "GRN Matched"))

	def test_duplicate_upload_rows(self):
		rows = outcome.duplicate_upload_rows("f", None, {"file_hash": "DI-1"})
		self.assertEqual([(r["check_id"], r["result"]) for r in rows], [("V-DUP-06", FAIL)])
		self.assertEqual(outcome.duplicate_upload_rows("f", "q", {})[1]["result"], PASS)

	def test_einvoice_json_dates_are_day_first(self):
		p = files.parse_einvoice({"DocDtls": {"No": "A1", "Dt": "05/09/2026"}, "BuyerDtls": {"Pos": "27"},
			"ValDtls": {"TotInvVal": 118}, "ItemList": [{"Qty": 2, "UnitPrice": 50, "TotAmt": 100}]})
		self.assertEqual((p["invoice_date"], p["place_of_supply"], p["items"][0]["amount"]),
			("2026-09-05", "27-Maharashtra", 100.0))


class TestIntakeSkillsCallSite(UnitTestCase):
	"""The intake skills name our methods by dotted path; a rename would break them silently."""

	def test_intake_skills_name_whitelisted_methods(self):
		import inspect
		import re
		from pathlib import Path

		import frappe

		calls = []
		for f in (Path(__file__).parents[2] / "skills").glob("intake-*.md"):
			calls += [(f.name, *m.groups()) for m in re.finditer(
				r"method:\s*(vendor_invoice_automation\.\S+)\s*\n\s*args:\s*(\{.*?\})\n", f.read_text())]
		self.assertTrue(calls)
		for fname, method, args in calls:
			fn = frappe.get_attr(method)
			frappe.is_whitelisted(fn)
			for key in re.findall(r'"(\w+)":', args):
				self.assertIn(key, inspect.signature(fn).parameters, f"{fname}: {method} takes no `{key}`")
