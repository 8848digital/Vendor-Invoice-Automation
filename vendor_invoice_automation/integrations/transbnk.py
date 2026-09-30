"""Thin authenticated client for TransBnk (trusthub.in) verification APIs.

TransBnk requires IP whitelisting, so by default this module proxies every call through
the whitelisted HOP relay (see `integrations.hop`) rather than calling trusthub.in directly.
`TransBnk Settings.use_hop` controls that per this integration — flip it off only if the
calling bench's own egress IP is itself whitelisted with TransBnk. Callers go through
`vendor_invoice_automation.api.v1.onboarding`, which maps a logical endpoint key (from
`TRANSBNK_ENDPOINTS`) to the `path` this function actually calls.
"""

import frappe

from vendor_invoice_automation.integrations import hop


class TransBnkError(frappe.ValidationError):
	pass


def _settings():
	settings = frappe.get_single("TransBnk Settings")
	if not settings.enabled:
		frappe.throw("TransBnk Settings is disabled.", TransBnkError)
	if not settings.get_password("api_key", raise_exception=False):
		frappe.throw("TransBnk Settings has no API key configured.", TransBnkError)
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
	"""Send `payload` to a TransBnk endpoint path (e.g. "/pan-details"), via the HOP
	proxy unless `use_hop` is off, and return the parsed JSON body. Raises TransBnkError
	on a transport failure, a non-JSON body, or a non-2xx response — callers never see
	a raw `requests` exception."""
	settings = _settings()
	base = settings.uat_base_url if settings.environment == "UAT" else settings.prod_base_url
	target_url = base.rstrip("/") + path
	target_headers = {
		"x-api-key": settings.get_password("api_key"),
		"Content-Type": "application/json",
	}

	body, error, duration_ms = hop.call(target_url, method, target_headers, payload, use_hop=settings.use_hop)

	_log_call(path, method, error, duration_ms)

	if error:
		frappe.throw(error, TransBnkError)
	return body
