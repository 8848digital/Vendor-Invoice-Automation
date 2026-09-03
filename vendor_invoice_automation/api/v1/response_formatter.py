"""Consistent API responses across every vendor_invoice_automation endpoint.

Mirrors the house `api_response` envelope. Note this takes `success: bool`, not a
`status` string — the handlers below pass it correctly.
"""

from datetime import datetime
from typing import Any


def api_response(
	success: bool = True,
	data: Any = None,
	message: str | None = None,
	error_code: str | None = None,
) -> dict[str, Any]:
	"""Standard envelope.

	Args:
		success: True for "success", False for "error"
		data: response payload
		message: human-readable message
		error_code: machine-readable code, on failures only

	Returns:
		Formatted response dictionary, with None values stripped.
	"""
	response = {
		"status": "success" if success else "error",
		"data": data,
		"message": message,
		"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
	}

	if error_code:
		response["error_code"] = error_code

	return {k: v for k, v in response.items() if v is not None}


def handle_bad_request(message: str, error_code: str = "BAD_REQUEST"):
	return api_response(success=False, message=message, error_code=error_code)


def handle_permission_error(message: str | None = None):
	return api_response(
		success=False,
		message=message or "You don't have permission to access this resource",
		error_code="PERMISSION_DENIED",
	)
