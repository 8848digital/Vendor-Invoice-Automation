# Copyright (c) 2026, 8848 Digital and contributors
# For license information, please see license.txt

"""How often a person had to correct what was extracted, per supplier.

A correction is a Track Changes Version on a Document Intake that changed one of the
extracted fields — Jarvis saves first and applies corrections after, so every fix is recorded.
"""

import json

import frappe
from frappe import _

EXTRACTED = {"party", "tax_id", "reference_no", "reference_date", "against", "taxable_value", "tax_amount",
	"amount", "irn", "currency"}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = {"document_type": "Purchase Invoice", "extraction_method": ["is", "set"]}
	if filters.get("from_date") and filters.get("to_date"):
		conditions["creation"] = ["between", [filters.from_date, filters.to_date]]
	if filters.get("party"):
		conditions["party"] = filters.party

	intakes = frappe.get_all("Document Intake", filters=conditions,
		fields=["name", "party", "tax_id", "confidence", "extraction_method"])
	corrected = _corrected_fields([i.name for i in intakes])

	by_party = {}
	for i in intakes:
		key = i.party or i.tax_id or _("(unresolved)")
		row = by_party.setdefault(key, {"party": key, "uploads": 0, "corrected": 0, "fields": 0,
			"confidence": 0.0, "methods": {}})
		fields = corrected.get(i.name, set())
		row["uploads"] += 1
		row["corrected"] += bool(fields)
		row["fields"] += len(fields)
		row["confidence"] += i.confidence or 0
		row["methods"][i.extraction_method] = row["methods"].get(i.extraction_method, 0) + 1

	data = [{**r, "accuracy": 100 * (1 - r["corrected"] / r["uploads"]),
		"confidence": r["confidence"] / r["uploads"],
		"methods": ", ".join(f"{m}: {n}" for m, n in sorted(r["methods"].items()))}
		for r in by_party.values()]
	return _columns(), sorted(data, key=lambda r: r["accuracy"])


def _corrected_fields(names):
	out = {}
	if not names:
		return out
	for v in frappe.get_all("Version", filters={"ref_doctype": "Document Intake", "docname": ["in", names]},
		fields=["docname", "data"]):
		changed = {c[0] for c in (json.loads(v.data or "{}").get("changed") or [])} & EXTRACTED
		if changed:
			out.setdefault(v.docname, set()).update(changed)
	return out


def _columns():
	return [
		{"label": _("Supplier"), "fieldname": "party", "fieldtype": "Data", "width": 220},
		{"label": _("Uploads"), "fieldname": "uploads", "fieldtype": "Int", "width": 90},
		{"label": _("Corrected Invoices"), "fieldname": "corrected", "fieldtype": "Int", "width": 140},
		{"label": _("Corrected Fields"), "fieldname": "fields", "fieldtype": "Int", "width": 130},
		{"label": _("Accuracy %"), "fieldname": "accuracy", "fieldtype": "Percent", "width": 110},
		{"label": _("Avg Confidence %"), "fieldname": "confidence", "fieldtype": "Percent", "width": 140},
		{"label": _("Extraction Methods"), "fieldname": "methods", "fieldtype": "Data", "width": 220},
	]
