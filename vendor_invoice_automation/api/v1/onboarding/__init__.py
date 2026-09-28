"""Vendor onboarding API: one whitelisted function per requirement point.

    vendor_invoice_automation.api.v1.onboarding.<point_name>

e.g. `.cin_based_company_profile`, `.bank_account_verification`,
`.aadhaar_esign_create_deal`. Every point returns the house `api_response` envelope; a
point TransBnk doesn't cover returns a clean `NOT_AVAILABLE` error instead of 404ing —
call `list_requirement_points()` to see the full list with an `available` flag per
point, grouped by the requirement's 5 stages.

`call_transbnk(endpoint, payload)` / `list_endpoints()` (from `_core.py`) remain the
lower-level escape hatch: call any registry endpoint by key, for anything not worth a
dedicated named point yet.

This module reads and writes no business data of its own — it does not persist
onboarding state, decide pass/fail, or sequence stages. The caller (Jarvis) owns the
vendor record and interprets each raw TransBnk response.
"""

import frappe

from ._core import call_transbnk, list_endpoints
from ._shared import REQUIREMENT_POINTS
from .stage1_business_identification import *  # noqa: F401,F403
from .stage2_statutory_verification import *  # noqa: F401,F403
from .stage3_identity_address_verification import *  # noqa: F401,F403
from .stage4_bank_readiness import *  # noqa: F401,F403
from .stage5_risk_compliance import *  # noqa: F401,F403
from ..response_formatter import api_response

STAGE_LABELS = {
	1: "Vendor & Business Identification",
	2: "Business, Tax & Statutory Verification",
	3: "Vendor Identity, Contact & Address Verification",
	4: "Bank Account & Payment Readiness",
	5: "Risk, Compliance & Final Vendor Approval",
}


@frappe.whitelist()
def list_requirement_points() -> dict:
	"""Every requirement point, grouped by stage, each flagged `available` (has a real
	TransBnk endpoint behind it) or not (returns NOT_AVAILABLE — a documented gap, not
	a bug)."""
	stages = {stage: {"label": label, "points": {}} for stage, label in STAGE_LABELS.items()}
	for point in REQUIREMENT_POINTS:
		stages[point["stage"]]["points"][point["name"]] = {
			"available": point["available"],
			"doc": point["doc"],
		}

	return api_response(success=True, data=stages)
