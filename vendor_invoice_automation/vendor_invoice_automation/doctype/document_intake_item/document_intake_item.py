# Copyright (c) 2026, 8848 Digital and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class DocumentIntakeItem(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		amount: DF.Currency
		batch_no: DF.Data | None
		description: DF.SmallText | None
		gst_rate: DF.Percent
		hsn_sac: DF.Data | None
		item_code: DF.Link | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		qty: DF.Float
		rate: DF.Currency
		serial_no: DF.SmallText | None
		tax_amount: DF.Currency
		uom: DF.Link | None
		warehouse: DF.Link | None
	# end: auto-generated types

	_DOCTYPE_NAME = "Document Intake Item"
