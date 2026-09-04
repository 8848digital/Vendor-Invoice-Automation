"""Vendor invoice validation endpoints.

Thin transport layer: parse, delegate, format. All rules live in
`vendor_invoice_automation.validations`.

This API reads no business data of its own. Everything the checks compare against arrives
as `context`, assembled by the caller against its own site — see CONTEXT.md for how to
build it and which keys each block needs.
"""

import json
import secrets

import frappe
from frappe.rate_limiter import rate_limit

from vendor_invoice_automation.validations import BLOCKS, DEFAULT_SEQUENCE
from vendor_invoice_automation.validations import validate as _validate

from .response_formatter import api_response, handle_bad_request

# Bumped whenever the `context` contract changes shape. Callers send theirs; a mismatch is
# refused rather than silently validating against keys we no longer read.
CONTRACT_VERSION = "1.0"

# Which context keys each block consumes. Returned by `validation_blocks()` so a caller can
# discover the contract instead of reading source, and so a per-block caller sends only what
# its own block needs.
CONTEXT_BY_BLOCK = {
	"intake": ["supplier"],
	"extraction": ["fiscal_year", "company_gstins"],
	"duplicate": ["existing_invoices", "irn_hits"],
	"fraud": ["supplier"],
	"einvoice": [],
	"gst": ["supplier", "hsn_codes", "inward_supply", "gstin_status"],
	"itc": ["inward_supply"],
	"routing": ["items"],
	"po_match": ["po", "items", "settings"],
	"grn_match": ["grn", "items", "settings"],
}

_REF_PREFIX = "via:invoice:"
_REF_TTL_SECONDS = 3600


def _mint_ref(invoice: dict) -> str:
	"""Cache the payload so later calls validate byte-identically what was extracted once.

	Redis only, never a doctype: this is a request cache, not a record — nothing here is
	queryable, listable or durable, and it evaporates on its own. The token is a bearer
	secret, so it is random rather than derived from anything about the invoice.
	"""
	ref = secrets.token_urlsafe(32)
	frappe.cache().set_value(_REF_PREFIX + ref, invoice, expires_in_sec=_REF_TTL_SECONDS)
	return ref


def _resolve_ref(ref: str):
	return frappe.cache().get_value(_REF_PREFIX + ref)


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=60, seconds=60)
def validate_invoice(
	invoice: dict | str | None = None,
	blocks: list | str | None = None,
	context: dict | str | None = None,
	invoice_ref: str | None = None,
	contract_version: str | None = None,
) -> dict:
	"""Validate one extracted invoice. Read-only — nothing is written.

	`invoice` is the extracted payload (dict, or a JSON string):

	    supplier          Supplier name (required)
	    company           Company name (required for V-EXT-09 / V-EXT-10)
	    invoice_no        supplier's bill number
	    invoice_date      YYYY-MM-DD
	    supplier_gstin    GSTIN printed on the document
	    company_gstin     buyer GSTIN printed on the document
	    place_of_supply   "NN-State Name"
	    po_number         Purchase Order, if any — absent means non-PO
	    irn, currency
	    taxable_value, cgst, sgst, igst, cess, round_off, grand_total
	    declared          {grand_total, ...} — what the uploader typed, optional
	    items             [{item_code, hsn_sac, qty, uom, rate, amount,
	                        warehouse, batch_no, serial_no, description}]

	`context` is what the checks compare against, fetched by the caller on its own site.
	A key that is **absent** means "I did not look" and yields Skipped; a key present and
	`null`/`[]` means "I looked and found nothing" and is judged as the real answer. Call
	`validation_blocks()` for which keys each block needs.

	`blocks` picks which validation blocks run, in the order given — a list, a JSON array,
	or a comma-separated string. Omit it to run the whole sequence.

	Pass `invoice` once and reuse the returned `invoice_ref` on later calls instead: every
	block then validates byte-identically the same payload, which matters when a multi-step
	caller would otherwise restate it from a transcript.

	`data` carries the verdict, `auto_create_allowed`, and every check row. Gate any write
	on `auto_create_allowed`, never on `ok` — a green verdict with blocking checks `unrun`
	is not a clean invoice, it is an unvalidated one.
	"""
	if contract_version and contract_version != CONTRACT_VERSION:
		return handle_bad_request(
			f"`contract_version` {contract_version!r} does not match this API's "
			f"{CONTRACT_VERSION!r}. Re-read validation_blocks() for the current contract."
		)

	if invoice_ref and invoice is None:
		invoice = _resolve_ref(invoice_ref)
		if invoice is None:
			return handle_bad_request(
				"`invoice_ref` is unknown or expired; re-run extraction and send `invoice`."
			)
		minted = invoice_ref
	else:
		invoice, err = _as_dict(invoice, "invoice")
		if err:
			return handle_bad_request(err)
		if invoice is None:
			return handle_bad_request("Supply either `invoice` or `invoice_ref`.")
		minted = _mint_ref(invoice)

	context, err = _as_dict(context, "context")
	if err:
		return handle_bad_request(err)

	if isinstance(blocks, str):
		try:
			blocks = json.loads(blocks)
		except ValueError:
			blocks = [b.strip() for b in blocks.split(",") if b.strip()]
	if blocks is not None and not isinstance(blocks, list):
		return handle_bad_request("`blocks` must be a list of block names.")

	try:
		result = _validate(invoice, blocks, context or {})
	except ValueError as e:
		return handle_bad_request(str(e))

	result["invoice_ref"] = minted
	result["contract_version"] = CONTRACT_VERSION
	return api_response(
		success=result["ok"],
		data=result,
		message=result["exception_type"] or f"Validation {result['verdict']}.",
	)


def _as_dict(value, label):
	"""Accept a dict, a JSON object string, or None. Returns (value, error_message)."""
	if value is None or isinstance(value, dict):
		return value, None
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError as e:
			return None, f"`{label}` is not valid JSON: {e}"
		if not isinstance(value, dict):
			return None, f"`{label}` must be an object or a JSON string."
		return value, None
	return None, f"`{label}` must be an object or a JSON string."


@frappe.whitelist(allow_guest=True)
def validation_blocks() -> dict:
	"""The block names `validate_invoice` accepts, the default sequence, and the `context`
	keys each block consumes."""
	return api_response(data={
		"blocks": sorted(BLOCKS),
		"default": list(DEFAULT_SEQUENCE),
		"context_by_block": CONTEXT_BY_BLOCK,
		"contract_version": CONTRACT_VERSION,
	})
