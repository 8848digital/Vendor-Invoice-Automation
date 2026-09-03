"""Requirement 8 — ITC validation: Eligible / Blocked / RCM / ISD / Ineligible.

Pure classification. Every input is already on the `GST Inward Supply` row that
india_compliance downloads with GSTR-2A/2B — the government's own determination of
what credit this invoice carries. Re-deriving it from GST rules would be inventing a
second opinion where an authoritative one exists.

Info severity throughout: ITC status is a stamp the invoice carries into the books,
not a reason to reject it. An ineligible invoice is still a valid invoice.
"""

from .base import INFO, PASS, row
from .gst_2b import inward_supply

STAGE = "itc"

ELIGIBLE, BLOCKED, INELIGIBLE = "Eligible", "Blocked", "Ineligible"
RCM, ISD, PROVISIONAL = "RCM", "ISD", "Provisional"

ISD_CLASSIFICATIONS = ("ISD", "ISDA")
ISD_DOC_TYPES = ("ISD Invoice", "ISD Credit Note")


def run(p):
	"""No 2B row means no ITC determination — which V-GST-16 already reports. Repeating
	it here as a second Skipped row told the caller nothing, so this stays quiet."""
	supply = inward_supply(p)
	if not supply:
		return []

	status, why = _classify(supply)
	return [row("V-ITC-01", STAGE, INFO, PASS, why, "an ITC classification", status)]


def _classify(s):
	"""Order matters: RCM and ISD describe *how* the credit is claimed and override
	the plain availability flag, which for a reverse-charge invoice reads as the
	supplier having charged nothing."""
	if s.get("is_reverse_charge"):
		return RCM, "Reverse charge — the credit is claimed after we pay the tax ourselves."

	if s.get("classification") in ISD_CLASSIFICATIONS or s.get("doc_type") in ISD_DOC_TYPES:
		return ISD, "Input Service Distributor document — credit is distributed, not claimed here."

	availability = s.get("itc_availability")
	if availability == "Yes":
		return ELIGIBLE, "ITC is available on this invoice per GSTR-2B."
	if availability == "Temporary":
		return PROVISIONAL, "ITC is provisionally available; GSTN may still revise it."
	if availability == "No":
		reason = s.get("reason_itc_unavailability")
		# GSTN's own reason strings distinguish a blocked credit (section 17(5), POS
		# in another state) from one that has simply lapsed.
		if reason:
			return BLOCKED, f"ITC is not available: {reason}."
		return INELIGIBLE, "ITC is not available on this invoice per GSTR-2B."

	return PROVISIONAL, "GSTR-2B carries no ITC determination for this invoice yet."
