"""Stage 4 — Bank Account & Payment Readiness.

One whitelisted function per line item from the requirement. See `_shared.py` for what
`_endpoint()` / `_unavailable()` do.
"""

from ._shared import _endpoint, _register_stage, _unavailable

bank_account_verification = _endpoint(
	"/bank-validateacct", "bank_account_verification",
	"Bank Account Verification: verifies bank/UPI account ownership via IMPS penny-drop, "
	"penny-less, UPI, or reverse-VPA, returning nameAtBank and a fuzzy match score.",
)

bank_account_verification_status = _endpoint(
	"/bank-validateacct-status", "bank_account_verification_status",
	"Bank Account Verification - status: polls a previously submitted validation request.",
)

pan_vs_bank_identity_match = _endpoint(
	"/bank-validateacct", "pan_vs_bank_identity_match",
	"PAN vs Bank Identity Match: no standalone endpoint — same TransBnk call as "
	"bank_account_verification. Pass the PAN-holder's name (from business_pan_verification "
	"or pan_advanced_verification) as custName; TransBnk itself returns nameAtBank plus a "
	"fuzzyLogicScore against it, so the match is computed server-side, not locally.",
)

ifsc_smart_discovery = _unavailable(
	"ifsc_smart_discovery",
	"IFSC Smart Discovery: no TransBnk API for this in the current doc set.",
)

ifsc_code_validator = _unavailable(
	"ifsc_code_validator",
	"IFSC Code Validator: no TransBnk API for this in the current doc set.",
)

mobile_to_bank_account = _unavailable(
	"mobile_to_bank_account",
	"Mobile to Bank Account: no direct TransBnk API for this. The closest available flow "
	"is bank_account_verification's REVERSE/REVERSE_INTENT txnType, which resolves a VPA "
	"(not a mobile number) to an account.",
)

mobile_to_upi_address = _endpoint(
	"/mobile2vpa", "mobile_to_upi_address",
	"Mobile-to-UPI Address: looks up the UPI VPA(s) linked to a mobile number.",
)

mobile_to_multiple_vpa_lookup = _endpoint(
	"/mobile2vpa", "mobile_to_multiple_vpa_lookup",
	"Mobile to Multiple VPA Lookup: same TransBnk endpoint as mobile_to_upi_address, "
	"which already returns every VPA linked to the number.",
)

vpa_to_name_lookup = _endpoint(
	"/upiap-validate-vpa", "vpa_to_name_lookup",
	"VPA to Name Lookup: validates a UPI VPA and returns the linked account-holder's "
	"masked name.",
)

vpa_to_ifsc_and_name_match = _endpoint(
	"/upiap-validate-vpa", "vpa_to_ifsc_and_name_match",
	"VPA to IFSC & Name Match: same TransBnk endpoint as vpa_to_name_lookup, whose "
	"response includes vpaIfscCode alongside vpaMaskedName/payerName — confirmed present, "
	"not just an inference.",
)

bank_statement_analyzer = _endpoint(
	"/bank-stmt-2", "bank_statement_analyzer",
	"Bank Statement Analyzer: submits a base64 bank-statement PDF for automated "
	"cash-flow/income analysis.",
)

bank_statement_analyzer_status = _endpoint(
	"/bank-status", "bank_statement_analyzer_status",
	"Bank Statement Analyzer - status: polls status and retrieves KPIs/cashflow/risk "
	"score once processing completes.",
)

aa_powered_bank_statement_analyzer_generate_url = _endpoint(
	"/aa-generate-url", "aa_powered_bank_statement_analyzer_generate_url",
	"AA-Powered Bank Statement Analyzer - step 1: generate the Account Aggregator "
	"consent redirect URL.",
)

aa_powered_bank_statement_analyzer_status_check = _endpoint(
	"/aa-status-check", "aa_powered_bank_statement_analyzer_status_check",
	"AA-Powered Bank Statement Analyzer - step 2: poll the AA transaction status.",
)

aa_powered_bank_statement_analyzer_retrieve_report = _endpoint(
	"/aa-retrieve-report", "aa_powered_bank_statement_analyzer_retrieve_report",
	"AA-Powered Bank Statement Analyzer - step 3: download the generated bank-"
	"transactions report.",
)

pdf_bank_statement_analyzer_create_session = _endpoint(
	"/bs-create-session", "pdf_bank_statement_analyzer_create_session",
	"PDF Bank Statement Analyzer - step 1: opens a FinEye analysis session for a "
	"borrower + document type.",
)

pdf_bank_statement_analyzer_upload = _endpoint(
	"/bs-upload", "pdf_bank_statement_analyzer_upload",
	"PDF Bank Statement Analyzer - step 2: uploads a base64 bank-statement PDF against "
	"the session.",
)

pdf_bank_statement_analyzer_analysis = _endpoint(
	"/bs-analysis", "pdf_bank_statement_analyzer_analysis",
	"PDF Bank Statement Analyzer - step 3: kicks off analysis of all documents uploaded "
	"under the session.",
)

pdf_bank_statement_analyzer_check_status = _endpoint(
	"/bs-check-status", "pdf_bank_statement_analyzer_check_status",
	"PDF Bank Statement Analyzer - step 4: polls processing status.",
)

pdf_bank_statement_analyzer_retrieve_report = _endpoint(
	"/bs-retrieve-report", "pdf_bank_statement_analyzer_retrieve_report",
	"PDF Bank Statement Analyzer - step 5: fetches presigned XLSX/JSON report links. "
	"Documented as GET in the source PDF while every sibling TransBnk endpoint is POST — "
	"confirm before relying on it.",
	method="GET",
)

scanned_bank_statement_analyzer = _unavailable(
	"scanned_bank_statement_analyzer",
	"Scanned Bank Statement Analyzer: not a separate endpoint — the same FinEye pipeline "
	"behind pdf_bank_statement_analyzer_create_session/_upload/_analysis handles scanned "
	"PDFs too. Use those.",
)

_register_stage(4, globals())
