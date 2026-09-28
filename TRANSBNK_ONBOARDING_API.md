# Vendor Onboarding API (TransBnk) — Contract Spec

Companion to [`PURCHASE_INVOICE_VALIDATION_API.md`](PURCHASE_INVOICE_VALIDATION_API.md).
That file covers validating an *invoice*; this one covers verifying the *vendor* before
any invoice arrives: identity, GST/PAN/MCA, bank account, risk. Both are separate
endpoints families in the same app and are independent — neither calls the other.

Upstream reference for TransBnk's own APIs: [`TRANSBNK_API_REFERENCE.md`](TRANSBNK_API_REFERENCE.md)
(52 documents, 121 endpoints). This spec covers only the proxy we ship over them.

---

## 1. What it does

A **thin, stateless proxy** to TransBnk (trusthub.in). Each requirement point in the
5-stage vendor-onboarding journey is one whitelisted function that forwards your payload
to the matching TransBnk endpoint and returns TransBnk's response unmodified inside the
house envelope.

It does **not**: persist onboarding state, decide pass/fail, sequence the stages, or
interpret responses. The caller (Jarvis) owns the vendor record and reads each raw
TransBnk response itself. Contrast with the invoice API, which returns a verdict.

Read-only by design. Every money-movement product (payouts, beneficiary add, NACH, UPI
Autopay mandates, BBPS, payment links) is deliberately **not** in the allowlist, and so
is card/GPR issuance, which uses a different auth contract.

---

## 2. Configuration — `TransBnk Settings` (Single DocType)

| Field | Notes |
| --- | --- |
| `enabled` | Off = every call returns `TRANSBNK_ERROR` ("TransBnk Settings is disabled.") |
| `environment` | `UAT` (default) or `Production` — picks the base URL |
| `api_key` | Password field. Sent as `x-api-key` on every call. Issued by TransBnk after activation **and IP whitelisting of the server** |
| `uat_base_url` | default `https://sandbox-api.trusthub.in` |
| `prod_base_url` | default `https://api.trusthub.in` |

Only `System Manager` can edit it. The key never appears in a response.

---

## 3. Endpoints

All under `/api/method/vendor_invoice_automation.api.v1.onboarding.<name>`.

**Auth:** unlike `validate_invoice`, these are **not** `allow_guest` — a logged-in Frappe
user (session or API key/secret) is required. **Method:** `POST` only for every point
and for `call_transbnk`; the two discovery calls accept GET. **Rate limit:** 60 calls per
60 seconds per caller, on every point.

### 3a. One function per requirement point (primary interface)

```
POST /api/method/vendor_invoice_automation.api.v1.onboarding.cin_based_company_profile
{ "payload": { …exactly what TransBnk's endpoint expects… } }
```

`payload` is a dict or a JSON string, passed through as the request body — this proxy
does not validate or rename fields; check the TransBnk doc for that endpoint in
[`TRANSBNK_API_REFERENCE.md`](TRANSBNK_API_REFERENCE.md). Omitted = `{}`.

Point names are in the tables in §6. Several points share one TransBnk endpoint on
purpose (e.g. `gstin_active_status_validator` and `gst_taxpayer_status_lite` both hit
`/gstin-validation`) because the requirement lists them separately.

### 3b. Points with no TransBnk API — `NOT_AVAILABLE`

39 of the 118 points have nothing behind them (company-name→CIN, PAN→CIN, AML/PEP,
credit-bureau CRIF/Equifax, TAN, LEI, e-way bill, liveness, video KYC, …). They still
exist as callable functions and return a clean error instead of a 404, so a caller
branches on them like any other result:

```json
{ "status": "error", "message": "PAN to CIN Lookup: no TransBnk API for this in the current doc set.",
  "error_code": "NOT_AVAILABLE", "timestamp": "…" }
```

These are gaps to source from another vendor — do not fake them.

### 3c. `list_requirement_points()` — discovery

```
GET /api/method/vendor_invoice_automation.api.v1.onboarding.list_requirement_points
```
Returns every point grouped by stage, each with `available: true|false` and its doc
string. **Authoritative and live** — prefer it over the static tables below, which are a
snapshot.

### 3d. `call_transbnk(endpoint, payload)` — generic escape hatch

```
POST /api/method/vendor_invoice_automation.api.v1.onboarding.call_transbnk
{ "endpoint": "pan_basic", "payload": { "isUserConsent": "y", "panId": "AAIPM3854E" } }
```
`endpoint` must be a key in the allowlist (`integrations/transbnk_endpoints.py`); anything
else is refused **before** a request leaves the server, which is the only guard against
the site's API key being used for a product this proxy wasn't reviewed for. Unknown key →
`UNKNOWN_ENDPOINT`.

### 3e. `list_endpoints()` — the allowlist

```
GET /api/method/vendor_invoice_automation.api.v1.onboarding.list_endpoints
```
Returns `{stage: {label, endpoints: {key: description}}}` for the raw allowlist used by
`call_transbnk`.

---

## 4. Response

Success — TransBnk's body, untouched, under `data`:
```json
{ "status": "success", "data": { …TransBnk's response… }, "timestamp": "2026-09-24 10:12:03" }
```

Failure:
```json
{ "status": "error", "message": "TransBnk /pan-details returned 401: {…}",
  "error_code": "TRANSBNK_ERROR", "timestamp": "…" }
```

| `error_code` | When |
| --- | --- |
| `TRANSBNK_ERROR` | Settings disabled or no key; network failure / 30 s timeout; non-JSON body; any non-2xx from TransBnk (body included in `message`) |
| `NOT_AVAILABLE` | The point has no TransBnk endpoint (§3b) |
| `UNKNOWN_ENDPOINT` | `call_transbnk` given a key outside the allowlist |

`status: "success"` means **the HTTP call worked**, not that the vendor passed. A PAN
that TransBnk reports as invalid is still `success` — read `data`. Never gate an
onboarding decision on `status` alone.

---

## 5. Stages

| # | Stage |
| --- | --- |
| 1 | Vendor & Business Identification |
| 2 | Business, Tax & Statutory Verification |
| 3 | Vendor Identity, Contact & Address Verification |
| 4 | Bank Account & Payment Readiness |
| 5 | Risk, Compliance & Final Vendor Approval |

Stages are labels for grouping and discovery only. Nothing enforces order or completion;
sequencing is the caller's job.

---

## 6. Point catalog (snapshot — `list_requirement_points()` is live truth)

118 points: **79 available**, **39 gaps**. Paths are TransBnk's, appended to the
environment base URL. Method is `POST` unless shown.

### Stage 1 — Vendor & Business Identification

| Point | TransBnk path | Available |
| --- | --- | --- |
| `company_name_to_cin_lookup` | — | **gap** |
| `cin_based_company_profile` | `/cin-validation` | yes |
| `cin_to_pan_lookup` | — | **gap** |
| `pan_to_cin_lookup` | — | **gap** |
| `pan_to_gst_registration_mapper` | `/pan2gstin-search` | yes |
| `pan_to_udyam_details_lookup` | — | **gap** |
| `mobile_to_udyam_details_lookup` | `/mobile-to-udyam` | yes |
| `udyam_to_udyam_details` | `/udyam-verification` | yes |
| `gst_taxpayer_lookup_basic` | `/gstin-validation` | yes |
| `gst_to_mobile_number_lookup` | — | **gap** |
| `mobile_to_gstin_lookup` | — | **gap** |
| `mca_director_din_profile` | `/cin-validation` | yes |
| `pan_to_director_din_lookup` | — | **gap** |
| `business_pan_verification` | `/pan-details` | yes |
| `lei_entity_identifier_lookup` | — | **gap** |
| `llp_verification` | — | **gap** |
| `global_company_search_and_profile` | — | **gap** |

### Stage 2 — Business, Tax & Statutory Verification

| Point | TransBnk path | Available |
| --- | --- | --- |
| `gstin_active_status_validator` | `/gstin-validation` | yes |
| `gstin_deep_profile_validation` | `/gstin-advancedvalidation` | yes |
| `gst_taxpayer_status_lite` | `/gstin-validation` | yes |
| `gst_einvoice_authenticity_check` | `/gstin-advancedvalidation` | yes |
| `gst_eway_bill_status` | — | **gap** |
| `hsn_code_lookup_from_gstin` | `/gstin-validation` | yes |
| `fssai_license_verification` | `/fssai-verification` | yes |
| `business_tan_verification` | — | **gap** |
| `gst_financial_analytics_via_account_aggregator_generate_url` | `/aa-generate-url` | yes |
| `gst_financial_analytics_via_account_aggregator_status_check` | `/aa-status-check` | yes |
| `gst_financial_analytics_via_account_aggregator_retrieve_report` | `/aa-retrieve-report` | yes |
| `udyam_verification_apis` | `/udyam-verification` | yes |
| `industry_specific_licence_verification` | — | **gap** |

### Stage 3 — Vendor Identity, Contact & Address Verification

| Point | TransBnk path | Available |
| --- | --- | --- |
| `pan_basic_lite_verification` | `/pan-details` | yes |
| `pan_advanced_verification` | `/pan-advanced-2` | yes |
| `pan_comprehensive_kyc` | `/pan-supreme-v2` | yes |
| `pan_based_kyc_verification` | `/pan-advanced-2` | yes |
| `pan_to_name_and_dob_lookup` | `/pan-advanced-2` | yes |
| `pan_to_father_name_lookup` | `/pan-supreme-v2` | yes |
| `pan_demographic_verification` | `/pan-advanced-2` | yes |
| `phone_to_pan_verification` | `/mobile-to-pan` | yes |
| `ckyc_identity_fetch` | `/ckyc-search-2` | yes |
| `ckyc_download` | `/ckyc-download-2` | yes |
| `digilocker_kyc_session_launcher` | `/digilocker-kyc-generate-url` | yes |
| `aadhaar_offline_kyc_initiate_otp` | `/okyc-initiate-otp` | yes |
| `aadhaar_offline_kyc_resend_otp` | `/okyc-resend-otp` | yes |
| `aadhaar_offline_kyc_submit_otp` | `/okyc-submit-otp` | yes |
| `aadhaar_offline_kyc_via_digilocker_get_details` | `/digilocker-kyc-get-details` | yes |
| `aadhaar_offline_kyc_via_digilocker_list_docs` | `/digilocker-list-docs` | yes |
| `pan_aadhaar_linkage_verification` | `/pan2aadhaar-search` | yes |
| `mobile_number_verification_consent_initiate_otp` | `/mobnvalid-initiate-otp` | yes |
| `mobile_number_verification_consent_submit_otp` | `/mobnvalid-submit-otp` | yes |
| `mobile_number_verification_consent_get_status` | `/mobnvalid-get-status` | yes |
| `mobile_number_verification_no_consent` | `/mobile-number-validation` | yes |
| `mobile_subscriber_name` | `/mobile-name-match` | yes |
| `mobile_based_profile_prefill` | `/mobile-to-prefill` | yes |
| `mobile_to_physical_address_lookup` | `/mobile-to-prefill` | yes |
| `address_to_lat_long` | `/addr2latlong` | yes |
| `lat_long_to_address` | `/latlong2addr` | yes |
| `coordinate_distance` | `/2pt-distance` | yes |
| `electricity_account_verification` | `/electricity-bill` | yes |
| `electricity_operator_codes` | `/electricity-operator-code (GET)` | yes |
| `lpg_verification` | `/lpg-mv` | yes |
| `driving_license_verification` | `/dl-advance` | yes |
| `voter_id_verification` | `/voter-details` | yes |
| `smart_document_ocr_extraction` | — | **gap** |
| `document_type_classification` | — | **gap** |
| `face_match_verification` | `/face-match` | yes |
| `face_liveness_check` | — | **gap** |
| `video_kyc` | — | **gap** |

### Stage 4 — Bank Account & Payment Readiness

| Point | TransBnk path | Available |
| --- | --- | --- |
| `bank_account_verification` | `/bank-validateacct` | yes |
| `bank_account_verification_status` | `/bank-validateacct-status` | yes |
| `pan_vs_bank_identity_match` | `/bank-validateacct` | yes |
| `ifsc_smart_discovery` | — | **gap** |
| `ifsc_code_validator` | — | **gap** |
| `mobile_to_bank_account` | — | **gap** |
| `mobile_to_upi_address` | `/mobile2vpa` | yes |
| `mobile_to_multiple_vpa_lookup` | `/mobile2vpa` | yes |
| `vpa_to_name_lookup` | `/upiap-validate-vpa` | yes |
| `vpa_to_ifsc_and_name_match` | `/upiap-validate-vpa` | yes |
| `bank_statement_analyzer` | `/bank-stmt-2` | yes |
| `bank_statement_analyzer_status` | `/bank-status` | yes |
| `aa_powered_bank_statement_analyzer_generate_url` | `/aa-generate-url` | yes |
| `aa_powered_bank_statement_analyzer_status_check` | `/aa-status-check` | yes |
| `aa_powered_bank_statement_analyzer_retrieve_report` | `/aa-retrieve-report` | yes |
| `pdf_bank_statement_analyzer_create_session` | `/bs-create-session` | yes |
| `pdf_bank_statement_analyzer_upload` | `/bs-upload` | yes |
| `pdf_bank_statement_analyzer_analysis` | `/bs-analysis` | yes |
| `pdf_bank_statement_analyzer_check_status` | `/bs-check-status` | yes |
| `pdf_bank_statement_analyzer_retrieve_report` | `/bs-retrieve-report (GET)` | yes |
| `scanned_bank_statement_analyzer` | — | **gap** |

### Stage 5 — Risk, Compliance & Final Vendor Approval

| Point | TransBnk path | Available |
| --- | --- | --- |
| `india_aml_pep_screening` | — | **gap** |
| `global_aml_pep_screening` | — | **gap** |
| `cybercrime_registry_risk_check` | — | **gap** |
| `individual_crime_check` | — | **gap** |
| `money_mule_detection_lite` | — | **gap** |
| `money_mule_detection_advanced` | — | **gap** |
| `ip_based_risk_scoring` | — | **gap** |
| `device_integrity_and_spoof_detection` | — | **gap** |
| `sim_swap_fraud_risk` | — | **gap** |
| `digital_footprint_risk_profiler` | — | **gap** |
| `background_check_submission` | — | **gap** |
| `background_check_status_tracker` | — | **gap** |
| `background_check_report_retrieval` | — | **gap** |
| `court_case_and_litigation_record` | — | **gap** |
| `digital_jurisdictional_police_check` | — | **gap** |
| `industry_fraud_signal_consortium` | — | **gap** |
| `credit_bureau_report_cibil` | `/cibil-report` | yes |
| `credit_bureau_report_experian` | `/experian-report-3` | yes |
| `credit_bureau_report_crif` | — | **gap** |
| `credit_bureau_report_equifax` | — | **gap** |
| `itr_financial_analysis_create_credentials` | `/itr-create-credentials` | yes |
| `itr_financial_analysis_validate_credentials` | `/itr-validate-credentials` | yes |
| `itr_financial_analysis_download_profile` | `/itr-download-profile` | yes |
| `epfo_employment_verification_history` | `/employment-history` | yes |
| `epfo_employment_verification_passbook` | `/get-passbook` | yes |
| `epfo_employment_verification_esic_details` | `/mobile2eisc` | yes |
| `aadhaar_esign_create_deal` | `/docuflow-1call` | yes |
| `aadhaar_esign_deal_status` | `/docuflow-status` | yes |
| `aadhaar_esign_resend_signing_link` | `/docuflow-resend-link` | yes |
| `aadhaar_esign_cancel_deal` | `/docuflow-cancel` | yes |


---

## 7. Caveats

- **Two paths are unverified against a live account:** `itr_download_profile` (source PDF
  had a "fi" ligature; normalized to ASCII `profile`) and `bsa_retrieve_report` (documented
  as GET while everything else is POST). Spot-check both in UAT before relying on them.
- **Some "points" are aliases for a field inside another response**, not a real endpoint
  (HSN from GSTIN, director DIN from CIN, e-invoice mandate status). They share a path
  with the point they piggyback on; read the named field from `data`.
- **`gst_einvoice_authenticity_check` is only a partial match:** it reports whether the
  *supplier* is e-invoice mandated/compliant, not whether a specific IRN is authentic.
  For per-invoice authenticity use the invoice API's e-Invoice block (V-FAKE-02/04),
  which verifies the signed QR.
- **Consent-bearing calls** (PAN, mobile, Aadhaar/DigiLocker flows) carry their own
  consent fields in `payload` (e.g. `isUserConsent`). The proxy does not add or check
  them — the caller is responsible for having obtained consent.
- **PII:** responses contain personal data (PAN, DOB, masked Aadhaar, addresses). Nothing
  is stored by this app; don't log `data` upstream unless you intend to retain it.
- **Card / GPR products need extra headers** (`x-client-id`, `x-username`,
  `x-client-password`) the client does not send — out of scope, see the module docstring
  in `integrations/transbnk_endpoints.py`.
- **Widening the allowlist** (e.g. adding a payout endpoint) is a deliberate review
  decision, not a config change.
