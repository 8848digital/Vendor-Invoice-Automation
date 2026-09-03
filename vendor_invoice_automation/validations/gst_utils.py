"""Thin helpers over `india_compliance`. Shared by `fraud.py` and `gst.py`.

SPEC §5 Stage 3 is explicit that GST rules belong to `india_compliance`, not to a
parallel layer here. This module holds only the glue: turning its throwing validators
into values a check row can carry.
"""

import frappe

from india_compliance.gst_india.doctype.gstin.gstin import get_gstin_status
from india_compliance.gst_india.utils import is_valid_pan, validate_gstin


def pan_of(gstin):
	"""Characters 3-12 of a GSTIN are the holder's PAN — india_compliance's own idiom
	(gst_india/overrides/party.py)."""
	if not gstin or len(gstin) < 12:
		return None
	pan = gstin[2:12]
	return pan if is_valid_pan(pan) else None


def gstin_error(gstin, label="GSTIN"):
	"""india_compliance's validate_gstin throws; we want the message as a check row.
	Returns None when the GSTIN is valid."""
	try:
		validate_gstin(gstin, label=label)
		return None
	except Exception as e:
		return frappe.utils.strip_html(str(e)) or "invalid"


def gstin_doc(gstin, invoice_date):
	"""Local GSTIN row, refreshed from the GSTN API only if GST Settings enables it.
	Returns None when the status is simply unknown — callers must treat that as
	Skipped, never Fail (SPEC §8)."""
	try:
		return get_gstin_status(gstin, doc={"posting_date": invoice_date})
	except Exception:
		return None
