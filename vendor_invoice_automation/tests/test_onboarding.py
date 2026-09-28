# Copyright (c) 2026, 8848 Digital and Contributors
# For license information, please see license.txt

"""Unit tests for the TransBnk onboarding proxy.

No real HTTP leaves the process: `transbnk.call` is patched out, so these prove the
allowlist gate and the response envelope, not TransBnk's own behaviour.
"""

from unittest.mock import patch

from frappe.tests import UnitTestCase

from vendor_invoice_automation.api.v1 import onboarding
from vendor_invoice_automation.api.v1.onboarding import call_transbnk, list_endpoints, list_requirement_points
from vendor_invoice_automation.integrations.transbnk_endpoints import TRANSBNK_ENDPOINTS


class TestCallTransBnk(UnitTestCase):
	def test_unknown_endpoint_is_refused_before_any_request(self):
		with patch("vendor_invoice_automation.integrations.transbnk.call") as mock_call:
			result = call_transbnk(endpoint="bank_payout", payload={})

		mock_call.assert_not_called()
		self.assertEqual(result["status"], "error")
		self.assertEqual(result["error_code"], "UNKNOWN_ENDPOINT")

	def test_known_endpoint_calls_the_mapped_path(self):
		with patch("vendor_invoice_automation.integrations.transbnk.call") as mock_call:
			mock_call.return_value = {"status": True, "data": {"pan_number": "AAIPM3854E"}}
			result = call_transbnk(endpoint="pan_basic", payload={"isUserConsent": "y", "panId": "AAIPM3854E"})

		mock_call.assert_called_once_with("/pan-details", {"isUserConsent": "y", "panId": "AAIPM3854E"}, method="POST")
		self.assertEqual(result["status"], "success")
		self.assertEqual(result["data"]["data"]["pan_number"], "AAIPM3854E")

	def test_transbnk_error_becomes_an_error_envelope_not_an_exception(self):
		from vendor_invoice_automation.integrations.transbnk import TransBnkError

		with patch("vendor_invoice_automation.integrations.transbnk.call", side_effect=TransBnkError("boom")):
			result = call_transbnk(endpoint="pan_basic", payload={})

		self.assertEqual(result["status"], "error")
		self.assertEqual(result["error_code"], "TRANSBNK_ERROR")

	def test_list_endpoints_covers_every_registry_entry(self):
		result = list_endpoints()
		listed = {key for stage in result["data"].values() for key in stage["endpoints"]}
		self.assertEqual(listed, set(TRANSBNK_ENDPOINTS))


class TestPerPointFunctions(UnitTestCase):
	"""One named whitelisted function per requirement bullet — see stage1..5 modules."""

	def test_an_available_point_proxies_to_its_mapped_path(self):
		with patch("vendor_invoice_automation.integrations.transbnk.call") as mock_call:
			mock_call.return_value = {"status": True, "data": {"cin": "U12345MH2020PTC000000"}}
			result = onboarding.cin_based_company_profile(payload={"cin": "U12345MH2020PTC000000"})

		mock_call.assert_called_once_with("/cin-validation", {"cin": "U12345MH2020PTC000000"}, method="POST")
		self.assertEqual(result["status"], "success")

	def test_gap_points_the_user_asked_about_are_explicit_not_available(self):
		# The two examples from the request: neither has a matching TransBnk endpoint.
		for point in (onboarding.company_name_to_cin_lookup, onboarding.pan_to_cin_lookup):
			with patch("vendor_invoice_automation.integrations.transbnk.call") as mock_call:
				result = point(payload={})
			mock_call.assert_not_called()
			self.assertEqual(result["status"], "error")
			self.assertEqual(result["error_code"], "NOT_AVAILABLE")

	def test_list_requirement_points_covers_every_stage_and_flags_gaps(self):
		result = list_requirement_points()
		data = result["data"]
		self.assertEqual(set(data), {1, 2, 3, 4, 5})

		all_points = {name: p for stage in data.values() for name, p in stage["points"].items()}
		self.assertIn("cin_based_company_profile", all_points)
		self.assertTrue(all_points["cin_based_company_profile"]["available"])
		self.assertIn("pan_to_cin_lookup", all_points)
		self.assertFalse(all_points["pan_to_cin_lookup"]["available"])

		# every point is whitelisted and callable from the package namespace
		import frappe

		for name in all_points:
			fn = getattr(onboarding, name)
			self.assertIn(fn, frappe.whitelisted, f"{name} is not whitelisted")
