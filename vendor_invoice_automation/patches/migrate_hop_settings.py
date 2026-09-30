"""hop_url/hop_token moved off TransBnk Settings onto the shared HOP Settings singleton
(now that any integration can opt into the HOP relay, not just TransBnk). By this
(post_model_sync) point TransBnk Settings' own meta no longer has these fields, so
meta-validated lookups (get_single_value, doc.get_password) would reject them — read
the old values straight from where Frappe actually stores them: hop_url sits in the
`tabSingles` key-value row (untouched by the field's removal from the doctype JSON),
and hop_token, being a Password field, only ever lived in `__Auth`.

Also backfills `use_hop` on the existing TransBnk Settings row: the field's own "1"
default only applies to new documents, not one already saved before this migration,
and every site on the old code was relying on HOP unconditionally — so an already
configured site must come out of this migration still calling via HOP, not silently
switched to direct calls.
"""

import frappe
from frappe.utils.password import get_decrypted_password


def execute():
	old_hop_url = frappe.db.sql(
		"select value from `tabSingles` where doctype=%s and field=%s",
		("TransBnk Settings", "hop_url"),
	)
	old_hop_url = old_hop_url[0][0] if old_hop_url else None
	old_hop_token = get_decrypted_password(
		"TransBnk Settings", "TransBnk Settings", "hop_token", raise_exception=False
	)

	if old_hop_url or old_hop_token:
		hop_settings = frappe.get_single("HOP Settings")
		if not hop_settings.hop_url:
			hop_settings.hop_url = old_hop_url
		if not hop_settings.get_password("hop_token", raise_exception=False):
			hop_settings.hop_token = old_hop_token
		hop_settings.save(ignore_permissions=True)

	frappe.db.set_single_value("TransBnk Settings", "use_hop", 1)
