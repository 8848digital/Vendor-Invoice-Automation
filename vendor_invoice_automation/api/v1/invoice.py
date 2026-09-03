"""Vendor invoice validation endpoints.

Thin transport layer: parse, delegate, format. All rules live in
`vendor_invoice_automation.validations`.
"""

import json

import frappe

from vendor_invoice_automation.validations import BLOCKS, DEFAULT_SEQUENCE
from vendor_invoice_automation.validations import validate as _validate

from .response_formatter import api_response, handle_bad_request


@frappe.whitelist()
def validate_invoice(invoice: dict | str, blocks: list | str | None = None) -> dict:
	"""Validate one extracted invoice. Read-only — nothing is stored or written.

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
	    items             [{item_code, supplier_part_no, description, hsn_sac, qty,
	                        uom, rate, amount, gst_rate, tax_amount}]

	`blocks` picks which validation blocks run, in the order given — a list, a JSON
	array, or a comma-separated string. Omit it to run the whole sequence. Call
	`validation_blocks()` for the names.

	`data` carries the verdict, `auto_create_allowed`, and every check row. Gate any
	write on `auto_create_allowed`, not on `ok`.
	"""
	if isinstance(invoice, str):
		try:
			invoice = json.loads(invoice)
		except ValueError as e:
			return handle_bad_request(f"`invoice` is not valid JSON: {e}")
	if not isinstance(invoice, dict):
		return handle_bad_request("`invoice` must be an object or a JSON string.")

	if isinstance(blocks, str):
		try:
			blocks = json.loads(blocks)
		except ValueError:
			blocks = [b.strip() for b in blocks.split(",") if b.strip()]
	if blocks is not None and not isinstance(blocks, list):
		return handle_bad_request("`blocks` must be a list of block names.")

	try:
		result = _validate(invoice, blocks)
	except ValueError as e:
		return handle_bad_request(str(e))
	return api_response(
		success=result["ok"],
		data=result,
		message=result["exception_type"] or f"Validation {result['verdict']}.",
	)


@frappe.whitelist()
def validation_blocks() -> dict:
	"""The block names `validate_invoice` accepts, and the default sequence."""
	return api_response(data={"blocks": sorted(BLOCKS), "default": list(DEFAULT_SEQUENCE)})
