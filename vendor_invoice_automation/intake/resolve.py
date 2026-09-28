"""Turn printed values into master-data names: supplier, company, and each line's item_code.

The model transcribes what is printed; mapping "Alpha Systems Ltd." to a Supplier record, or
"Laptop 14in" to an Item, is a database lookup, so it happens here. Every resolution made is
reported back in `resolved[]` — nothing is silently guessed.
"""

import frappe


def run(p):
	"""Mutates `p` in place. Returns human-readable notes for each value it filled."""
	notes = []
	_supplier(p, notes)
	_company(p, notes)
	_items(p, notes)
	return notes


def _supplier(p, notes):
	name, gstin = p.get("supplier"), p.get("supplier_gstin")
	if name and frappe.db.exists("Supplier", name):
		return
	matches = frappe.get_all("Supplier", filters={"gstin": gstin}, pluck="name") if gstin else []
	if not matches and name:
		matches = frappe.get_all("Supplier", filters={"supplier_name": name}, pluck="name")
	if len(matches) == 1:
		notes.append(f"supplier: '{name or gstin}' → {matches[0]}")
		p["supplier"] = matches[0]
	elif name:
		# Leave the printed name: V-INT-04 then fails it as "not one Supplier", which is true.
		notes.append(f"supplier: '{name}' matched {len(matches)} Supplier records")


def _company(p, notes):
	company = p.get("company")
	if company and frappe.db.exists("Company", company):
		return
	found = None
	if p.get("company_gstin"):
		found = frappe.db.get_value("Dynamic Link",
			{"link_doctype": "Company", "parenttype": "Address",
			 "parent": ["in", frappe.get_all("Address", {"gstin": p["company_gstin"]}, pluck="name") or [""]]},
			"link_name")
	if not found:
		companies = frappe.get_all("Company", pluck="name", limit=2)
		found = frappe.defaults.get_user_default("Company") or (companies[0] if len(companies) == 1 else None)
	if found:
		notes.append(f"company: '{company or p.get('company_gstin') or ''}' → {found}")
		p["company"] = found


def _items(p, notes):
	"""Match unresolved lines against the PO's own lines — the only items that can be billed."""
	lines = [line for line in p.get("items") or [] if not line.get("item_code")]
	po = p.get("po_number")
	if not lines or not (po and frappe.db.exists("Purchase Order", po)):
		return

	po_items = frappe.get_all("Purchase Order Item", filters={"parent": po},
		fields=["item_code", "item_name", "description"], order_by="idx")
	supplier_parts = {
		(r.supplier_part_no or "").strip().casefold(): r.parent
		for r in frappe.get_all("Item Supplier", filters={"supplier": p.get("supplier") or ""},
			fields=["parent", "supplier_part_no"])
		if r.supplier_part_no
	}

	for line in lines:
		text = (line.get("description") or "").strip().casefold()
		code = supplier_parts.get((line.get("supplier_part_no") or "").strip().casefold()) or next(
			(i.item_code for i in po_items
			 if text and text in {(i.item_name or "").casefold(), frappe.utils.strip_html(i.description or "").strip().casefold(), i.item_code.casefold()}),
			None)
		# ponytail: exact-text match only; add fuzzy matching when real invoices show it's needed.
		if not code and len(po_items) == 1 and len(p["items"]) == 1:
			code = po_items[0].item_code
		if code:
			line["item_code"] = code
			notes.append(f"item: '{line.get('description') or ''}' → {code}")
