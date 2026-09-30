"""Generic client for calling a third-party endpoint either directly, or proxied through
the whitelisted HOP relay (`HOP Settings`) when the target requires IP whitelisting this
app's own egress IP doesn't have. `transbnk.py` is the first caller; any future integration
with the same whitelisting problem reuses this instead of re-implementing the proxy envelope.
"""

import time

import frappe
import requests

TIMEOUT = 30


def call(url: str, method: str, headers: dict, payload: dict, use_hop: bool) -> tuple[dict | None, str | None, int]:
	"""Call `url` directly, or proxied through the HOP relay when `use_hop` is set.
	Returns (body, error, duration_ms) — callers keep their own logging/throw behavior."""
	started = time.monotonic()
	error = None
	body = None

	try:
		if use_hop:
			hop = frappe.get_single("HOP Settings")
			if not hop.hop_url or not hop.get_password("hop_token", raise_exception=False):
				frappe.throw("HOP Settings has no HOP URL/token configured.")
			response = requests.post(
				hop.hop_url,
				headers={
					"Authorization": f"Bearer {hop.get_password('hop_token')}",
					"Content-Type": "application/json",
				},
				json={"url": url, "method": method, "headers": headers, "payload": payload},
				timeout=TIMEOUT,
			)
		else:
			response = requests.request(method, url, headers=headers, json=payload, timeout=TIMEOUT)
	except requests.RequestException as e:
		error = f"{'HOP request' if use_hop else 'Request'} to {url} failed: {e}"
	else:
		try:
			body = response.json()
		except ValueError:
			error = f"{url} returned a non-JSON response ({response.status_code})."
		else:
			if not response.ok:
				error = f"{url} returned {response.status_code}: {body}"

	return body, error, int((time.monotonic() - started) * 1000)
