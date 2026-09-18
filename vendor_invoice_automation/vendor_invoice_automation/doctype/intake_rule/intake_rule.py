# Copyright (c) 2026, 8848 Digital and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class IntakeRule(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		check_id: DF.Data
		description: DF.SmallText | None
		document_type: DF.Link
		enabled: DF.Check
		severity: DF.Literal["", "Info", "Warning", "Error"]
	# end: auto-generated types

	_DOCTYPE_NAME = "Intake Rule"

	def validate(self):
		self.check_id = (self.check_id or "").strip()
		clash = frappe.db.exists("Intake Rule", {"document_type": self.document_type, "check_id": self.check_id,
			"name": ["!=", self.name]})
		if clash:
			frappe.throw(f"{clash} already configures {self.check_id} for {self.document_type}.")
