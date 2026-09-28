// Copyright (c) 2026, 8848 Digital and contributors
// For license information, please see license.txt

frappe.ui.form.on("Intake Action", {
	refresh(frm) {
		if (frm.doc.status !== "Pending") return;
		const decide = (decision) =>
			frappe.prompt(
				{ fieldname: "note", fieldtype: "Small Text", label: __("Note") },
				({ note }) =>
					frappe.call({
						method: "vendor_invoice_automation.api.v1.intake.decide_action",
						args: { action: frm.doc.name, decision, note },
						freeze: true,
						callback: () => frm.reload_doc(),
					}),
				__(decision),
				__(decision)
			);
		frm.add_custom_button(__("Approve"), () => decide("Approve")).addClass("btn-primary");
		frm.add_custom_button(__("Reject"), () => decide("Reject"));
	},
});
