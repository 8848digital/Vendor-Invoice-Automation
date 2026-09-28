"""Stage 3 — Vendor Identity, Contact & Address Verification.

One whitelisted function per line item from the requirement. See `_shared.py` for what
`_endpoint()` / `_unavailable()` do.
"""

from ._shared import _endpoint, _register_stage, _unavailable

pan_basic_lite_verification = _endpoint(
	"/pan-details", "pan_basic_lite_verification",
	"PAN Basic / Lite Verification: authenticates a PAN and returns basic holder details. "
	"Same TransBnk endpoint as stage1.business_pan_verification.",
)

pan_advanced_verification = _endpoint(
	"/pan-advanced-2", "pan_advanced_verification",
	"PAN Advanced Verification: detailed KYC data — name parts, DOB, masked "
	"email/phone/Aadhaar.",
)

pan_comprehensive_kyc = _endpoint(
	"/pan-supreme-v2", "pan_comprehensive_kyc",
	"PAN Comprehensive KYC: adds father's name and masked Aadhaar on top of the "
	"advanced tier.",
)

pan_based_kyc_verification = _endpoint(
	"/pan-advanced-2", "pan_based_kyc_verification",
	"PAN-Based KYC Verification: same TransBnk endpoint as pan_advanced_verification; "
	"kept as its own point because the requirement lists it separately.",
)

pan_to_name_and_dob_lookup = _endpoint(
	"/pan-advanced-2", "pan_to_name_and_dob_lookup",
	"PAN to Name & DOB Lookup: no standalone endpoint — same TransBnk call as "
	"pan_advanced_verification, whose response includes fullName/firstName/"
	"middleName/lastName and dob.",
)

pan_to_father_name_lookup = _endpoint(
	"/pan-supreme-v2", "pan_to_father_name_lookup",
	"PAN to Father Name Lookup: no standalone endpoint — same TransBnk call as "
	"pan_comprehensive_kyc, whose response includes fname (father's name).",
)

pan_demographic_verification = _endpoint(
	"/pan-advanced-2", "pan_demographic_verification",
	"PAN Demographic Verification: no standalone endpoint — same TransBnk call as "
	"pan_advanced_verification, whose response includes gender, dob, and address.",
)

phone_to_pan_verification = _endpoint(
	"/mobile-to-pan", "phone_to_pan_verification",
	"Phone to PAN Verification: returns the PAN number linked to a mobile number and name.",
)

ckyc_identity_fetch = _endpoint(
	"/ckyc-search-2", "ckyc_identity_fetch",
	"CKYC Identity Fetch: looks up an individual/entity's CKYC ID and basic KYC details.",
)

ckyc_download = _endpoint(
	"/ckyc-download-2", "ckyc_download",
	"CKYC Download: retrieves the full CKYC record (identity, address, images, document "
	"list) for a CKYC ID.",
)

digilocker_kyc_session_launcher = _endpoint(
	"/digilocker-kyc-generate-url", "digilocker_kyc_session_launcher",
	"DigiLocker KYC Session Launcher: generates a DigiLocker consent/redirect URL.",
)

aadhaar_offline_kyc_initiate_otp = _endpoint(
	"/okyc-initiate-otp", "aadhaar_offline_kyc_initiate_otp",
	"Aadhaar Offline KYC - initiate OTP: triggers a UIDAI OTP to the Aadhaar-linked mobile.",
)

aadhaar_offline_kyc_resend_otp = _endpoint(
	"/okyc-resend-otp", "aadhaar_offline_kyc_resend_otp",
	"Aadhaar Offline KYC - resend OTP: re-triggers the UIDAI OTP (max 2 times, 60s apart).",
)

aadhaar_offline_kyc_submit_otp = _endpoint(
	"/okyc-submit-otp", "aadhaar_offline_kyc_submit_otp",
	"Aadhaar Offline KYC - submit OTP: exchanges the UIDAI OTP for a presigned link to "
	"the Aadhaar XML plus demographic data.",
)

aadhaar_offline_kyc_via_digilocker_get_details = _endpoint(
	"/digilocker-kyc-get-details", "aadhaar_offline_kyc_via_digilocker_get_details",
	"Aadhaar Offline KYC via DigiLocker: fetches Aadhaar-derived demographic KYC details "
	"for a completed DigiLocker session.",
)

aadhaar_offline_kyc_via_digilocker_list_docs = _endpoint(
	"/digilocker-list-docs", "aadhaar_offline_kyc_via_digilocker_list_docs",
	"Aadhaar Offline KYC via DigiLocker - list documents: lists the documents (Aadhaar, "
	"PAN card, etc.) pulled from a user's DigiLocker account.",
)

pan_aadhaar_linkage_verification = _endpoint(
	"/pan2aadhaar-search", "pan_aadhaar_linkage_verification",
	"PAN-Aadhaar Linkage Verification: checks whether a PAN is linked to Aadhaar.",
)

mobile_number_verification_consent_initiate_otp = _endpoint(
	"/mobnvalid-initiate-otp", "mobile_number_verification_consent_initiate_otp",
	"Mobile Number Verification - Consent - initiate OTP.",
)

mobile_number_verification_consent_submit_otp = _endpoint(
	"/mobnvalid-submit-otp", "mobile_number_verification_consent_submit_otp",
	"Mobile Number Verification - Consent - submit OTP.",
)

mobile_number_verification_consent_get_status = _endpoint(
	"/mobnvalid-get-status", "mobile_number_verification_consent_get_status",
	"Mobile Number Verification - Consent - full subscriber report (identity, contact, "
	"device, plan, SIM, billing).",
)

mobile_number_verification_no_consent = _endpoint(
	"/mobile-number-validation", "mobile_number_verification_no_consent",
	"Mobile Number Verification - No Consent: connection/porting/service-provider details "
	"without an OTP flow.",
)

mobile_subscriber_name = _endpoint(
	"/mobile-name-match", "mobile_subscriber_name",
	"Mobile Subscriber Name: name linked to a mobile number, with a fuzzy match score "
	"if a name is supplied.",
)

mobile_based_profile_prefill = _endpoint(
	"/mobile-to-prefill", "mobile_based_profile_prefill",
	"Mobile-Based Profile Prefill: given a mobile number + name, returns the linked PAN "
	"and full PAN-holder profile.",
)

mobile_to_physical_address_lookup = _endpoint(
	"/mobile-to-prefill", "mobile_to_physical_address_lookup",
	"Mobile to Physical Address Lookup: no standalone endpoint — same TransBnk call as "
	"mobile_based_profile_prefill, whose response includes pan_details.address.",
)

address_to_lat_long = _endpoint(
	"/addr2latlong", "address_to_lat_long",
	"Address & Geolocation Verification - address to lat/long: geocodes a free-text "
	"postal address.",
)

lat_long_to_address = _endpoint(
	"/latlong2addr", "lat_long_to_address",
	"Address & Geolocation Verification - lat/long to address: reverse-geocodes "
	"coordinates into a postal address.",
)

coordinate_distance = _endpoint(
	"/2pt-distance", "coordinate_distance",
	"Address & Geolocation Verification - distance: computes the distance in km between "
	"two lat/long pairs.",
)

electricity_account_verification = _endpoint(
	"/electricity-bill", "electricity_account_verification",
	"Electricity Account Verification: fetches electricity-bill/consumer details for a "
	"consumer/CA number. Call electricity_operator_codes first to get the operator_code.",
)

electricity_operator_codes = _endpoint(
	"/electricity-operator-code", "electricity_operator_codes",
	"Electricity Account Verification - operator codes: state-to-operator_code mapping "
	"table needed before calling electricity_account_verification.",
	method="GET",
)

lpg_verification = _endpoint(
	"/lpg-mv", "lpg_verification",
	"LPG Verification: verifies LPG gas-connection details (provider, consumer id/status, "
	"distributor).",
)

driving_license_verification = _endpoint(
	"/dl-advance", "driving_license_verification",
	"Driving License Verification: verifies a DL number + DOB and returns holder details.",
)

voter_id_verification = _endpoint(
	"/voter-details", "voter_id_verification",
	"Voter ID Verification: retrieves electoral-roll details (name, age, gender, "
	"constituency, address).",
)

smart_document_ocr_extraction = _unavailable(
	"smart_document_ocr_extraction",
	"Smart Document OCR / OCR Extraction: no TransBnk API for this in the current doc set.",
)

document_type_classification = _unavailable(
	"document_type_classification",
	"Document Type Classification: no TransBnk API for this in the current doc set.",
)

face_match_verification = _endpoint(
	"/face-match", "face_match_verification",
	"Face Match Verification: compares a selfie/person photo against an ID-card photo.",
)

face_liveness_check = _unavailable(
	"face_liveness_check",
	"Face Liveness Check: no dedicated TransBnk API for this in the current doc set — "
	"face_match_verification compares two photos, it does not attest liveness.",
)

video_kyc = _unavailable(
	"video_kyc",
	"Video KYC, where applicable: no TransBnk API for this in the current doc set.",
)

_register_stage(3, globals())
