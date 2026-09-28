"""Curated, read-only TransBnk endpoints for vendor onboarding.

TransBnk's full doc set covers 121 endpoints across 52 products (see
TRANSBNK_API_REFERENCE.md at the repo root for the full analysis). This registry is
the subset actually wired into `api.v1.onboarding.call_transbnk` — the 5-stage
vendor-identity/KYB/bank-readiness journey, nothing else.

Deliberately excluded, on purpose, not by omission:
  - Every money-movement/collection product: Bank Payout, Bulk Payout, Beneficiary
    Add/Status, NACH mandates/presentations, UPI Autopay mandate lifecycle (only its
    read-only VPA-validate call is kept), BBPS, Dynamic QR, DLC, Payment Gateway Link.
    A vendor-onboarding proxy has no business moving money.
  - Card / GPR / Virtual Gift Card issuance: a different TransBnk product line with a
    different auth contract (x-client-id / x-username / x-client-password on top of
    x-api-key) that `integrations.transbnk.call` does not implement.
Widening this registry to any of the above is a deliberate follow-up, not a bug fix.

Two paths here are unverified against a live TransBnk account and should be
spot-checked before production use (both flagged during extraction):
  - `itr_download_profile`: the source PDF renders the path with a "fi" ligature
    glyph (`proﬁle`); normalized to plain ASCII here on the assumption that's a
    PDF-rendering artifact, not the real path.
  - `bsa_retrieve_report`: documented as GET while every other TransBnk endpoint in
    this set is POST; confirm before relying on it.

Requirement items with no matching TransBnk API in this doc set at all (Company
Name -> CIN lookup, PAN -> CIN lookup, CIN -> PAN lookup, PAN -> Director DIN lookup,
LEI lookup, LLP verification, IFSC validator/discovery, mobile-to-bank-account,
mobile-to-GSTIN / GST-to-mobile, business TAN verification, AML/PEP screening,
credit-bureau CRIF/Equifax, background/court-record checks, device-spoof/IP/digital-
footprint risk scoring, e-way bill status, OCR/document-classification, face liveness,
video KYC) are gaps to source from another vendor, not things to fake here. See
api/v1/onboarding/*.py — every such point exists as a callable stub that returns a
NOT_AVAILABLE error, and `list_requirement_points()` gives the live, authoritative
available/gap breakdown; treat that as current, this docstring as a snapshot.

A second pass through the full response schemas (not just endpoint purposes) found
several items that looked like gaps but are actually answered by fields embedded in an
endpoint already listed above — HSN code lookup from GSTIN (gstin-validation's
goods_service.bzgddtls[].hsncd), MCA director DIN profile (cin-validation's
directors_signatory_details[].din_pan), PAN-to-name/DOB/demographic/father's-name
(pan-advanced-2 / pan-supreme-v2 response fields), mobile-to-physical-address
(mobile-to-prefill's pan_details.address), PAN-vs-bank identity match (bank-
validateacct's fuzzyLogicScore, computed server-side against a supplied custName), and
a partial match for GST e-invoice authenticity (gstin-advancedvalidation's
einvoiceStatus/mandatedeInvoice mandate flags, not a per-IRN authenticity check).
These are wired as aliases in the stage modules, not new registry entries.
"""

STAGE_LABELS = {
	1: "Vendor & Business Identification",
	2: "Business, Tax & Statutory Verification",
	3: "Vendor Identity, Contact & Address Verification",
	4: "Bank Account & Payment Readiness",
	5: "Risk, Compliance & Final Vendor Approval",
}

TRANSBNK_ENDPOINTS = {
	# Stage 1 -- Vendor & Business Identification
	"cin_profile": {"path": "/cin-validation", "stage": 1,
		"label": "CIN-based company profile (MCA master data, charges, directors)"},
	"pan_to_gstin": {"path": "/pan2gstin-search", "stage": 1,
		"label": "PAN to GST registration mapper"},
	"gstin_basic": {"path": "/gstin-validation", "stage": 1,
		"label": "GST taxpayer lookup - basic"},
	"udyam_details": {"path": "/udyam-verification", "stage": 1,
		"label": "Udyam registration details"},
	"mobile_to_udyam": {"path": "/mobile-to-udyam", "stage": 1,
		"label": "Mobile number to Udyam details lookup"},
	"pan_basic": {"path": "/pan-details", "stage": 1,
		"label": "Business PAN verification - basic"},
	"mobile_to_pan": {"path": "/mobile-to-pan", "stage": 1,
		"label": "Mobile number to PAN lookup"},
	"mobile_prefill": {"path": "/mobile-to-prefill", "stage": 1,
		"label": "Mobile-based profile prefill (mobile + name -> PAN profile)"},

	# Stage 2 -- Business, Tax & Statutory Verification
	"gstin_advanced": {"path": "/gstin-advancedvalidation", "stage": 2,
		"label": "GSTIN deep profile validation (turnover slab, income, places of business)"},
	"gst_turnover": {"path": "/gst-turnover", "stage": 2,
		"label": "GST turnover (estimated + filed) by GSTIN and financial year"},
	"fssai_verification": {"path": "/fssai-verification", "stage": 2,
		"label": "FSSAI food-license verification"},
	"section_206ab": {"path": "/206ab", "stage": 2,
		"label": "Section 206AB specified-person (higher TDS) compliance check"},

	# Stage 3 -- Vendor Identity, Contact & Address Verification
	"pan_advanced": {"path": "/pan-advanced-2", "stage": 3,
		"label": "PAN advanced KYC (name parts, DOB, masked email/phone/Aadhaar)"},
	"pan_supreme": {"path": "/pan-supreme-v2", "stage": 3,
		"label": "PAN comprehensive KYC (adds father's name, masked Aadhaar)"},
	"pan_to_aadhaar": {"path": "/pan2aadhaar-search", "stage": 3,
		"label": "PAN-Aadhaar linkage verification"},
	"ckyc_search": {"path": "/ckyc-search-2", "stage": 3,
		"label": "CKYC identity search (CKYC ID + basic KYC)"},
	"ckyc_download": {"path": "/ckyc-download-2", "stage": 3,
		"label": "CKYC full record download"},
	"digilocker_generate_url": {"path": "/digilocker-kyc-generate-url", "stage": 3,
		"label": "DigiLocker KYC consent/session URL"},
	"digilocker_details": {"path": "/digilocker-kyc-get-details", "stage": 3,
		"label": "DigiLocker demographic KYC details (Aadhaar-derived)"},
	"digilocker_list_docs": {"path": "/digilocker-list-docs", "stage": 3,
		"label": "DigiLocker document list"},
	"aadhaar_okyc_initiate": {"path": "/okyc-initiate-otp", "stage": 3,
		"label": "Aadhaar offline e-KYC - initiate OTP"},
	"aadhaar_okyc_resend": {"path": "/okyc-resend-otp", "stage": 3,
		"label": "Aadhaar offline e-KYC - resend OTP"},
	"aadhaar_okyc_submit": {"path": "/okyc-submit-otp", "stage": 3,
		"label": "Aadhaar offline e-KYC - submit OTP, retrieve XML"},
	"mobile_validation_consent_initiate": {"path": "/mobnvalid-initiate-otp", "stage": 3,
		"label": "Mobile number verification (consent) - initiate OTP"},
	"mobile_validation_consent_submit": {"path": "/mobnvalid-submit-otp", "stage": 3,
		"label": "Mobile number verification (consent) - submit OTP"},
	"mobile_validation_consent_status": {"path": "/mobnvalid-get-status", "stage": 3,
		"label": "Mobile number verification (consent) - full subscriber report"},
	"mobile_validation_no_consent": {"path": "/mobile-number-validation", "stage": 3,
		"label": "Mobile number verification - no consent"},
	"mobile_name_match": {"path": "/mobile-name-match", "stage": 3,
		"label": "Mobile subscriber name / fuzzy name match"},
	"address_geocode": {"path": "/addr2latlong", "stage": 3,
		"label": "Address to latitude/longitude"},
	"latlong_to_address": {"path": "/latlong2addr", "stage": 3,
		"label": "Latitude/longitude to address (reverse geocode)"},
	"two_point_distance": {"path": "/2pt-distance", "stage": 3,
		"label": "Distance in km between two coordinate pairs"},
	"electricity_operator_codes": {"path": "/electricity-operator-code", "stage": 3, "method": "GET",
		"label": "Electricity operator-code list (state -> operator_code, call before electricity_bill)"},
	"electricity_bill": {"path": "/electricity-bill", "stage": 3,
		"label": "Electricity account verification"},
	"lpg_verification": {"path": "/lpg-mv", "stage": 3,
		"label": "LPG gas connection verification"},
	"driving_license": {"path": "/dl-advance", "stage": 3,
		"label": "Driving license verification"},
	"voter_id": {"path": "/voter-details", "stage": 3,
		"label": "Voter ID (EPIC) verification"},
	"face_match": {"path": "/face-match", "stage": 3,
		"label": "Face match (selfie vs ID photo)"},

	# Stage 4 -- Bank Account & Payment Readiness
	"bank_account_validate": {"path": "/bank-validateacct", "stage": 4,
		"label": "Bank account validation (penny-drop / UPI / reverse-VPA) with name match score"},
	"bank_account_validate_status": {"path": "/bank-validateacct-status", "stage": 4,
		"label": "Bank account validation - async status"},
	"mobile_to_vpa": {"path": "/mobile2vpa", "stage": 4,
		"label": "Mobile number to UPI VPA(s) lookup"},
	"vpa_validate": {"path": "/upiap-validate-vpa", "stage": 4,
		"label": "VPA validation (name-at-VPA lookup)"},
	"bank_statement_analysis": {"path": "/bank-stmt-2", "stage": 4,
		"label": "Bank statement analyzer - submit for cashflow/income analysis"},
	"bank_statement_analysis_status": {"path": "/bank-status", "stage": 4,
		"label": "Bank statement analyzer - status and KPIs/risk score"},
	"bank_statement_raw": {"path": "/bank-stmt", "stage": 4,
		"label": "Raw bank statement transaction lines (max 30 days)"},
	"bank_balance": {"path": "/bank-balance", "stage": 4,
		"label": "Real-time bank account balance"},
	"bank_institution_list": {"path": "/bank-institution-list", "stage": 4,
		"label": "Supported bank/institution list for AA and statement flows"},
	"aa_generate_url": {"path": "/aa-generate-url", "stage": 4,
		"label": "Account Aggregator - generate consent URL"},
	"aa_status_check": {"path": "/aa-status-check", "stage": 4,
		"label": "Account Aggregator - transaction status"},
	"aa_retrieve_report": {"path": "/aa-retrieve-report", "stage": 4,
		"label": "Account Aggregator - retrieve bank-transactions report"},
	"bsa_create_session": {"path": "/bs-create-session", "stage": 4,
		"label": "PDF/scanned bank statement analyzer (FinEye) - create session"},
	"bsa_upload": {"path": "/bs-upload", "stage": 4,
		"label": "PDF/scanned bank statement analyzer - upload statement PDF"},
	"bsa_analysis": {"path": "/bs-analysis", "stage": 4,
		"label": "PDF/scanned bank statement analyzer - run analysis"},
	"bsa_check_status": {"path": "/bs-check-status", "stage": 4,
		"label": "PDF/scanned bank statement analyzer - processing status"},
	"bsa_retrieve_report": {"path": "/bs-retrieve-report", "stage": 4, "method": "GET",
		"label": "PDF/scanned bank statement analyzer - retrieve report (unverified method, see module docstring)"},

	# Stage 5 -- Risk, Compliance & Final Vendor Approval
	"cibil_report": {"path": "/cibil-report", "stage": 5,
		"label": "CIBIL credit report"},
	"experian_report": {"path": "/experian-report-3", "stage": 5,
		"label": "Experian credit report"},
	"itr_create_credentials": {"path": "/itr-create-credentials", "stage": 5,
		"label": "ITR - register income-tax portal credentials"},
	"itr_validate_credentials": {"path": "/itr-validate-credentials", "stage": 5,
		"label": "ITR - validate registered portal credentials"},
	"itr_download_profile": {"path": "/itr-download-profile", "stage": 5,
		"label": "ITR - download taxpayer portal profile (path normalized, see module docstring)"},
	"employment_history": {"path": "/employment-history", "stage": 5,
		"label": "EPFO employment history"},
	"epf_passbook": {"path": "/get-passbook", "stage": 5,
		"label": "EPF passbook by UAN"},
	"esic_details": {"path": "/mobile2eisc", "stage": 5,
		"label": "ESIC registration details by mobile"},
	"esign_create_deal": {"path": "/docuflow-1call", "stage": 5,
		"label": "Create e-sign deal for final vendor agreement"},
	"esign_deal_status": {"path": "/docuflow-status", "stage": 5,
		"label": "E-sign deal - status and signed-document links"},
	"esign_resend_link": {"path": "/docuflow-resend-link", "stage": 5,
		"label": "E-sign deal - resend signing link"},
	"esign_cancel_deal": {"path": "/docuflow-cancel", "stage": 5,
		"label": "E-sign deal - cancel"},
}
