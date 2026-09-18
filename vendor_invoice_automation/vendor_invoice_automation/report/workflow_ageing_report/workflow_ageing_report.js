// Copyright (c) 2026, 8848 Digital and contributors
// For license information, please see license.txt

frappe.query_reports["Workflow Ageing Report"] = {
	filters: [
		{ fieldname: "workflow_state", label: __("Workflow State"), fieldtype: "Link", options: "Workflow State" },
	],
};
