"""Intake Rule: per document type, switch a check off or change its severity — without a
deploy. The check logic stays in `validations/`; a rule only changes how its row counts.

A disabled check still appears, as Skipped and naming the rule, so nothing reads as a Pass
that never ran.
"""

import frappe

from vendor_invoice_automation.validations.base import SKIP


def apply(document_type, rows):
	rules = {r.check_id: r for r in frappe.get_all("Intake Rule",
		filters={"document_type": document_type}, fields=["name", "check_id", "enabled", "severity"])}
	for r in rows:
		rule = rules.get(r["check_id"])
		if not rule:
			continue
		if not rule.enabled:
			r.update(result=SKIP, unrun=False, message=f"Disabled by Intake Rule {rule.name}. {r['message']}")
		elif rule.severity:
			r["severity"] = rule.severity
	return rows
