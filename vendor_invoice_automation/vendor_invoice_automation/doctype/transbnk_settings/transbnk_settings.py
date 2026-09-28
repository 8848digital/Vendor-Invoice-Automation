# Copyright (c) 2026, 8848 Digital and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class TransBnkSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		api_key: DF.Password | None
		enabled: DF.Check
		environment: DF.Literal["UAT", "Production"]
		prod_base_url: DF.Data | None
		uat_base_url: DF.Data | None
	# end: auto-generated types

	_DOCTYPE_NAME = "TransBnk Settings"
