"""Thin authenticated client for TransBnk (trusthub.in) verification APIs.

TransBnk requires IP whitelisting, so instead of calling trusthub.in directly this
module proxies every call through a whitelisted HOP server: the HOP server receives
the target URL/method/headers/payload as its own JSON body, and it is the one whose
IP is whitelisted with TransBnk. This module is the only place that knows any of that.
Callers go through `vendor_invoice_automation.api.v1.onboarding`, which maps a logical
endpoint key (from `TRANSBNK_ENDPOINTS`) to the `path` this function actually calls.
"""

import time

import frappe
import requests

TIMEOUT = 30


class TransBnkError(frappe.ValidationError):
	pass


def _settings():
	settings = frappe.get_single("TransBnk Settings")
	if not settings.enabled:
		frappe.throw("TransBnk Settings is disabled.", TransBnkError)
	if not settings.get_password("api_key", raise_exception=False):
		frappe.throw("TransBnk Settings has no API key configured.", TransBnkError)
	if not settings.hop_url:
		frappe.throw("TransBnk Settings has no HOP URL configured.", TransBnkError)
	if not settings.get_password("hop_token", raise_exception=False):
		frappe.throw("TransBnk Settings has no HOP token configured.", TransBnkError)
	return settings


def _log_call(endpoint: str, method: str, error: str | None, duration_ms: int) -> None:
	"""Best-effort call log, so TransBnk request volume/failures are visible locally —
	TransBnk's own per-key spend limits and IP/velocity controls live in their trusthub.in
	dashboard and aren't queryable from here."""
	try:
		frappe.get_doc(
			{
				"doctype": "TransBnk Call Log",
				"endpoint": endpoint,
				"method": method,
				"status": "Failed" if error else "Success",
				"error": error,
				"duration_ms": duration_ms,
			}
		).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="TransBnk Call Log failed")


def call(path: str, payload: dict, method: str = "POST") -> dict:
	"""Send `payload` to a TransBnk endpoint path (e.g. "/pan-details") via the HOP
	proxy and return the parsed JSON body. Raises TransBnkError on a transport failure,
	a non-JSON body, or a non-2xx response — callers never see a raw `requests`
	exception."""
	settings = _settings()
	base = settings.uat_base_url if settings.environment == "UAT" else settings.prod_base_url
	target_url = base.rstrip("/") + path
	target_headers = {
		"x-api-key": settings.get_password("api_key"),
		"Content-Type": "application/json",
	}

	started = time.monotonic()
	error = None
	body = None

	try:
		response = requests.post(
			settings.hop_url,
			headers={
				"Authorization": f"Bearer {settings.get_password('hop_token')}",
				"Content-Type": "application/json",
			},
			json={"url": target_url, "method": method, "headers": target_headers, "payload": payload},
			timeout=TIMEOUT,
		)
	except requests.RequestException as e:
		error = f"HOP request to {path} failed: {e}"
	else:
		try:
			body = response.json()
		except ValueError:
			error = f"HOP {path} returned a non-JSON response ({response.status_code})."
		else:
			if not response.ok:
				error = f"HOP {path} returned {response.status_code}: {body}"

	_log_call(path, method, error, int((time.monotonic() - started) * 1000))

	if error:
		frappe.throw(error, TransBnkError)
	return body
