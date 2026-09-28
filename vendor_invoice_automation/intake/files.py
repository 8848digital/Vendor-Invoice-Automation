"""What the file itself proves: its hash, its signed QR, and a machine-readable e-invoice.

Deterministic reads only. A value that came out of a signed QR or an e-invoice JSON is ground
truth, and overrides whatever the model transcribed for the same field.
"""

import hashlib
import json
from datetime import datetime

import frappe
from frappe.utils import flt

IMAGE_EXT = {"png", "jpg", "jpeg", "webp", "bmp", "gif", "tif", "tiff"}
QR_PAGES = 2


def read(file_url=None, file_name=None):
	"""{file_url, file_hash, ext, qr_payload, einvoice} for a File the session user may read.

	Jarvis shows the model an attachment's file *name*, so either identifies it; by name, the
	most recent one this user can read wins — the same rule as Jarvis's own read_file.
	"""
	filters = {"file_url": file_url} if file_url else {"file_name": file_name}
	name = next((n for n in frappe.get_all("File", filters=filters, pluck="name", order_by="creation desc", limit=20)
		if frappe.has_permission("File", "read", doc=n)), None)
	if not name:
		frappe.throw(f"No readable File named {file_url or file_name}", frappe.PermissionError)

	fdoc = frappe.get_doc("File", name)
	file_url = fdoc.file_url
	content = fdoc.get_content()
	if isinstance(content, str):
		content = content.encode()
	ext = (fdoc.file_name or file_url).rsplit(".", 1)[-1].lower()

	out = {"file_url": file_url, "file_hash": hashlib.sha256(content).hexdigest(), "ext": ext,
		"qr_payload": None, "einvoice": None}
	if ext == "json":
		out["einvoice"] = parse_einvoice(json.loads(content))
		out["qr_payload"] = (out["einvoice"] or {}).pop("qr_payload", None)
	elif ext == "pdf" or ext in IMAGE_EXT:
		out["qr_payload"] = decode_qr(content, ext)
	return out


def sha256(text):
	return hashlib.sha256(text.encode()).hexdigest() if text else None


def decode_qr(content, ext):
	"""The first QR on the first pages. A JWS-shaped one (the signed e-invoice QR) wins."""
	try:
		import zxingcpp
	except ImportError:
		return None  # ponytail: dependency missing on this bench — QR checks report Skipped instead.

	texts = []
	for image in _images(content, ext):
		texts += [r.text for r in zxingcpp.read_barcodes(image, formats=zxingcpp.BarcodeFormat.QRCode)]
	signed = [t for t in texts if t.count(".") == 2]
	return (signed or texts or [None])[0]


def _images(content, ext):
	import io

	from PIL import Image

	if ext != "pdf":
		yield Image.open(io.BytesIO(content))
		return
	import pypdfium2

	pdf = pypdfium2.PdfDocument(content)
	for i in range(min(len(pdf), QR_PAGES)):
		yield pdf[i].render(scale=3).to_pil()


def parse_einvoice(data):
	"""NIC e-invoice JSON (plain schema, or the signed IRP response) → the invoice payload shape."""
	import jwt

	qr, irn = data.get("SignedQRCode"), data.get("Irn")
	if data.get("SignedInvoice"):
		inner = jwt.decode(data["SignedInvoice"], options={"verify_signature": False})
		data = json.loads(inner["data"]) if isinstance(inner.get("data"), str) else inner.get("data", inner)
	if not data.get("DocDtls"):
		return None

	from india_compliance.gst_india.constants import STATE_NUMBERS

	states = {code: state for state, code in STATE_NUMBERS.items()}
	doc, seller, buyer, val = data["DocDtls"], data.get("SellerDtls", {}), data.get("BuyerDtls", {}), data.get("ValDtls", {})
	pos = buyer.get("Pos")
	po_refs = [c.get("PORefr") for c in (data.get("RefDtls") or {}).get("ContrDtls") or [] if c.get("PORefr")]

	return {
		"supplier": seller.get("LglNm") or seller.get("TrdNm"),
		"supplier_gstin": seller.get("Gstin"),
		"company_gstin": buyer.get("Gstin"),
		"invoice_no": doc.get("No"),
		"invoice_date": str(datetime.strptime(doc["Dt"], "%d/%m/%Y").date()) if doc.get("Dt") else None,
		"place_of_supply": f"{pos}-{states[pos]}" if pos in states else None,
		"po_number": po_refs[0] if po_refs else None,
		"irn": irn or data.get("Irn"),
		"is_reverse_charge": (data.get("TranDtls") or {}).get("RegRev") == "Y",
		"taxable_value": flt(val.get("AssVal")),
		"cgst": flt(val.get("CgstVal")),
		"sgst": flt(val.get("SgstVal")),
		"igst": flt(val.get("IgstVal")),
		"cess": flt(val.get("CesVal")),
		"round_off": flt(val.get("RndOffAmt")),
		"grand_total": flt(val.get("TotInvVal")),
		"qr_payload": qr,
		"items": [{
			"description": i.get("PrdDesc"),
			"hsn_sac": i.get("HsnCd"),
			"qty": flt(i.get("Qty")),
			"uom": i.get("Unit"),
			"rate": flt(i.get("UnitPrice")),
			"amount": flt(i.get("TotAmt") or i.get("AssAmt")),  # gross, so qty x rate = amount holds
			"gst_rate": flt(i.get("GstRt")),
			"tax_amount": flt(i.get("CgstAmt")) + flt(i.get("SgstAmt")) + flt(i.get("IgstAmt")) + flt(i.get("CesAmt")),
		} for i in data.get("ItemList") or []],
	}
