"""Factories behind the one-function-per-requirement-point API.

Every point in the vendor-onboarding requirement gets its own whitelisted, rate-limited
function in the `stageN_*.py` modules — `company_name_to_cin_lookup`,
`cin_based_company_profile`, and so on — so a caller (or the API browser) sees the
requirement's own vocabulary, not a `call_transbnk(endpoint=...)` indirection.

What's identical across all ~110 of them (whitelisting, rate limiting, parsing the
payload, calling TransBnk, wrapping the response, or refusing cleanly when TransBnk
has no matching API) lives here, once. A stage module line is then one call to
`_endpoint()` or `_unavailable()`, not a repeated function body.
"""

import frappe
from frappe.rate_limiter import rate_limit

from vendor_invoice_automation.integrations import transbnk

from ..response_formatter import api_response, handle_bad_request

# Filled in by _endpoint()/_unavailable() as the stage modules import. `list_requirement_points()`
# (see __init__.py) reads this instead of re-deriving it, so the discovery list can never drift
# from what actually got registered.
REQUIREMENT_POINTS: list[dict] = []


def _proxy(path: str, payload, method: str = "POST") -> dict:
	if isinstance(payload, str):
		payload = frappe.parse_json(payload)
	try:
		data = transbnk.call(path, payload or {}, method=method)
	except transbnk.TransBnkError as e:
		return api_response(success=False, message=str(e), error_code="TRANSBNK_ERROR")
	return api_response(success=True, data=data)


def _endpoint(path: str, name: str, doc: str, method: str = "POST"):
	"""One requirement point that TransBnk covers: a whitelisted function that proxies
	straight to `path`."""

	def handler(payload: dict | str | None = None) -> dict:
		return _proxy(path, payload, method=method)

	handler.__name__ = name
	handler.__qualname__ = name
	handler.__doc__ = doc
	fn = frappe.whitelist(methods=["POST"])(rate_limit(limit=60, seconds=60)(handler))
	fn._onboarding_available = True
	return fn


def _unavailable(name: str, reason: str):
	"""One requirement point TransBnk's current doc set does not cover. Still a real,
	discoverable, whitelisted function — it returns a NOT_AVAILABLE error rather than
	404ing or silently not existing, so a caller can branch on it exactly like it
	branches on any other point instead of special-casing "endpoint doesn't exist"."""

	def handler(payload: dict | str | None = None) -> dict:
		return handle_bad_request(reason, error_code="NOT_AVAILABLE")

	handler.__name__ = name
	handler.__qualname__ = name
	handler.__doc__ = reason
	fn = frappe.whitelist(methods=["POST"])(handler)
	fn._onboarding_available = False
	return fn


def _register_stage(stage: int, module_globals: dict):
	"""Called once at the bottom of each stageN_*.py module. Every public top-level
	name in that module is a point built by `_endpoint()`/`_unavailable()` — nothing
	else is defined there — so this needs no per-call bookkeeping to stay accurate."""
	for name, obj in module_globals.items():
		available = getattr(obj, "_onboarding_available", None)
		if available is None:
			continue
		REQUIREMENT_POINTS.append({
			"name": name,
			"stage": stage,
			"available": available,
			"doc": (obj.__doc__ or "").strip(),
		})
