# Copyright (c) 2026, 8848 Digital and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class HOPSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		hop_token: DF.Password | None
		hop_url: DF.Data | None
	# end: auto-generated types

	_DOCTYPE_NAME = "HOP Settings"
