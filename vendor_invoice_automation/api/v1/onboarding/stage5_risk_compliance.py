"""Stage 5 — Risk, Compliance & Final Vendor Approval.

One whitelisted function per line item from the requirement. See `_shared.py` for what
`_endpoint()` / `_unavailable()` do.
"""

from ._shared import _endpoint, _register_stage, _unavailable

india_aml_pep_screening = _unavailable(
	"india_aml_pep_screening",
	"India AML / PEP Screening: no TransBnk API for this in the current doc set.",
)

global_aml_pep_screening = _unavailable(
	"global_aml_pep_screening",
	"Global AML / PEP Screening: no TransBnk API for this in the current doc set.",
)

cybercrime_registry_risk_check = _unavailable(
	"cybercrime_registry_risk_check",
	"Cybercrime Registry Risk Check: no TransBnk API for this in the current doc set.",
)

individual_crime_check = _unavailable(
	"individual_crime_check",
	"Individual Crime Check: no TransBnk API for this in the current doc set.",
)

money_mule_detection_lite = _unavailable(
	"money_mule_detection_lite",
	"Money Mule Detection - Lite: no TransBnk API for this in the current doc set.",
)

money_mule_detection_advanced = _unavailable(
	"money_mule_detection_advanced",
	"Money Mule Detection - Advanced: no TransBnk API for this in the current doc set.",
)

ip_based_risk_scoring = _unavailable(
	"ip_based_risk_scoring",
	"IP-Based Risk Scoring: no TransBnk API for this in the current doc set.",
)

device_integrity_and_spoof_detection = _unavailable(
	"device_integrity_and_spoof_detection",
	"Device Integrity & Spoof Detection: no TransBnk API for this in the current doc set.",
)

sim_swap_fraud_risk = _unavailable(
	"sim_swap_fraud_risk",
	"SIM Swap Fraud Risk: no dedicated TransBnk API for this. "
	"mobile_number_verification_consent_get_status (stage 3) returns a subscriber "
	"report that may carry SIM/porting fields worth inspecting, but there is no "
	"purpose-built SIM-swap risk score.",
)

digital_footprint_risk_profiler = _unavailable(
	"digital_footprint_risk_profiler",
	"Digital Footprint Risk Profiler: no TransBnk API for this in the current doc set.",
)

background_check_submission = _unavailable(
	"background_check_submission",
	"Background Check Submission: no TransBnk API for this in the current doc set.",
)

background_check_status_tracker = _unavailable(
	"background_check_status_tracker",
	"Background Check Status Tracker: no TransBnk API for this in the current doc set.",
)

background_check_report_retrieval = _unavailable(
	"background_check_report_retrieval",
	"Background Check Report Retrieval: no TransBnk API for this in the current doc set.",
)

court_case_and_litigation_record = _unavailable(
	"court_case_and_litigation_record",
	"Court Case & Litigation Record: no TransBnk API for this in the current doc set.",
)

digital_jurisdictional_police_check = _unavailable(
	"digital_jurisdictional_police_check",
	"Digital Jurisdictional Police Check: no TransBnk API for this in the current doc set.",
)

industry_fraud_signal_consortium = _unavailable(
	"industry_fraud_signal_consortium",
	"Industry Fraud Signal Consortium: no TransBnk API for this in the current doc set.",
)

credit_bureau_report_cibil = _endpoint(
	"/cibil-report", "credit_bureau_report_cibil",
	"Credit Bureau Reports - CIBIL: fetches a CIBIL credit report for an individual.",
)

credit_bureau_report_experian = _endpoint(
	"/experian-report-3", "credit_bureau_report_experian",
	"Credit Bureau Reports - Experian: fetches an Experian credit score and full report.",
)

credit_bureau_report_crif = _unavailable(
	"credit_bureau_report_crif",
	"Credit Bureau Reports - CRIF: no TransBnk API for this in the current doc set.",
)

credit_bureau_report_equifax = _unavailable(
	"credit_bureau_report_equifax",
	"Credit Bureau Reports - Equifax: no TransBnk API for this in the current doc set.",
)

itr_financial_analysis_create_credentials = _endpoint(
	"/itr-create-credentials", "itr_financial_analysis_create_credentials",
	"ITR Financial Analysis - step 1: registers income-tax portal login credentials to "
	"create an ITR client profile.",
)

itr_financial_analysis_validate_credentials = _endpoint(
	"/itr-validate-credentials", "itr_financial_analysis_validate_credentials",
	"ITR Financial Analysis - step 2: validates that the created ITR client profile's "
	"credentials still work.",
)

itr_financial_analysis_download_profile = _endpoint(
	"/itr-download-profile", "itr_financial_analysis_download_profile",
	"ITR Financial Analysis - step 3: downloads the taxpayer's ITR portal profile "
	"(address, PAN details, contact, jurisdiction). Path normalized from a 'fi'-ligature "
	"artifact in the source PDF — confirm before relying on it.",
)

epfo_employment_verification_history = _endpoint(
	"/employment-history", "epfo_employment_verification_history",
	"EPFO / Employment Verification - employment history: employer, joining/exit dates "
	"by UAN.",
)

epfo_employment_verification_passbook = _endpoint(
	"/get-passbook", "epfo_employment_verification_passbook",
	"EPFO / Employment Verification - EPF passbook: employer establishment details plus "
	"monthly contributions by UAN.",
)

epfo_employment_verification_esic_details = _endpoint(
	"/mobile2eisc", "epfo_employment_verification_esic_details",
	"EPFO / Employment Verification - ESIC details: employer, UAN, bank, and dispensary "
	"details by mobile number. Not named explicitly in the requirement but the same "
	"employment-verification family as the two functions above.",
)

aadhaar_esign_create_deal = _endpoint(
	"/docuflow-1call", "aadhaar_esign_create_deal",
	"Aadhaar eSign / Digital Signature - create deal: creates a multi-party e-sign deal "
	"for final vendor documentation/agreement execution.",
)

aadhaar_esign_deal_status = _endpoint(
	"/docuflow-status", "aadhaar_esign_deal_status",
	"Aadhaar eSign / Digital Signature - status: polls deal/signing status and returns "
	"download links for the (partially) signed document.",
)

aadhaar_esign_resend_signing_link = _endpoint(
	"/docuflow-resend-link", "aadhaar_esign_resend_signing_link",
	"Aadhaar eSign / Digital Signature - resend link: resends the signing link to "
	"pending signatories.",
)

aadhaar_esign_cancel_deal = _endpoint(
	"/docuflow-cancel", "aadhaar_esign_cancel_deal",
	"Aadhaar eSign / Digital Signature - cancel: cancels an in-progress deal.",
)

_register_stage(5, globals())
