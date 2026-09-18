# Copyright (c) 2026, 8848 Digital and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class IntakeAction(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF
		from vendor_invoice_automation.vendor_invoice_automation.doctype.document_intake_check.document_intake_check import DocumentIntakeCheck

		action: DF.Literal["Create Purchase Invoice"]
		amount: DF.Currency
		checks: DF.Table[DocumentIntakeCheck]
		decided_by: DF.Link | None
		decided_on: DF.Datetime | None
		decision_note: DF.SmallText | None
		document_type: DF.Link | None
		error: DF.SmallText | None
		intake: DF.Link
		party: DF.DynamicLink | None
		party_type: DF.Link | None
		proposed_by: DF.Link | None
		reason: DF.SmallText | None
		result_doc: DF.DynamicLink | None
		result_doctype: DF.Link | None
		status: DF.Literal["Pending", "Approved", "Rejected", "Failed", "Cancelled"]
		summary: DF.SmallText | None
	# end: auto-generated types

	_DOCTYPE_NAME = "Intake Action"
