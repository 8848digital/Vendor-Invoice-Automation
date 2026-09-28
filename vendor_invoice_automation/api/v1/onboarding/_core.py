"""Generic fallback: call any allowlisted TransBnk endpoint by registry key.

The primary interface is the one-function-per-requirement-point API in the sibling
`stage1_business_identification.py` .. `stage5_risk_compliance.py` modules — this is
the lower-level escapee for anything not worth a dedicated named point (or added to
the registry before it gets one). Mirrors `invoice.py`'s shape: parse, delegate,
format. Reads and writes no business data of its own.

`endpoint` must be a key in `TRANSBNK_ENDPOINTS` (see integrations/transbnk_endpoints.py
for what's in scope and why). Anything else is refused before a request ever reaches
TransBnk — this is the only guard against the site's API key being used for a product
this proxy wasn't reviewed for.
"""

import frappe
from frappe.rate_limiter import rate_limit

from vendor_invoice_automation.integrations import transbnk
from vendor_invoice_automation.integrations.transbnk_endpoints import STAGE_LABELS, TRANSBNK_ENDPOINTS

from ..response_formatter import api_response, handle_bad_request


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=60)
def call_transbnk(endpoint: str, payload: dict | str | None = None) -> dict:
	"""Call one allowlisted TransBnk endpoint and return its response, unmodified,
	wrapped in the house envelope.

	    endpoint   key from TRANSBNK_ENDPOINTS, e.g. "pan_basic", "bank_account_validate"
	    payload    request body TransBnk expects for that endpoint (dict, or a JSON string)
	"""
	spec = TRANSBNK_ENDPOINTS.get(endpoint)
	if not spec:
		return handle_bad_request(
			f"Unknown TransBnk endpoint {endpoint!r}. Call list_endpoints() for the allowlist.",
			error_code="UNKNOWN_ENDPOINT",
		)

	if isinstance(payload, str):
		payload = frappe.parse_json(payload)

	try:
		data = transbnk.call(spec["path"], payload or {}, method=spec.get("method", "POST"))
	except transbnk.TransBnkError as e:
		return api_response(success=False, message=str(e), error_code="TRANSBNK_ERROR")

	return api_response(success=True, data=data)


@frappe.whitelist()
def list_endpoints() -> dict:
	"""Discovery: every allowlisted endpoint, grouped by onboarding stage, so a caller
	can build a journey without reading source."""
	stages = {stage: {"label": label, "endpoints": {}} for stage, label in STAGE_LABELS.items()}
	for key, spec in TRANSBNK_ENDPOINTS.items():
		stages[spec["stage"]]["endpoints"][key] = spec["label"]

	return api_response(success=True, data=stages)
