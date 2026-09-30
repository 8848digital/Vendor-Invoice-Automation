# Copyright (c) 2026, 8848 Digital and Contributors
# For license information, please see license.txt

"""Unit tests for TransBnk call logging (vendor_invoice_automation.integrations.transbnk).

TransBnk's own per-key spend limits and IP/velocity controls live in their trusthub.in
dashboard and aren't exposed to us — these tests only cover the local call log that
`transbnk.call` writes on every request, success or failure.
"""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from vendor_invoice_automation.integrations import transbnk


def _fake_settings():
	settings = MagicMock()
	settings.environment = "UAT"
	settings.uat_base_url = "https://sandbox-api.trusthub.in"
	settings.use_hop = True
	settings.get_password.return_value = "secret"
	return settings


def _fake_hop_settings():
	hop_settings = MagicMock()
	hop_settings.hop_url = "https://hop.example.com"
	hop_settings.get_password.return_value = "secret"
	return hop_settings


class TestTransBnkCallLog(UnitTestCase):
	def setUp(self):
		frappe.db.delete("TransBnk Call Log")

	def test_successful_call_is_logged(self):
		response = MagicMock(ok=True, status_code=200)
		response.json.return_value = {"status": "success"}

		with (
			patch.object(transbnk, "_settings", return_value=_fake_settings()),
			patch.object(transbnk.hop.frappe, "get_single", return_value=_fake_hop_settings()),
			patch.object(transbnk.hop.requests, "post", return_value=response),
		):
			transbnk.call("/pan-details", {})

		logs = frappe.get_all(
			"TransBnk Call Log", filters={"endpoint": "/pan-details"}, fields=["status", "error"]
		)
		self.assertEqual(len(logs), 1)
		self.assertEqual(logs[0].status, "Success")
		self.assertFalse(logs[0].error)

	def test_failed_call_is_logged_and_still_raises(self):
		response = MagicMock(ok=False, status_code=500)
		response.json.return_value = {"message": "boom"}

		with (
			patch.object(transbnk, "_settings", return_value=_fake_settings()),
			patch.object(transbnk.hop.frappe, "get_single", return_value=_fake_hop_settings()),
			patch.object(transbnk.hop.requests, "post", return_value=response),
		):
			with self.assertRaises(transbnk.TransBnkError):
				transbnk.call("/pan-details", {})

		logs = frappe.get_all(
			"TransBnk Call Log", filters={"endpoint": "/pan-details"}, fields=["status", "error"]
		)
		self.assertEqual(len(logs), 1)
		self.assertEqual(logs[0].status, "Failed")
		self.assertIn("500", logs[0].error)
