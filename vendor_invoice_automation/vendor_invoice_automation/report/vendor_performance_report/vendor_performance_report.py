# Copyright (c) 2026, 8848 Digital and contributors
# For license information, please see license.txt

"""Per supplier: how clean their invoices arrive, and how late."""

import frappe
from frappe import _
from frappe.utils import date_diff, getdate

EXCEPTIONS = {"OCR Failed", "GST Failed", "PO Failed", "GRN Failed", "Duplicate", "Rejected"}
DONE = {"Workflow", "Approved", "Posted", "Payment Pending", "Paid"}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = {"document_type": "Purchase Invoice", "party": ["is", "set"],
		"status": ["!=", "Vendor Invoice Pending Upload"]}
	if filters.get("from_date") and filters.get("to_date"):
		conditions["reference_date"] = ["between", [filters.from_date, filters.to_date]]

	by_party = {}
	for i in frappe.get_all("Document Intake", filters=conditions,
		fields=["party", "status", "confidence", "reference_date", "creation", "amount"]):
		r = by_party.setdefault(i.party, {"party": i.party, "uploads": 0, "clean": 0, "exceptions": 0,
			"duplicates": 0, "delay": 0, "dated": 0, "amount": 0.0})
		r["uploads"] += 1
		r["clean"] += i.status in DONE
		r["exceptions"] += i.status in EXCEPTIONS
		r["duplicates"] += i.status == "Duplicate"
		r["amount"] += i.amount or 0
		if i.reference_date:
			r["delay"] += max(date_diff(getdate(i.creation), i.reference_date), 0)
			r["dated"] += 1
	pending = {r.party: r.n for r in frappe.get_all("Document Intake",
		filters={"status": "Vendor Invoice Pending Upload", "party": ["is", "set"]},
		fields=["party", "count(name) as n"], group_by="party")}

	data = [{**r, "exception_rate": 100 * r["exceptions"] / r["uploads"],
		"avg_delay": r["delay"] / r["dated"] if r["dated"] else None,
		"not_received": pending.get(r["party"], 0)} for r in by_party.values()]
	return _columns(), sorted(data, key=lambda r: -r["exception_rate"])


def _columns():
	return [
		{"label": _("Supplier"), "fieldname": "party", "fieldtype": "Link", "options": "Supplier", "width": 200},
		{"label": _("Uploads"), "fieldname": "uploads", "fieldtype": "Int", "width": 90},
		{"label": _("Clean"), "fieldname": "clean", "fieldtype": "Int", "width": 80},
		{"label": _("Exceptions"), "fieldname": "exceptions", "fieldtype": "Int", "width": 100},
		{"label": _("Exception Rate %"), "fieldname": "exception_rate", "fieldtype": "Percent", "width": 130},
		{"label": _("Duplicates"), "fieldname": "duplicates", "fieldtype": "Int", "width": 100},
		{"label": _("Avg Upload Delay (days)"), "fieldname": "avg_delay", "fieldtype": "Float", "width": 170},
		{"label": _("Filed in GST, Not Received"), "fieldname": "not_received", "fieldtype": "Int", "width": 190},
		{"label": _("Invoiced Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 140},
	]
