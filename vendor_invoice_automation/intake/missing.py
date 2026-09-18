"""BRD §15 Option 2: invoices the supplier filed with GST that never reached us.

Daily. A GSTR-2B row with no Document Intake and no Purchase Invoice becomes a placeholder
intake, "Vendor Invoice Pending Upload"; when the real upload arrives, process_invoice fills
that same record. Placeholders still pending after `via_pending_upload_reminder_days`
(site_config, default 2) email the supplier once.
"""

import frappe
from frappe.utils import add_days, now_datetime, nowdate

from vendor_invoice_automation.api.v1.intake import PLACEHOLDER

LOOKBACK_DAYS = 90


def daily():
	create_placeholders()
	remind_suppliers()


def create_placeholders():
	rows = frappe.get_all("GST Inward Supply",
		filters={"bill_date": [">=", add_days(nowdate(), -LOOKBACK_DAYS)]},
		fields=["name", "supplier_gstin", "bill_no", "bill_date", "company", "company_gstin",
			"taxable_value", "cgst", "sgst", "igst", "cess"])
	for r in rows:
		if not (r.supplier_gstin and r.bill_no):
			continue
		if frappe.db.exists("Document Intake", {"tax_id": r.supplier_gstin, "reference_no": r.bill_no}):
			continue
		if frappe.db.exists("Purchase Invoice", {"supplier_gstin": r.supplier_gstin, "bill_no": r.bill_no}):
			continue
		supplier = frappe.db.get_value("Supplier", {"gstin": r.supplier_gstin}, "name")
		tax = sum((r.get(k) or 0) for k in ("cgst", "sgst", "igst", "cess"))
		frappe.get_doc({
			"doctype": "Document Intake",
			"document_type": "Purchase Invoice",
			"profile": "intake-purchase-invoice",
			"status": PLACEHOLDER,
			"exception_type": "Vendor Invoice Not Received",
			"company": r.company if r.company and frappe.db.exists("Company", r.company) else None,
			"party_type": "Supplier" if supplier else None,
			"party": supplier,
			"tax_id": r.supplier_gstin,
			"reference_no": r.bill_no,
			"reference_date": r.bill_date,
			"taxable_value": r.taxable_value,
			"tax_amount": tax,
			"amount": (r.taxable_value or 0) + tax,
			"inward_supply": r.name,
			"uploaded_by": None,
		}).insert(ignore_permissions=True)
	frappe.db.commit()


def remind_suppliers():
	days = int(frappe.conf.get("via_pending_upload_reminder_days") or 2)
	for intake in frappe.get_all("Document Intake",
		filters={"status": PLACEHOLDER, "reminder_sent_on": ["is", "not set"], "party": ["is", "set"],
			"creation": ["<=", add_days(now_datetime(), -days)]},
		fields=["name", "party", "reference_no", "reference_date", "amount"]):
		email = frappe.db.get_value("Supplier", intake.party, "email_id")
		if not email:
			continue
		frappe.sendmail(
			recipients=[email],
			subject=f"Invoice {intake.reference_no} not yet received",
			message=(f"Dear {intake.party},<br><br>Your invoice <b>{intake.reference_no}</b> dated "
				f"{intake.reference_date} (₹{intake.amount:,.2f}) appears in your GST filing but has not "
				"reached us yet. Please send a copy so we can process it.<br><br>Thank you."),
			reference_doctype="Document Intake",
			reference_name=intake.name,
		)
		frappe.db.set_value("Document Intake", intake.name, "reminder_sent_on", now_datetime())
	frappe.db.commit()
