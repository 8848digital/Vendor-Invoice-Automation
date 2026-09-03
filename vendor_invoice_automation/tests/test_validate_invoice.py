# Copyright (c) 2026, 8848 Digital and Contributors
# For license information, please see license.txt

import json

import frappe
from frappe.tests import IntegrationTestCase

from vendor_invoice_automation.api.v1.invoice import validate_invoice
from vendor_invoice_automation.validations import DEFAULT_SEQUENCE

COMPANY = "_Test Company"
SUPPLIER = "_Test VIA Supplier"

# Real-format GSTINs with correct NIC check digits, so india_compliance's own
# validate_gstin accepts them.
SUPPLIER_GSTIN = "27AAACI1195H1ZM"  # PAN AAACI1195H, Maharashtra
COMPANY_GSTIN = "27AABCU9603R1ZN"  # PAN AABCU9603R, Maharashtra
OTHER_STATE_GSTIN = "29AAACI1195H1ZI"  # same PAN, Karnataka
OTHER_PAN_GSTIN = "27AAECS1234F1ZO"  # PAN AAECS1234F, Maharashtra


class TestValidateInvoice(IntegrationTestCase):
	"""IntegrationTestCase rolls the DB back at class teardown, so these fixtures are disposable."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# Create or repair — the supplier may survive from a run predating india_compliance.
		if frappe.db.exists("Supplier", SUPPLIER):
			sup = frappe.get_doc("Supplier", SUPPLIER)
		else:
			sup = frappe.new_doc("Supplier")
			sup.supplier_name = SUPPLIER
			sup.supplier_group = "All Supplier Groups"
		sup.gst_category = "Registered Regular"
		sup.gstin = SUPPLIER_GSTIN
		sup.on_hold = 0
		sup.save()
		assert sup.pan == "AAACI1195H", f"pan not derived from gstin: {sup.pan!r}"
		frappe.db.set_value("Company", COMPANY, "gstin", COMPANY_GSTIN)
		frappe.db.commit()

	def payload(self, **kw):
		"""A clean intra-state non-PO service invoice."""
		p = {
			"supplier": SUPPLIER,
			"company": COMPANY,
			"invoice_no": "TEST-VIA-001",
			"invoice_date": frappe.utils.nowdate(),
			"supplier_gstin": SUPPLIER_GSTIN,
			"company_gstin": COMPANY_GSTIN,
			"place_of_supply": "27-Maharashtra",
			"taxable_value": 10000,
			"cgst": 900,
			"sgst": 900,
			"igst": 0,
			"cess": 0,
			"round_off": 0,
			"grand_total": 11800,
			"declared": {"grand_total": 11800},
			"items": [{
				"description": "Annual maintenance",
				"hsn_sac": "998713",
				"qty": 1,
				"rate": 10000,
				"amount": 10000,
				"gst_rate": 18,
				"tax_amount": 1800,
			}],
		}
		p.update(kw)
		return p

	def check(self, **kw):
		"""Call the endpoint and return the inner result, asserting the envelope holds."""
		envelope = validate_invoice(self.payload(**kw))
		self.assertIn(envelope["status"], ("success", "error"))
		self.assertIn("timestamp", envelope)
		return envelope["data"]

	def failed(self, result):
		return set(result["failed"])

	# ---------------------------------------------------------------- envelope

	def test_response_is_wrapped_in_the_house_envelope(self):
		envelope = validate_invoice(self.payload())

		self.assertEqual(envelope["status"], "success")
		self.assertEqual(envelope["data"]["verdict"], "green")
		self.assertNotIn("error_code", envelope)

	def test_a_failing_invoice_reports_status_error(self):
		envelope = validate_invoice(self.payload(grand_total=99999))
		self.assertEqual(envelope["status"], "error")

	def test_malformed_json_is_a_bad_request_not_a_traceback(self):
		envelope = validate_invoice("{not json")

		self.assertEqual(envelope["status"], "error")
		self.assertEqual(envelope["error_code"], "BAD_REQUEST")

	def test_accepts_a_json_string_payload(self):
		self.assertTrue(validate_invoice(json.dumps(self.payload()))["data"]["ok"])

	# -------------------------------------------------------------------- gate

	def test_clean_non_po_invoice_passes(self):
		r = self.check()

		self.assertEqual(r["matching_mode"], "Non-PO")
		self.assertTrue(r["ok"], f"unexpected failures: {r['failed']}")
		self.assertEqual(r["verdict"], "green")
		self.assertTrue(r["auto_create_allowed"])

	def test_po_invoice_fails_closed_while_matching_is_unbuilt(self):
		r = self.check(po_number="PUR-ORD-DOES-NOT-MATTER")

		self.assertEqual(r["matching_mode"], "2-Way")
		self.assertFalse(r["auto_create_allowed"])
		self.assertIn("V-PO-PENDING", self.failed(r))

	def test_no_non_po_checks_are_emitted(self):
		"""The V-NPO-* family was removed; non-PO PIs are created independently."""
		self.assertEqual([c for c in self.check()["checks"] if c["check_id"].startswith("V-NPO")], [])

	def test_skipped_checks_are_reported_not_silently_passed(self):
		r = self.check()

		self.assertIn("V-FAKE-02", r["skipped"])
		self.assertIn("V-DUP-03", r["skipped"])
		self.assertNotIn("V-FAKE-02", r["failed"])

	def test_fraud_outranks_arithmetic_when_naming_the_exception(self):
		"""A forged GSTIN must not be reported as an OCR problem just because a
		total also failed in the same pass."""
		r = self.check(supplier_gstin=OTHER_STATE_GSTIN, place_of_supply="29-Karnataka",
			grand_total=99999)

		self.assertIn("V-FAKE-01", self.failed(r))
		self.assertIn("V-EXT-04", self.failed(r))
		self.assertEqual(r["exception_type"], "Fraud Suspected")

	# ------------------------------------------------- fraud / identity checks

	def test_gstin_not_the_suppliers_own_is_fraud(self):
		r = self.check(supplier_gstin=OTHER_STATE_GSTIN, place_of_supply="29-Karnataka")

		self.assertIn("V-FAKE-01", self.failed(r))
		self.assertEqual(r["exception_type"], "Fraud Suspected")
		self.assertFalse(r["auto_create_allowed"])

	def test_same_pan_different_state_does_not_trip_the_pan_check(self):
		"""V-FAKE-01 and V-FAKE-07 are not redundant: a sibling-state GSTIN shares the PAN."""
		r = self.check(supplier_gstin=OTHER_STATE_GSTIN, place_of_supply="29-Karnataka")

		self.assertIn("V-FAKE-01", self.failed(r))
		self.assertNotIn("V-FAKE-07", self.failed(r))

	def test_a_different_pan_entirely_trips_both_pan_checks(self):
		r = self.check(supplier_gstin=OTHER_PAN_GSTIN)

		self.assertIn("V-FAKE-07", self.failed(r))
		self.assertIn("V-GST-07", self.failed(r))

	def test_malformed_gstin_fails_india_compliance_validation(self):
		self.assertIn("V-GST-01/02", self.failed(self.check(supplier_gstin="27AAACI1195H1ZZ")))

	def test_unknown_gstin_status_is_skipped_never_failed(self):
		"""SPEC §8: unknown is not invalid. No GSTIN row means Skipped, not Fail."""
		r = self.check()

		self.assertIn("V-GST-03", r["skipped"])
		self.assertIn("V-GST-04a", r["skipped"])
		self.assertNotIn("V-GST-03", r["failed"])

	def test_gstin_cancelled_before_the_invoice_date_fails(self):
		"""V-GST-04a via india_compliance's own registration/cancellation comparison."""
		frappe.get_doc({
			"doctype": "GSTIN",
			"gstin": SUPPLIER_GSTIN,
			"status": "Cancelled",
			"registration_date": "2020-01-01",
			"cancelled_date": "2024-01-01",
		}).insert()
		try:
			r = self.check()
			self.assertIn("V-GST-04a", self.failed(r))
			self.assertIn("V-GST-03", self.failed(r))
			self.assertEqual(r["exception_type"], "Suspended GST")
		finally:
			frappe.delete_doc("GSTIN", SUPPLIER_GSTIN, force=1)

	def test_composition_supplier_may_not_charge_gst(self):
		frappe.db.set_value("Supplier", SUPPLIER, "gst_category", "Registered Composition")
		try:
			self.assertIn("V-GST-05", self.failed(self.check()))
		finally:
			frappe.db.set_value("Supplier", SUPPLIER, "gst_category", "Registered Regular")

	# --------------------------------------------------------------- arithmetic

	def test_cgst_and_igst_together_is_incoherent(self):
		self.assertIn("V-EXT-05", self.failed(
			self.check(cgst=900, sgst=900, igst=1800, grand_total=13600)))

	def test_header_total_is_recomputed_not_trusted(self):
		self.assertIn("V-EXT-04", self.failed(self.check(grand_total=99999)))

	def test_line_arithmetic_is_recomputed(self):
		bad = self.payload()
		bad["items"][0]["amount"] = 12345
		self.assertIn("V-EXT-03", set(validate_invoice(bad)["data"]["failed"]))

	def test_interstate_invoice_must_carry_igst(self):
		self.assertIn("V-GST-12/13", self.failed(self.check(place_of_supply="29-Karnataka")))

	def test_unreal_state_code_is_rejected(self):
		self.assertIn("V-GST-12/13", self.failed(self.check(place_of_supply="99-Nowhere")))

	def test_short_hsn_is_a_warning_not_a_block(self):
		bad = self.payload()
		bad["items"][0]["hsn_sac"] = "998"
		r = validate_invoice(bad)["data"]

		self.assertIn("V-EXT-08", self.failed(r))
		self.assertEqual(r["verdict"], "yellow")
		self.assertTrue(r["ok"])  # warnings do not clear `ok`

	# -------------------------------------------------------------- intake/misc

	def test_supplier_on_hold_is_rejected(self):
		frappe.db.set_value("Supplier", SUPPLIER, {"on_hold": 1, "hold_type": "All"})
		try:
			self.assertIn("V-INT-05", self.failed(self.check()))
		finally:
			frappe.db.set_value("Supplier", SUPPLIER, {"on_hold": 0, "hold_type": ""})

	def test_unknown_supplier_short_circuits_the_pipeline(self):
		r = validate_invoice(self.payload(supplier="No Such Supplier"))["data"]

		self.assertEqual(r["failed"], ["V-INT-04"])
		self.assertEqual(len(r["checks"]), 1)  # nothing downstream ran
		self.assertIsNone(r["matching_mode"])

	def test_buyer_gstin_must_belong_to_the_company(self):
		self.assertIn("V-EXT-10", self.failed(self.check(company_gstin=OTHER_STATE_GSTIN)))

	# ------------------------------------------------------------------ blocks

	def test_a_single_block_runs_alone(self):
		r = validate_invoice(self.payload(), ["intake"])["data"]

		self.assertTrue(all(c["stage"] == "intake" for c in r["checks"]))

	def test_blocks_run_in_the_order_given(self):
		r = validate_invoice(self.payload(), "gst,intake")["data"]
		stages = [c["stage"] for c in r["checks"]]

		self.assertEqual(stages, sorted(stages, key=lambda s: ["gst", "intake"].index(s)))

	def test_matching_routes_itself_when_stacked_alone(self):
		r = validate_invoice(self.payload(po_number="PO-X"), ["matching"])["data"]

		self.assertEqual(r["matching_mode"], "2-Way")
		self.assertIn("V-PO-PENDING", r["failed"])

	def test_unknown_block_is_a_bad_request_not_a_traceback(self):
		envelope = validate_invoice(self.payload(), ["nope"])

		self.assertEqual(envelope["error_code"], "BAD_REQUEST")

	def test_omitting_blocks_runs_the_full_sequence(self):
		self.assertEqual(self.check()["checks"], validate_invoice(
			self.payload(), list(DEFAULT_SEQUENCE))["data"]["checks"])


class TestToleranceAgainstERPNextSettings(IntegrationTestCase):
	"""V-PO-10/11/12 read ERPNext's own limits, so these fixtures set the ERPNext
	settings — not a tolerance doctype of ours."""

	ITEM = "_Test VIA Item"
	ORDERED_RATE = 100.0
	ORDERED_QTY = 10

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Supplier", SUPPLIER):
			frappe.get_doc({"doctype": "Supplier", "supplier_name": SUPPLIER,
				"supplier_group": "All Supplier Groups"}).insert()
		if not frappe.db.exists("Item", cls.ITEM):
			frappe.get_doc({"doctype": "Item", "item_code": cls.ITEM, "item_name": cls.ITEM,
				"item_group": "All Item Groups", "is_stock_item": 0,
				"stock_uom": "Nos", "gst_hsn_code": "998713"}).insert()

		po = frappe.get_doc({
			"doctype": "Purchase Order",
			"supplier": SUPPLIER,
			"company": COMPANY,
			"transaction_date": frappe.utils.nowdate(),
			"schedule_date": frappe.utils.nowdate(),
			"items": [{"item_code": cls.ITEM, "qty": cls.ORDERED_QTY, "rate": cls.ORDERED_RATE,
				"schedule_date": frappe.utils.nowdate()}],
		}).insert()
		po.submit()
		cls.po = po.name
		frappe.db.commit()

	def tolerance_rows(self, rate, amount, **settings):
		"""Run just the tolerance block against the fixture PO."""
		for doctype, values in settings.items():
			frappe.db.set_value(doctype.replace("_", " ").title(), None, values)
			frappe.clear_cache(doctype=doctype.replace("_", " ").title())

		payload = {
			"supplier": SUPPLIER, "company": COMPANY, "po_number": self.po,
			"items": [{"item_code": self.ITEM, "qty": self.ORDERED_QTY,
				"rate": rate, "amount": amount}],
		}
		rows = validate_invoice(payload, ["tolerance"])["data"]["checks"]
		return {r["check_id"]: r for r in rows}

	def test_rate_and_amount_matching_the_order_pass(self):
		rows = self.tolerance_rows(self.ORDERED_RATE, self.ORDERED_RATE * self.ORDERED_QTY,
			buying_settings={"maintain_same_rate": 1, "maintain_same_rate_action": "Stop"},
			accounts_settings={"over_billing_allowance": 0})

		self.assertEqual(rows["V-PO-11"]["result"], "Pass")
		self.assertEqual(rows["V-PO-12"]["result"], "Pass")
		self.assertEqual(rows["V-PO-10"]["result"], "Skipped")

	def test_a_moved_rate_fails_only_while_erpnext_would_stop_it(self):
		blocked = self.tolerance_rows(self.ORDERED_RATE + 5, self.ORDERED_RATE * self.ORDERED_QTY,
			buying_settings={"maintain_same_rate": 1, "maintain_same_rate_action": "Stop"})
		self.assertEqual(blocked["V-PO-11"]["result"], "Fail")
		self.assertEqual(blocked["V-PO-11"]["severity"], "Error")

		warned = self.tolerance_rows(self.ORDERED_RATE + 5, self.ORDERED_RATE * self.ORDERED_QTY,
			buying_settings={"maintain_same_rate_action": "Warn"})
		self.assertEqual(warned["V-PO-11"]["severity"], "Warning")

		off = self.tolerance_rows(self.ORDERED_RATE + 5, self.ORDERED_RATE * self.ORDERED_QTY,
			buying_settings={"maintain_same_rate": 0})
		self.assertEqual(off["V-PO-11"]["result"], "Pass")

	def test_over_billing_is_measured_against_the_erpnext_allowance(self):
		ordered = self.ORDERED_RATE * self.ORDERED_QTY

		self.assertEqual(self.tolerance_rows(self.ORDERED_RATE, ordered * 1.05,
			accounts_settings={"over_billing_allowance": 0})["V-PO-12"]["result"], "Fail")

		self.assertEqual(self.tolerance_rows(self.ORDERED_RATE, ordered * 1.05,
			accounts_settings={"over_billing_allowance": 10})["V-PO-12"]["result"], "Pass")

	def test_an_item_level_allowance_overrides_the_global_one(self):
		ordered = self.ORDERED_RATE * self.ORDERED_QTY
		frappe.db.set_value("Item", self.ITEM, "over_billing_allowance", 20)
		frappe.clear_cache(doctype="Item")
		try:
			self.assertEqual(self.tolerance_rows(self.ORDERED_RATE, ordered * 1.15,
				accounts_settings={"over_billing_allowance": 0})["V-PO-12"]["result"], "Pass")
		finally:
			frappe.db.set_value("Item", self.ITEM, "over_billing_allowance", 0)
			frappe.clear_cache(doctype="Item")

	def test_non_po_invoices_emit_no_tolerance_rows(self):
		payload = {"supplier": SUPPLIER, "company": COMPANY, "items": []}
		self.assertEqual(validate_invoice(payload, ["tolerance"])["data"]["checks"], [])
