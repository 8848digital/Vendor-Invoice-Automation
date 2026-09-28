# Copyright (c) 2026, 8848 Digital and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class DocumentIntakeCheck(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		check_id: DF.Data | None
		expected: DF.SmallText | None
		found: DF.SmallText | None
		message: DF.SmallText | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		result: DF.Literal["Pass", "Fail", "Skipped"]
		severity: DF.Literal["Info", "Warning", "Error"]
		stage: DF.Data | None
	# end: auto-generated types

	_DOCTYPE_NAME = "Document Intake Check"
