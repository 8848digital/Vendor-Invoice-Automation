"""BRD §13 approval workflow on Purchase Invoice, created **inactive**.

A patch rather than a fixture on purpose: fixtures overwrite on every migrate, which would
switch the workflow back off each time someone activates it, and an active workflow changes
how every Purchase Invoice on the site is saved — that switch is the site owner's to flip.
"""

import frappe

WORKFLOW = "Purchase Invoice Approval"
# ponytail: one threshold for the approval matrix; add transitions per cost center /
# department / vendor category in the Workflow form once finance gives the rules.
FINANCE_REVIEW_ABOVE = 500000

STATES = [  # state, docstatus, role allowed to edit
	("Draft", 0, "Accounts User"),
	("Buyer Review", 0, "Purchase User"),
	("Finance Review", 0, "Accounts Manager"),
	("Accounts Approval", 0, "Accounts Manager"),
	("Approved", 0, "Accounts Manager"),
	("Rejected", 0, "Accounts User"),
	("Posted", 1, "Accounts Manager"),
]

TRANSITIONS = [  # from, action, to, role, condition
	("Draft", "Submit for Review", "Buyer Review", "Accounts User", None),
	("Buyer Review", "Approve", "Accounts Approval", "Purchase User", f"doc.grand_total <= {FINANCE_REVIEW_ABOVE}"),
	("Buyer Review", "Approve", "Finance Review", "Purchase User", f"doc.grand_total > {FINANCE_REVIEW_ABOVE}"),
	("Buyer Review", "Reject", "Rejected", "Purchase User", None),
	("Finance Review", "Approve", "Accounts Approval", "Accounts Manager", None),
	("Finance Review", "Reject", "Rejected", "Accounts Manager", None),
	("Accounts Approval", "Approve", "Approved", "Accounts Manager", None),
	("Accounts Approval", "Reject", "Rejected", "Accounts Manager", None),
	("Approved", "Post", "Posted", "Accounts Manager", None),
	("Rejected", "Review", "Draft", "Accounts User", None),
]

STYLE = {"Approved": "Success", "Posted": "Success", "Rejected": "Danger", "Draft": "Warning"}


def execute():
	for state, _, _ in STATES:
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": state,
				"style": STYLE.get(state, "Primary")}).insert(ignore_permissions=True)
	for action in {t[1] for t in TRANSITIONS}:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": action}).insert(
				ignore_permissions=True)

	if frappe.db.exists("Workflow", WORKFLOW):
		return
	frappe.get_doc({
		"doctype": "Workflow",
		"workflow_name": WORKFLOW,
		"document_type": "Purchase Invoice",
		"workflow_state_field": "workflow_state",
		"is_active": 0,
		"send_email_alert": 0,
		"states": [{"state": s, "doc_status": str(d), "allow_edit": r} for s, d, r in STATES],
		"transitions": [{"state": f, "action": a, "next_state": t, "allowed": r, "condition": c,
			"allow_self_approval": 1} for f, a, t, r, c in TRANSITIONS],
	}).insert(ignore_permissions=True)
