"""Requirement 8 — IRN Valid / QR Valid / GST Number Match / Invoice Date Valid.

The supplier's printed QR is a JWS signed by NIC. It is the only way to verify a
*supplier's* IRN: NIC's `GetIRNDetails` authenticates as the caller's own GSTIN and
is scoped to invoices that caller generated — india_compliance's own client treats
`2283: "IRN details cannot be provided as it is generated more than 2 days ago"` as
an expected error (api_classes/nic/e_invoice.py). So the QR, offline, is the check.

Two separate things happen here, and conflating them would be a security bug:

    decode   reads the claims. Proves nothing about authenticity — anyone can mint
             a JWS. It does prove the *printed* document agrees with its own QR,
             which is what catches an altered invoice.
    verify   checks NIC's RSA signature. This is the part that proves the invoice
             is genuine, and it needs NIC's public certificate on file.

Decode always runs. Verification runs only when a certificate is configured, and
says so plainly when it is not.
"""

import json
from datetime import datetime

import frappe
from frappe.utils import flt, getdate

from .base import (
	ERROR,
	FAIL,
	MONETARY_AGREEMENT_TOLERANCE,
	PASS,
	SKIP,
	WARN,
	nic_public_certificate,
	row,
	verdict,
)

STAGE = "einvoice"


def run(p):
	"""Everything here hangs off the QR. When there is none, or it will not decode, one
	row says so — five rows repeating the same sentence told the caller nothing extra.
	"""
	qr = p.get("qr_payload")
	if not qr:
		# Legitimate: suppliers under the e-invoice turnover threshold issue no IRN.
		return [row("V-FAKE-02", STAGE, ERROR, SKIP,
			"No `qr_payload`, so the IRN, QR and GSTIN-match checks (V-FAKE-04, "
			"V-GST-08/09/10) do not apply. Expected for a supplier below the e-invoice "
			"mandate; Jarvis sends the raw signed QR string when one is present.")]

	claims, error = _decode(qr)
	if error:
		return [row("V-FAKE-02", STAGE, ERROR, FAIL,
			f"QR payload is not a readable e-invoice JWS: {error}",
			"a signed NIC QR", qr[:40] + "…")]

	return [
		_signature(qr),
		_agrees_with_document(p, claims),
		_seller_gstin(p, claims),
		_buyer_gstin(p, claims),
		_irn(p, claims),
	]


def _decode(qr):
	"""The JWS `data` claim is itself a JSON string — india_compliance's own idiom
	(gst_india/utils/e_invoice.py:333). Returns (claims, error)."""
	import jwt

	try:
		payload = jwt.decode(qr, options={"verify_signature": False})
		return frappe._dict(json.loads(payload["data"])), None
	except Exception as e:
		return None, frappe.utils.strip_html(str(e)) or type(e).__name__


def _signature(qr):
	"""V-FAKE-02 — the half that proves authenticity."""
	cert = nic_public_certificate()
	if not cert:
		return row("V-FAKE-02", STAGE, ERROR, SKIP,
			"No NIC public certificate in Vendor Invoice Settings, so the QR signature "
			"cannot be verified. The field checks below still compare the QR against the "
			"printed document — they catch alteration, not forgery.")

	import jwt
	from cryptography import x509
	from cryptography.hazmat.backends import default_backend

	try:
		public_key = x509.load_pem_x509_certificate(cert.encode(), default_backend()).public_key()
		jwt.decode(qr, key=public_key, algorithms=["RS256"])
	except Exception as e:
		return row("V-FAKE-02", STAGE, ERROR, FAIL,
			f"QR signature does not verify against NIC's certificate: "
			f"{frappe.utils.strip_html(str(e)) or type(e).__name__}",
			"a signature from NIC", "invalid")
	return row("V-FAKE-02", STAGE, ERROR, PASS,
		"QR signature verifies against NIC's certificate — the IRN is genuine.")


def _agrees_with_document(p, c):
	"""V-FAKE-04 — every header value the QR carries, against what was read off the
	page. A disagreement means the printed invoice was altered after signing."""
	tol = MONETARY_AGREEMENT_TOLERANCE
	off = []

	if c.DocNo and str(c.DocNo) != str(p.get("invoice_no") or ""):
		off.append(f"invoice no: QR {c.DocNo} vs document {p.get('invoice_no')}")
	if c.TotInvVal is not None and abs(flt(c.TotInvVal) - flt(p.get("grand_total"))) > tol:
		off.append(f"total: QR {flt(c.TotInvVal):.2f} vs document {flt(p.get('grand_total')):.2f}")
	if (qr_date := _qr_date(c.DocDt)) and p.get("invoice_date") \
		and qr_date != getdate(p["invoice_date"]):
		off.append(f"date: QR {qr_date} vs document {p.get('invoice_date')}")

	return row("V-FAKE-04", STAGE, ERROR, verdict(not off),
		"QR disagrees with the printed invoice — the document was altered after signing." if off
		else "Every header value on the QR matches the printed invoice.",
		"QR and document agree", off or None)


def _qr_date(doc_dt):
	"""NIC stamps DocDt as DD/MM/YYYY, which `getdate` would read as MM/DD."""
	try:
		return datetime.strptime(str(doc_dt), "%d/%m/%Y").date()
	except (TypeError, ValueError):
		return None


def _seller_gstin(p, c):
	"""V-GST-08 — GST Number Match, supplier side."""
	if not c.SellerGstin:
		return row("V-GST-08", STAGE, ERROR, SKIP, "QR carries no SellerGstin.")
	ok = c.SellerGstin == p.get("supplier_gstin")
	return row("V-GST-08", STAGE, ERROR, verdict(ok),
		"Supplier GSTIN on the QR matches the invoice." if ok
		else "Supplier GSTIN on the QR is not the GSTIN read off the invoice.",
		c.SellerGstin, p.get("supplier_gstin"))


def _buyer_gstin(p, c):
	"""V-GST-09 — GST Number Match, buyer side. An invoice signed to somebody else's
	GSTIN is not ours to book, whatever it says on the page."""
	if not c.BuyerGstin:
		return row("V-GST-09", STAGE, ERROR, SKIP, "QR carries no BuyerGstin.")
	ok = c.BuyerGstin == p.get("company_gstin")
	return row("V-GST-09", STAGE, ERROR, verdict(ok),
		"The e-invoice was issued to our buyer GSTIN." if ok
		else "The e-invoice was issued to a different buyer GSTIN.",
		c.BuyerGstin, p.get("company_gstin"))


def _irn(p, c):
	"""V-GST-10 — the IRN the payload claims is the IRN inside the signed QR."""
	if not c.Irn:
		return row("V-GST-10", STAGE, ERROR, FAIL,
			"QR decoded but carries no IRN.", "an IRN", None)
	if not p.get("irn"):
		return row("V-GST-10", STAGE, WARN, PASS,
			"No IRN was extracted from the document; taking the QR's.", found=c.Irn)
	ok = c.Irn == p["irn"]
	return row("V-GST-10", STAGE, ERROR, verdict(ok),
		"IRN on the document matches the one inside the signed QR." if ok
		else "IRN read off the document differs from the one inside the signed QR.",
		c.Irn, p.get("irn"))
