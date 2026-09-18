"""Row-level access for Document Intake: one table holds supplier invoices and employee
receipts, so who sees a row depends on its document_type, not just the doctype.

A user sees a row when they uploaded it, or hold a role allowed for its document_type.
Unmapped types are visible to their uploader and System Managers only.
"""

import frappe

ROLES_BY_TYPE = {
	"Purchase Invoice": {"Accounts User", "Accounts Manager", "Purchase User", "Purchase Manager"},
	"Expense Claim": {"HR User", "HR Manager", "Expense Approver"},
}


def _allowed_types(user):
	roles = set(frappe.get_roles(user))
	return [t for t, allowed in ROLES_BY_TYPE.items() if roles & allowed]


def query_conditions(user=None, doctype="Document Intake"):
	user = user or frappe.session.user
	if user == "Administrator" or "System Manager" in frappe.get_roles(user):
		return ""
	t, who = f"`tab{doctype}`", frappe.db.escape(user)
	mine = f"{t}.uploaded_by = {who} or {t}.owner = {who}" if doctype == "Document Intake" else f"{t}.owner = {who}"
	types = _allowed_types(user)
	if types:
		return f"({mine} or {t}.document_type in ({', '.join(map(frappe.db.escape, types))}))"
	return f"({mine})"


def action_query_conditions(user=None):
	return query_conditions(user, "Intake Action")


def has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if user == "Administrator" or "System Manager" in frappe.get_roles(user):
		return True
	if user in (doc.get("uploaded_by"), doc.get("owner")):
		return True
	return doc.get("document_type") in _allowed_types(user)
