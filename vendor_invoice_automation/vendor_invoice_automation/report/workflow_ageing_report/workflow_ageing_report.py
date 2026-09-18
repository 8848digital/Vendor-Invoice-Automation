# Copyright (c) 2026, 8848 Digital and contributors
# For license information, please see license.txt

"""Draft Purchase Invoices created from an intake, and how long each has sat in its approval
state. Time in state comes from the last Version that changed `workflow_state`."""

import json

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, nowdate

BUCKETS = ((2, "0-2 days"), (5, "3-5 days"), (10, "6-10 days"))


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = {"docstatus": 0, "document_intake": ["is", "set"]}
	if filters.get("workflow_state"):
		conditions["workflow_state"] = filters.workflow_state

	invoices = frappe.get_all("Purchase Invoice", filters=conditions,
		fields=["name", "supplier", "bill_no", "grand_total", "workflow_state", "document_intake", "creation"])
	data = []
	for pi in invoices:
		entered = _entered_state(pi.name) or pi.creation
		in_state = date_diff(nowdate(), getdate(entered))
		data.append({**pi, "in_state_since": getdate(entered), "days_in_state": in_state,
			"total_age": date_diff(nowdate(), getdate(pi.creation)),
			"bucket": next((label for limit, label in BUCKETS if in_state <= limit), "> 10 days")})
	return _columns(), sorted(data, key=lambda r: -r["days_in_state"])


def _entered_state(name):
	for v in frappe.get_all("Version", filters={"ref_doctype": "Purchase Invoice", "docname": name},
		fields=["creation", "data"], order_by="creation desc"):
		if any(c[0] == "workflow_state" for c in json.loads(v.data or "{}").get("changed") or []):
			return v.creation
	return None


def _columns():
	return [
		{"label": _("Purchase Invoice"), "fieldname": "name", "fieldtype": "Link", "options": "Purchase Invoice", "width": 170},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 180},
		{"label": _("Bill No"), "fieldname": "bill_no", "fieldtype": "Data", "width": 120},
		{"label": _("Grand Total"), "fieldname": "grand_total", "fieldtype": "Currency", "width": 120},
		{"label": _("Workflow State"), "fieldname": "workflow_state", "fieldtype": "Data", "width": 140},
		{"label": _("In State Since"), "fieldname": "in_state_since", "fieldtype": "Date", "width": 120},
		{"label": _("Days in State"), "fieldname": "days_in_state", "fieldtype": "Int", "width": 110},
		{"label": _("Ageing"), "fieldname": "bucket", "fieldtype": "Data", "width": 100},
		{"label": _("Total Age (days)"), "fieldname": "total_age", "fieldtype": "Int", "width": 120},
		{"label": _("Document Intake"), "fieldname": "document_intake", "fieldtype": "Link", "options": "Document Intake", "width": 150},
	]
