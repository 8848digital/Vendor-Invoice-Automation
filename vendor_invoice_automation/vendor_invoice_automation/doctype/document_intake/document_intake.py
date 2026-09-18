# Copyright (c) 2026, 8848 Digital and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class DocumentIntake(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF
		from vendor_invoice_automation.vendor_invoice_automation.doctype.document_intake_check.document_intake_check import DocumentIntakeCheck
		from vendor_invoice_automation.vendor_invoice_automation.doctype.document_intake_item.document_intake_item import DocumentIntakeItem

		against: DF.DynamicLink | None
		against_type: DF.Link | None
		amount: DF.Currency
		buyer: DF.Link | None
		checks: DF.Table[DocumentIntakeCheck]
		company: DF.Link | None
		confidence: DF.Percent
		created_doc: DF.DynamicLink | None
		created_doctype: DF.Link | None
		currency: DF.Link | None
		document_type: DF.Link
		exception_type: DF.Data | None
		extracted_data: DF.JSON | None
		extraction_method: DF.Literal["", "E-Invoice JSON", "QR", "XML", "Text PDF", "LLM"]
		file: DF.Attach | None
		file_hash: DF.Data | None
		intake_ref: DF.Data | None
		inward_supply: DF.Link | None
		irn: DF.Data | None
		itc_status: DF.Data | None
		items: DF.Table[DocumentIntakeItem]
		matching_mode: DF.Data | None
		party: DF.DynamicLink | None
		party_type: DF.Link | None
		plant: DF.Link | None
		profile: DF.Data | None
		qr_hash: DF.Data | None
		reference_date: DF.Date | None
		reference_no: DF.Data | None
		reminder_sent_on: DF.Datetime | None
		review_required: DF.Check
		status: DF.Literal["Uploaded", "OCR Processing", "OCR Completed", "OCR Failed", "GST Validation", "GST Failed", "PO Matched", "PO Failed", "GRN Matched", "GRN Failed", "Duplicate", "Workflow", "Approved", "Rejected", "Posted", "Payment Pending", "Paid", "Vendor Invoice Pending Upload"]
		tax_amount: DF.Currency
		tax_id: DF.Data | None
		taxable_value: DF.Currency
		uncertain_fields: DF.SmallText | None
		uploaded_by: DF.Link | None
		verdict: DF.Literal["", "green", "yellow", "red"]
	# end: auto-generated types

	def before_validate(self):
		"""Jarvis saves an intake by passing only `intake_ref`; the validated values come from
		the server cache, so what is stored is byte-identical to what was checked — the model
		never re-types forty check rows."""
		if not self.intake_ref:
			return
		from vendor_invoice_automation.api.v1.intake import load_ref

		values = load_ref(self.intake_ref)
		if not values:
			frappe.throw("This intake_ref has expired or is unknown. Run process_invoice again.")
		if self.created_doc and not self.is_new():
			# Once a Purchase Invoice exists its workflow owns the status.
			values.pop("status", None)
		self.set("items", [])
		self.set("checks", [])
		self.update(values)
		self.intake_ref = None

	def on_update(self):
		from vendor_invoice_automation.intake import actions

		actions.sync(self)
