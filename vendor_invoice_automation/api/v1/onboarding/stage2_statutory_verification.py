"""Stage 2 — Business, Tax & Statutory Verification.

One whitelisted function per line item from the requirement. See `_shared.py` for what
`_endpoint()` / `_unavailable()` do.
"""

from ._shared import _endpoint, _register_stage, _unavailable

gstin_active_status_validator = _endpoint(
	"/gstin-validation", "gstin_active_status_validator",
	"GSTIN Active Status Validator: validates a GSTIN and returns its active/inactive "
	"status and basic taxpayer details. Same TransBnk endpoint as "
	"stage1.gst_taxpayer_lookup_basic.",
)

gstin_deep_profile_validation = _endpoint(
	"/gstin-advancedvalidation", "gstin_deep_profile_validation",
	"GSTIN Deep Profile Validation: superset of the basic validator — adds annual "
	"turnover slab, gross income, and all registered business places.",
)

gst_taxpayer_status_lite = _endpoint(
	"/gstin-validation", "gst_taxpayer_status_lite",
	"GST Taxpayer Status - Lite: same TransBnk endpoint as gstin_active_status_validator; "
	"kept as its own point because the requirement lists it separately.",
)

gst_einvoice_authenticity_check = _endpoint(
	"/gstin-advancedvalidation", "gst_einvoice_authenticity_check",
	"GST e-Invoice Authenticity Check: partial match, not a literal per-invoice/IRN "
	"authenticity check (no such endpoint exists). gstin-advancedvalidation returns "
	"einvoiceStatus and mandatedeInvoice for the GSTIN itself — whether the supplier is "
	"mandated for and currently compliant with e-invoicing, which is the closest "
	"verifiable signal TransBnk offers here.",
)

gst_eway_bill_status = _unavailable(
	"gst_eway_bill_status",
	"GST e-Way Bill Status: no TransBnk API for this in the current doc set.",
)

hsn_code_lookup_from_gstin = _endpoint(
	"/gstin-validation", "hsn_code_lookup_from_gstin",
	"HSN Code Lookup from GSTIN: no standalone endpoint, but the same gstin-validation "
	"call behind gstin_active_status_validator returns result.goods_service.bzgddtls[] "
	"with the registered HSN codes (and bzsdtls[] with SAC codes for services).",
)

fssai_license_verification = _endpoint(
	"/fssai-verification", "fssai_license_verification",
	"FSSAI License Verification: verifies an FSSAI food-license number and returns "
	"validity/status.",
)

business_tan_verification = _unavailable(
	"business_tan_verification",
	"Business TAN Verification: no TransBnk API for this in the current doc set.",
)

gst_financial_analytics_via_account_aggregator_generate_url = _endpoint(
	"/aa-generate-url", "gst_financial_analytics_via_account_aggregator_generate_url",
	"GST Financial Analytics via Account Aggregator - step 1: generate the AA consent "
	"redirect URL.",
)

gst_financial_analytics_via_account_aggregator_status_check = _endpoint(
	"/aa-status-check", "gst_financial_analytics_via_account_aggregator_status_check",
	"GST Financial Analytics via Account Aggregator - step 2: poll the AA transaction "
	"status.",
)

gst_financial_analytics_via_account_aggregator_retrieve_report = _endpoint(
	"/aa-retrieve-report", "gst_financial_analytics_via_account_aggregator_retrieve_report",
	"GST Financial Analytics via Account Aggregator - step 3: download the generated "
	"AA report.",
)

udyam_verification_apis = _endpoint(
	"/udyam-verification", "udyam_verification_apis",
	"Udyam Verification APIs: same TransBnk endpoint as "
	"stage1.udyam_to_udyam_details; kept as its own point because the requirement "
	"lists it separately here.",
)

industry_specific_licence_verification = _unavailable(
	"industry_specific_licence_verification",
	"Industry-specific registration/licence verification, wherever applicable: only "
	"FSSAI is concretely available in the current doc set — see "
	"fssai_license_verification. No general-purpose industry-licence API exists.",
)

_register_stage(2, globals())
