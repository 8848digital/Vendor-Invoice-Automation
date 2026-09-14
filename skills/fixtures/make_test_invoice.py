"""Render the synthetic GST tax invoice PNGs for testing /invoice-extract.

Three fixtures, one renderer. See README.md for why these particular values were chosen
and what each one is expected to do to the pipeline.

    clean      → every check that can run, passes
    gst-fail   → intra-state supply charged as IGST      → V-GST-12/13 Fail (Error)
    duplicate  → the supplier's bill for PUR-INV-2026-90365, already booked on the site
                 → V-DUP-01 Fail (Error)
"""

import os

from PIL import Image, ImageDraw, ImageFont

W, H = 1240, 1500                      # A4-ish, trimmed of dead space
BG, INK, MUTED, LINE = "white", "#111111", "#555555", "#cccccc"
ACCENT = "#1f3b73"

R = "/System/Library/Fonts/Supplemental/Arial.ttf"
B = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def f(path, size):
    return ImageFont.truetype(path, size)


F = {"h1": f(B, 40), "h2": f(B, 23), "b": f(B, 19), "n": f(R, 19),
     "s": f(R, 16), "sb": f(B, 16), "tiny": f(R, 14), "big": f(B, 27)}

M = 70
bx = 690

# (#, description, HSN/SAC, qty, uom, rate, amount)
SERVICES = [
    ("1", "Managed hosting - production cluster", "998315", "12", "Month", "4,500.00", "54,000.00"),
    ("2", "On-site engineer support visit", "998713", "6", "Visit", "2,750.00", "16,500.00"),
    ("3", "SSL certificate renewal (wildcard)", "998319", "3", "Nos", "1,200.00", "3,600.00"),
]
# Mirrors Purchase Invoice Item PII-8106f5a112 on PUR-INV-2026-90365, field for field.
GOODS = [
    ("1", "PPR-0802-100", "391740", "10", "Nos", "439.98", "4,399.80"),
]


def render(out_name, invoice_no, invoice_date, due_date, copy_label, reference,
           items, taxable, heads, grand, words, note=None):
    """One invoice. `heads` is the tax lines under Taxable Value — two @9% for an
    intra-state supply, one IGST @18% for the wrong head, none at all for a nil-rated
    supply."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    def txt(x, y, t, k="n", fill=INK, anchor=None):
        d.text((x, y), t, font=F[k], fill=fill, anchor=anchor)

    def rt(x, y, t, k="n", fill=INK):
        d.text((x, y), t, font=F[k], fill=fill, anchor="ra")

    # ── header ───────────────────────────────────────────────────────────
    d.rectangle([0, 0, W, 132], fill=ACCENT)
    txt(M, 34, "ALPHA SYSTEMS LTD", "h1", "white")
    txt(M, 88, "IT Infrastructure & Managed Services", "s", "#c8d4ea")
    rt(W - M, 40, "TAX INVOICE", "h2", "white")
    rt(W - M, 78, copy_label, "tiny", "#c8d4ea")

    y = 165
    txt(M, y, "Unit 402, Solaris Business Park, Andheri East", "s", MUTED)
    txt(M, y + 24, "Mumbai 400069, Maharashtra, India", "s", MUTED)
    txt(M, y + 48, "GSTIN: 27AAACI1195H1ZM", "sb")
    txt(M, y + 72, "PAN: AAACI1195H", "s", MUTED)
    txt(M, y + 96, "State: 27-Maharashtra", "s", MUTED)

    d.rounded_rectangle([bx, y - 14, W - M, y + 118], 8, outline=LINE, width=2)
    rows = [("Invoice No.", invoice_no), ("Invoice Date", invoice_date),
            ("Due Date", due_date), ("Place of Supply", "27-Maharashtra")]
    for i, (k, v) in enumerate(rows):
        txt(bx + 20, y + 4 + i * 28, k, "s", MUTED)
        rt(W - M - 20, y + 4 + i * 28, v, "sb")

    # ── bill to ──────────────────────────────────────────────────────────
    y = 320
    d.line([M, y, W - M, y], fill=LINE, width=2)
    txt(M, y + 20, "BILL TO", "sb", MUTED)
    txt(M, y + 48, "8848 DIGITAL", "b")
    txt(M, y + 78, "7th Floor, Tower B, Cyber Park", "s", MUTED)
    txt(M, y + 102, "Pune 411014, Maharashtra, India", "s", MUTED)
    txt(M, y + 126, "GSTIN: 27AABCU9603R1ZN", "sb")

    txt(bx, y + 20, "REFERENCE", "sb", MUTED)
    # The PO line always prints a placeholder, never a blank — that is the point of it.
    txt(bx, y + 48, "PO Number:  — (non-PO)", "s")
    for i, line in enumerate(reference):
        txt(bx, y + 76 + i * 28, line, "s")

    # ── line items ───────────────────────────────────────────────────────
    y = 500
    COLS = [(M, "#"), (M + 46, "DESCRIPTION"), (640, "HSN/SAC"),
            (790, "QTY"), (860, "UOM"), (975, "RATE"), (W - M, "AMOUNT")]
    d.rectangle([M, y, W - M, y + 40], fill="#eef1f6")
    for x, label in COLS:
        if label in ("AMOUNT", "RATE", "QTY"):
            rt(x if label == "AMOUNT" else x + 60, y + 11, label, "sb", MUTED)
        else:
            txt(x + 10, y + 11, label, "sb", MUTED)

    y += 40
    for it in items:
        d.line([M, y, W - M, y], fill=LINE)
        txt(M + 10, y + 15, it[0], "n")
        txt(M + 56, y + 15, it[1], "n")
        txt(650, y + 15, it[2], "n")
        rt(850, y + 15, it[3], "n")
        txt(870, y + 15, it[4], "n")
        rt(1035, y + 15, it[5], "n")
        rt(W - M, y + 15, it[6], "n")
        y += 52
    d.line([M, y, W - M, y], fill=LINE, width=2)

    # ── totals ───────────────────────────────────────────────────────────
    ty = y + 30
    for k, v in [("Taxable Value", taxable)] + heads + [("Round Off", "0.00")]:
        txt(790, ty, k, "n", MUTED)
        rt(W - M, ty, v, "n")
        ty += 32

    d.rectangle([760, ty + 6, W - M, ty + 62], fill=ACCENT)
    txt(780, ty + 22, "GRAND TOTAL", "b", "white")
    rt(W - M - 16, ty + 20, "INR " + grand, "big", "white")

    ty += 90
    txt(M, ty, "Amount in words: " + words, "s", MUTED)
    txt(M, ty + 30, "Reverse charge applicable: No", "s", MUTED)
    if note:
        txt(M, ty + 60, note, "sb", "#8a5a12")

    # ── footer ───────────────────────────────────────────────────────────
    fy = H - 260
    d.line([M, fy, W - M, fy], fill=LINE)
    txt(M, fy + 24, "Bank Details", "sb", MUTED)
    txt(M, fy + 52, "Alpha Systems Ltd  ·  A/c 5021 4478 9930", "s", MUTED)
    txt(M, fy + 78, "IFSC ABCD0001234  ·  Andheri East Branch", "s", MUTED)
    txt(bx, fy + 24, "For Alpha Systems Ltd", "sb", MUTED)
    txt(bx, fy + 110, "Authorised Signatory", "s", MUTED)
    d.line([bx, fy + 100, W - M, fy + 100], fill=LINE)

    d.rectangle([M, H - 96, W - M, H - 52], fill="#fff4e5", outline="#e0a961")
    txt(W // 2, H - 82, "SAMPLE DOCUMENT — generated for pipeline testing. Not a genuine invoice.",
        "s", "#8a5a12", anchor="ma")

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), out_name)
    img.save(out, "PNG")
    return out


FIXTURES = [
    dict(out_name="test-invoice-alpha-systems.png",
         invoice_no="ALS/2026-27/0412", invoice_date="28-08-2026", due_date="27-09-2026",
         copy_label="Original for Recipient",
         reference=["Contract:   AMC-2026-114", "Currency:   INR"],
         items=SERVICES, taxable="74,100.00",
         heads=[("CGST @ 9%", "6,669.00"), ("SGST @ 9%", "6,669.00")], grand="87,438.00",
         words="Rupees Eighty Seven Thousand Four Hundred Thirty Eight Only"),

    dict(out_name="test-invoice-gst-mismatch.png",
         invoice_no="ALS/2026-27/0418", invoice_date="30-08-2026", due_date="29-09-2026",
         copy_label="Original for Recipient",
         reference=["Contract:   AMC-2026-114", "Currency:   INR"],
         items=SERVICES, taxable="74,100.00",
         heads=[("IGST @ 18%", "13,338.00")], grand="87,438.00",
         words="Rupees Eighty Seven Thousand Four Hundred Thirty Eight Only"),

    # The supplier's own bill behind PUR-INV-2026-90365, which is already booked
    # (docstatus 1) on the site. Date, amount and the single line are copied from that
    # record, so V-DUP-01's four key fields line up against the real history rather than
    # against a row someone has to seed first.
    dict(out_name="test-invoice-duplicate.png",
         invoice_no="ALS/2025-26/0118", invoice_date="28-01-2026", due_date="27-02-2026",
         copy_label="Duplicate for Supplier",
         reference=["GRN Ref:    MAT-PRE-2026-00542", "Currency:   INR"],
         items=GOODS, taxable="4,399.80",
         heads=[], grand="4,399.80",
         words="Rupees Four Thousand Three Hundred Ninety Nine and Eighty Paise Only",
         note="Duplicate copy — reissued on request 05-09-2026."),
]


def _money(s):
    return round(float(s.replace(",", "")), 2)


for spec in FIXTURES:
    lines = sum(_money(i[6]) for i in spec["items"])
    assert all(_money(i[3]) * _money(i[5]) == _money(i[6]) for i in spec["items"]), spec["out_name"]
    assert lines == _money(spec["taxable"]), (spec["out_name"], lines)
    assert lines + sum(_money(v) for _, v in spec["heads"]) == _money(spec["grand"]), spec["out_name"]
    print(render(**spec))

# PUR-INV-2026-90365, the invoice the duplicate fixture is the supplier's copy of.
assert _money(FIXTURES[2]["grand"]) == 4399.80
print("arithmetic OK for all three fixtures")
