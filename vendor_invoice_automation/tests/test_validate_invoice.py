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

	def test_po_invoice_against_a_missing_order_fails_closed(self):
		"""An order ERPNext cannot invoice must never come back auto-createable."""
		r = self.check(po_number="PUR-ORD-DOES-NOT-EXIST")

		self.assertEqual(r["matching_mode"], "2-Way")
		self.assertFalse(r["auto_create_allowed"])
		self.assertIn("V-PO-01", self.failed(r))
		self.assertEqual(r["exception_type"], "Missing PO")

	def test_no_non_po_checks_are_emitted(self):
		"""The V-NPO-* family was removed; non-PO PIs are created independently."""
		self.assertEqual([c for c in self.check()["checks"] if c["check_id"].startswith("V-NPO")], [])

	def test_skipped_checks_are_reported_not_silently_passed(self):
		r = self.check()

		self.assertIn("V-FAKE-02", r["skipped"])
		self.assertNotIn("V-FAKE-02", r["failed"])
		# ...and a skip stands for exactly one cause, not one row per dependent check.
		self.assertEqual(r["skipped"], ["V-FAKE-02", "V-GST-03"], "skips should stay minimal")

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
		self.assertIn("V-GST-04a", next(
			c["message"] for c in r["checks"] if c["check_id"] == "V-GST-03"),
			"the collapsed row must still name the check it stands for")
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
		r = validate_invoice(self.payload(po_number="PO-X"), ["po_match"])["data"]

		self.assertEqual(r["matching_mode"], "2-Way")
		self.assertIn("V-PO-01", r["failed"])

	def test_unknown_block_is_a_bad_request_not_a_traceback(self):
		envelope = validate_invoice(self.payload(), ["nope"])

		self.assertEqual(envelope["error_code"], "BAD_REQUEST")

	def test_omitting_blocks_runs_the_full_sequence(self):
		self.assertEqual(self.check()["checks"], validate_invoice(
			self.payload(), list(DEFAULT_SEQUENCE))["data"]["checks"])


class TestDuplicate(IntegrationTestCase):
	"""Requirement 7. The composite key is GSTIN + invoice no + date + amount, and a
	partial match is a different answer from a full one."""

	AMOUNT = 1180.0
	DATE = "2026-01-15"

	def setUp(self):
		# IntegrationTestCase rolls back once per class, not per test, and these rows are
		# written with db_insert. A bill number per test keeps them from colliding.
		self.BILL_NO = f"DUP-{self._testMethodName[:40]}"

	def rows(self, **overrides):
		payload = {
			"supplier": SUPPLIER, "supplier_gstin": SUPPLIER_GSTIN,
			"invoice_no": self.BILL_NO, "invoice_date": self.DATE, "grand_total": self.AMOUNT,
		}
		payload.update(overrides)
		return {c["check_id"]: c for c in validate_invoice(payload, ["duplicate"])["data"]["checks"]}

	def book(self, **overrides):
		"""A Purchase Invoice row written straight to the table — this block only ever
		reads it back, and a full insert drags in accounts we do not need."""
		values = {
			"doctype": "Purchase Invoice", "name": f"PINV-DUP-{frappe.generate_hash(length=6)}",
			"supplier": SUPPLIER, "supplier_gstin": SUPPLIER_GSTIN, "company": COMPANY,
			"bill_no": self.BILL_NO, "bill_date": self.DATE, "grand_total": self.AMOUNT,
			"docstatus": 1,
		}
		values.update(overrides)
		doc = frappe.get_doc(values)
		doc.db_insert()
		return doc.name

	def test_an_unseen_invoice_is_not_a_duplicate(self):
		self.assertEqual(self.rows()["V-DUP-01"]["result"], "Pass")

	def test_all_four_fields_matching_is_a_duplicate(self):
		booked = self.book()
		row = self.rows()["V-DUP-01"]

		self.assertEqual(row["result"], "Fail")
		self.assertIn(booked, row["found"])

	def test_a_cancelled_invoice_still_counts(self):
		"""Cancelling a duplicate does not make re-uploading it legitimate."""
		self.book(docstatus=2)

		self.assertEqual(self.rows()["V-DUP-01"]["result"], "Fail")

	def test_same_number_different_amount_is_a_warning_not_a_rejection(self):
		self.book(grand_total=self.AMOUNT + 100)
		rows = self.rows()

		self.assertEqual(rows["V-DUP-01"]["result"], "Pass")
		self.assertEqual(rows["V-DUP-07"]["result"], "Fail")
		self.assertEqual(rows["V-DUP-07"]["severity"], "Warning")
		self.assertIn("amount", rows["V-DUP-07"]["found"])

	def test_same_number_different_date_is_reported_as_such(self):
		self.book(bill_date="2026-02-20")
		rows = self.rows()

		self.assertEqual(rows["V-DUP-01"]["result"], "Pass")
		self.assertIn("invoice_date", rows["V-DUP-07"]["found"])

	def test_no_party_to_dedupe_on_is_skipped_not_passed(self):
		rows = self.rows(supplier=None, supplier_gstin=None)

		self.assertEqual(rows["V-DUP-01"]["result"], "Skipped")

	def test_unbuilt_layers_emit_no_row_at_all(self):
		"""QR and file-hash dedup (V-DUP-05/06) are held by decision. A Skipped row
		repeating that in every response is a constant, not information — the decision
		lives in VALIDATION_API_MAP.md. Absent is not Pass: neither appears anywhere."""
		result = validate_invoice({
			"supplier": SUPPLIER, "supplier_gstin": SUPPLIER_GSTIN,
			"invoice_no": self.BILL_NO, "invoice_date": self.DATE, "grand_total": self.AMOUNT,
		}, ["duplicate"])["data"]

		for check_id in ("V-DUP-05", "V-DUP-06"):
			self.assertNotIn(check_id, [c["check_id"] for c in result["checks"]])
			self.assertNotIn(check_id, result["skipped"])
			self.assertNotIn(check_id, result["failed"])

	def test_the_irn_layer_is_quiet_when_there_is_no_irn(self):
		self.assertNotIn("V-DUP-02", [c["check_id"] for c in validate_invoice(
			{"supplier": SUPPLIER, "invoice_no": self.BILL_NO}, ["duplicate"]
		)["data"]["checks"]])


class TestEInvoiceQR(IntegrationTestCase):
	"""Requirement 8 — IRN Valid / QR Valid / GST Number Match, offline."""

	def rows(self, **overrides):
		payload = {
			"supplier": SUPPLIER, "supplier_gstin": SUPPLIER_GSTIN,
			"company_gstin": COMPANY_GSTIN, "invoice_no": "EINV-1",
			"invoice_date": "2026-01-15", "grand_total": 1180.0,
		}
		payload.update(overrides)
		return {c["check_id"]: c for c in validate_invoice(payload, ["einvoice"])["data"]["checks"]}

	@staticmethod
	def signed(**overrides):
		"""An unsigned JWS shaped like NIC's. Enough to exercise decoding and the field
		cross-checks; signature verification needs NIC's certificate and is skipped
		without it, which is itself asserted below."""
		import jwt

		data = {
			"SellerGstin": SUPPLIER_GSTIN, "BuyerGstin": COMPANY_GSTIN,
			"DocNo": "EINV-1", "DocTyp": "INV", "DocDt": "15/01/2026",
			"TotInvVal": 1180.0, "ItemCnt": 1, "MainHsnCode": "998713",
			"Irn": "a" * 64, "IrnDt": "2026-01-15 10:00:00",
		}
		data.update(overrides)
		return jwt.encode({"data": json.dumps(data)}, key="", algorithm="none")

	def test_no_qr_is_skipped_never_failed(self):
		"""A supplier below the e-invoice threshold issues no IRN. That is legal."""
		rows = self.rows()

		self.assertTrue(all(r["result"] == "Skipped" for r in rows.values()), rows)

	def test_an_unreadable_qr_fails(self):
		self.assertEqual(self.rows(qr_payload="not-a-jws")["V-FAKE-02"]["result"], "Fail")

	def test_a_matching_qr_agrees_with_the_document(self):
		rows = self.rows(qr_payload=self.signed(), irn="a" * 64)

		self.assertEqual(rows["V-FAKE-04"]["result"], "Pass")
		self.assertEqual(rows["V-GST-08"]["result"], "Pass")
		self.assertEqual(rows["V-GST-09"]["result"], "Pass")
		self.assertEqual(rows["V-GST-10"]["result"], "Pass")

	def test_an_altered_total_is_caught(self):
		"""The QR is signed; the printed page is not. Disagreement means tampering."""
		row = self.rows(qr_payload=self.signed(), grand_total=99999.0)["V-FAKE-04"]

		self.assertEqual(row["result"], "Fail")
		self.assertIn("total", row["found"])

	def test_an_altered_invoice_number_is_caught(self):
		row = self.rows(qr_payload=self.signed(DocNo="OTHER-9"))["V-FAKE-04"]

		self.assertEqual(row["result"], "Fail")
		self.assertIn("invoice no", row["found"])

	def test_an_altered_date_is_caught(self):
		row = self.rows(qr_payload=self.signed(DocDt="01/02/2026"))["V-FAKE-04"]

		self.assertEqual(row["result"], "Fail")
		self.assertIn("date", row["found"])

	def test_a_qr_issued_to_another_buyer_is_not_ours_to_book(self):
		row = self.rows(qr_payload=self.signed(BuyerGstin=OTHER_PAN_GSTIN))["V-GST-09"]

		self.assertEqual(row["result"], "Fail")

	def test_an_irn_that_differs_from_the_qr_is_fraud(self):
		rows = self.rows(qr_payload=self.signed(), irn="b" * 64)

		self.assertEqual(rows["V-GST-10"]["result"], "Fail")

	def test_signature_verification_is_skipped_without_a_certificate(self):
		"""Skipped, never Pass: decoding proves the document is self-consistent, not
		that NIC signed it. Passing here would be a security bug."""
		row = self.rows(qr_payload=self.signed())["V-FAKE-02"]

		self.assertEqual(row["result"], "Skipped")
		self.assertIn("certificate", row["message"])


class TestMatchingDiff(IntegrationTestCase):
	"""Requirements 10 and 11 — green / yellow / red against what ERPNext says is
	billable. The mapper's answer is fed in directly, so these exercise our diff
	rather than re-testing ERPNext's mapper."""

	ITEM, QTY, RATE, WAREHOUSE = "_Test VIA Item", 10.0, 100.0, "_Test VIA Warehouse"

	def expected(self, qty=None, rate=None, uom="Nos", **extra):
		from vendor_invoice_automation.validations import matching

		item = frappe._dict(item_code=self.ITEM, qty=qty or self.QTY, rate=rate or self.RATE,
			uom=uom, warehouse=self.WAREHOUSE, **extra)
		return matching._by_item(frappe._dict(items=[item]))

	def line(self, **kw):
		base = {"item_code": self.ITEM, "qty": self.QTY, "rate": self.RATE,
			"amount": self.QTY * self.RATE, "uom": "Nos"}
		base.update(kw)
		return base

	def diff(self, lines, allowance=0.0, expected=None):
		"""`allowance` stands in for ERPNext's own, so the yellow band is exercised on a
		site whose allowances are zero."""
		from vendor_invoice_automation.validations import matching

		real = matching._allowance
		matching._allowance = lambda item, kind, **kw: allowance
		try:
			rows = matching._line_checks({"items": lines},
				expected if expected is not None else self.expected(), "po_matching", "V-PO")
		finally:
			matching._allowance = real
		return {r["check_id"]: r for r in rows}

	def test_an_exact_invoice_is_green(self):
		rows = self.diff([self.line()])

		self.assertTrue(all(r["result"] == "Pass" for r in rows.values()), rows)

	def test_a_variance_inside_the_allowance_is_yellow(self):
		row = self.diff([self.line(qty=10.2, amount=1020.0)], allowance=2.0)["V-PO-10"]

		self.assertEqual(row["result"], "Fail")
		self.assertEqual(row["severity"], "Warning")

	def test_a_variance_beyond_the_allowance_is_red(self):
		row = self.diff([self.line(qty=10.3, amount=1030.0)], allowance=2.0)["V-PO-10"]

		self.assertEqual(row["result"], "Fail")
		self.assertEqual(row["severity"], "Error")

	def test_over_billing_is_measured_against_the_allowance(self):
		self.assertEqual(self.diff([self.line(amount=1020.0)], allowance=2.0)["V-PO-12"]["severity"],
			"Warning")
		self.assertEqual(self.diff([self.line(amount=1030.0)], allowance=2.0)["V-PO-12"]["severity"],
			"Error")

	def test_a_line_that_is_not_billable_is_blocking(self):
		row = self.diff([self.line(item_code="_Test Item Not On The Order")])["V-PO-07"]

		self.assertEqual(row["result"], "Fail")
		self.assertEqual(row["severity"], "Error")

	def test_an_unresolved_line_skips_the_numeric_checks_rather_than_passing_them(self):
		"""Silently passing qty/rate/amount because nothing matched would turn an
		entirely wrong invoice green."""
		rows = self.diff([self.line(item_code="_Test Item Not On The Order")])

		for check_id in ("V-PO-10", "V-PO-11", "V-PO-12"):
			self.assertEqual(rows[check_id]["result"], "Skipped")

	def test_a_different_uom_is_blocking(self):
		"""A different unit makes every quantity comparison meaningless."""
		row = self.diff([self.line(uom="Kg")])["V-PO-09"]

		self.assertEqual(row["result"], "Fail")
		self.assertEqual(row["severity"], "Error")

	def test_an_invoice_with_no_lines_cannot_match(self):
		self.assertEqual(self.diff([])["V-PO-07"]["result"], "Fail")

	def test_one_item_ordered_twice_accepts_either_price(self):
		from vendor_invoice_automation.validations import matching

		two = matching._by_item(frappe._dict(items=[
			frappe._dict(item_code=self.ITEM, qty=5.0, rate=100.0, uom="Nos"),
			frappe._dict(item_code=self.ITEM, qty=5.0, rate=120.0, uom="Nos"),
		]))
		for rate in (100.0, 120.0):
			self.assertEqual(
				self.diff([self.line(qty=10.0, rate=rate, amount=1100.0)], expected=two)["V-PO-11"]["result"],
				"Pass", f"rate {rate} should match an order carrying it")

	def test_warehouse_batch_and_serial_are_compared_only_when_stated(self):
		from vendor_invoice_automation.validations import matching

		expected = self.expected(batch_no="BATCH-A")
		cases = {
			"agrees": (self.line(warehouse=self.WAREHOUSE, batch_no="BATCH-A"), "Pass"),
			"states neither": (self.line(), "Pass"),
			"wrong warehouse": (self.line(warehouse="_Test Other Warehouse"), "Fail"),
			"wrong batch": (self.line(warehouse=self.WAREHOUSE, batch_no="BATCH-Z"), "Fail"),
		}
		for label, (line, want) in cases.items():
			row = matching._warehouse_batch_serial({"items": [line]}, expected)
			self.assertEqual(row["result"], want, f"{label}: {row['message']} {row['found']}")


class TestITC(IntegrationTestCase):
	"""Requirement 8 — ITC classification, straight off GSTR-2B."""

	def classify(self, **fields):
		from vendor_invoice_automation.validations.itc import _classify

		return _classify(fields)[0]

	def test_every_itc_state_is_classified(self):
		cases = {
			"Eligible": {"itc_availability": "Yes"},
			"Provisional": {"itc_availability": "Temporary"},
			"Ineligible": {"itc_availability": "No"},
			"Blocked": {"itc_availability": "No", "reason_itc_unavailability": "POS and PoS state differ"},
			"RCM": {"is_reverse_charge": 1, "itc_availability": "No"},
			"ISD": {"classification": "ISD", "itc_availability": "Yes"},
		}
		for want, fields in cases.items():
			self.assertEqual(self.classify(**fields), want, fields)

	def test_reverse_charge_outranks_the_availability_flag(self):
		"""A reverse-charge invoice reads as 'no credit' in 2B because the supplier
		charged no tax — but we pay it and claim it, so it is RCM, not Ineligible."""
		self.assertEqual(self.classify(is_reverse_charge=1, itc_availability="No"), "RCM")

	def test_no_2b_row_emits_nothing_and_never_blocks(self):
		"""V-GST-16 already reports "not yet in 2B"; saying it again here was noise."""
		payload = {"supplier_gstin": SUPPLIER_GSTIN, "invoice_no": "ITC-NOT-FILED-YET"}
		r = validate_invoice(payload, ["itc"])["data"]

		self.assertEqual(r["checks"], [])
		self.assertEqual(r["verdict"], "green")
