"""Stage 1 — Vendor & Business Identification.

One whitelisted function per line item from the requirement. See `_shared.py` for what
`_endpoint()` / `_unavailable()` do.
"""

from ._shared import _endpoint, _register_stage, _unavailable

company_name_to_cin_lookup = _unavailable(
	"company_name_to_cin_lookup",
	"Company Name to CIN Lookup: no TransBnk API for this in the current doc set. "
	"cin_based_company_profile takes the CIN itself as input, not a company name.",
)

cin_based_company_profile = _endpoint(
	"/cin-validation", "cin_based_company_profile",
	"CIN-Based Company Profile: MCA company master data, charges, and director/signatory "
	"details for a given CIN.",
)

cin_to_pan_lookup = _unavailable(
	"cin_to_pan_lookup",
	"CIN to PAN Lookup: no TransBnk API for this. Verified against the full "
	"cin-validation response schema (company_master_data + charges + "
	"directors_signatory_details) — no PAN field anywhere in it, so there is no way "
	"to derive this from cin_based_company_profile either.",
)

pan_to_cin_lookup = _unavailable(
	"pan_to_cin_lookup",
	"PAN to CIN Lookup: no TransBnk API for this in the current doc set.",
)

pan_to_gst_registration_mapper = _endpoint(
	"/pan2gstin-search", "pan_to_gst_registration_mapper",
	"PAN to GST Registration Mapper: lists all GSTIN(s) linked to a PAN, each with "
	"active/inactive status and state.",
)

pan_to_udyam_details_lookup = _unavailable(
	"pan_to_udyam_details_lookup",
	"PAN to Udyam Details Lookup: no TransBnk API for this in the current doc set. Only "
	"a mobile-number-based Udyam lookup exists — see mobile_to_udyam_details_lookup.",
)

mobile_to_udyam_details_lookup = _endpoint(
	"/mobile-to-udyam", "mobile_to_udyam_details_lookup",
	"Mobile to Udyam Details Lookup: Udyam (MSME) registration number(s) and enterprise "
	"name linked to a mobile number.",
)

udyam_to_udyam_details = _endpoint(
	"/udyam-verification", "udyam_to_udyam_details",
	"Udyam to Udyam Details: verifies a Udyam registration number and returns "
	"enterprise details.",
)

gst_taxpayer_lookup_basic = _endpoint(
	"/gstin-validation", "gst_taxpayer_lookup_basic",
	"GST Taxpayer Lookup - Basic: validates a GSTIN and returns basic taxpayer details "
	"and recent return-filing status.",
)

gst_to_mobile_number_lookup = _unavailable(
	"gst_to_mobile_number_lookup",
	"GST to Mobile Number Lookup: no TransBnk API for this in the current doc set.",
)

mobile_to_gstin_lookup = _unavailable(
	"mobile_to_gstin_lookup",
	"Mobile to GSTIN Lookup: no TransBnk API for this in the current doc set.",
)

mca_director_din_profile = _endpoint(
	"/cin-validation", "mca_director_din_profile",
	"MCA Director DIN Profile: no standalone endpoint, but the same cin-validation call "
	"behind cin_based_company_profile returns directors_signatory_details[] — each "
	"director's DIN (field din_pan), name, and appointment/resignation dates.",
)

pan_to_director_din_lookup = _unavailable(
	"pan_to_director_din_lookup",
	"PAN to Director DIN Lookup: no TransBnk API for this in the current doc set.",
)

business_pan_verification = _endpoint(
	"/pan-details", "business_pan_verification",
	"Business PAN Verification: authenticates a PAN and returns basic holder details.",
)

lei_entity_identifier_lookup = _unavailable(
	"lei_entity_identifier_lookup",
	"LEI Entity Identifier Lookup: no TransBnk API for this in the current doc set.",
)

llp_verification = _unavailable(
	"llp_verification",
	"LLP Verification: no dedicated TransBnk API for this in the current doc set — "
	"cin_based_company_profile may cover an LLPIN if MCA files it identically to a CIN, "
	"unconfirmed.",
)

global_company_search_and_profile = _unavailable(
	"global_company_search_and_profile",
	"Global Company Search & Profile: no TransBnk API for this in the current doc set.",
)

_register_stage(1, globals())
