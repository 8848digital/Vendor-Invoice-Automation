"""Render a synthetic GST tax invoice PNG for testing /invoice-extract.

See README.md for why these particular values were chosen.
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

img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)
M = 70

def txt(x, y, t, k="n", fill=INK, anchor=None):
    d.text((x, y), t, font=F[k], fill=fill, anchor=anchor)

def rt(x, y, t, k="n", fill=INK):
    d.text((x, y), t, font=F[k], fill=fill, anchor="ra")

# ── header ───────────────────────────────────────────────────────────────
d.rectangle([0, 0, W, 132], fill=ACCENT)
txt(M, 34, "ALPHA SYSTEMS LTD", "h1", "white")
txt(M, 88, "IT Infrastructure & Managed Services", "s", "#c8d4ea")
rt(W - M, 40, "TAX INVOICE", "h2", "white")
rt(W - M, 78, "Original for Recipient", "tiny", "#c8d4ea")

y = 165
txt(M, y, "Unit 402, Solaris Business Park, Andheri East", "s", MUTED)
txt(M, y + 24, "Mumbai 400069, Maharashtra, India", "s", MUTED)
txt(M, y + 48, "GSTIN: 27AAACI1195H1ZM", "sb")
txt(M, y + 72, "PAN: AAACI1195H", "s", MUTED)
txt(M, y + 96, "State: 27-Maharashtra", "s", MUTED)

bx = 690
d.rounded_rectangle([bx, y - 14, W - M, y + 118], 8, outline=LINE, width=2)
rows = [("Invoice No.", "ALS/2026-27/0412"), ("Invoice Date", "28-08-2026"),
        ("Due Date", "27-09-2026"), ("Place of Supply", "27-Maharashtra")]
for i, (k, v) in enumerate(rows):
    txt(bx + 20, y + 4 + i * 28, k, "s", MUTED)
    rt(W - M - 20, y + 4 + i * 28, v, "sb")

# ── bill to ──────────────────────────────────────────────────────────────
y = 320
d.line([M, y, W - M, y], fill=LINE, width=2)
txt(M, y + 20, "BILL TO", "sb", MUTED)
txt(M, y + 48, "8848 DIGITAL", "b")
txt(M, y + 78, "7th Floor, Tower B, Cyber Park", "s", MUTED)
txt(M, y + 102, "Pune 411014, Maharashtra, India", "s", MUTED)
txt(M, y + 126, "GSTIN: 27AABCU9603R1ZN", "sb")

txt(bx, y + 20, "REFERENCE", "sb", MUTED)
txt(bx, y + 48, "PO Number:  — (non-PO)", "s")
txt(bx, y + 76, "Contract:   AMC-2026-114", "s")
txt(bx, y + 104, "Currency:   INR", "s")

# ── line items ───────────────────────────────────────────────────────────
y = 500
COLS = [(M, "#"), (M + 46, "DESCRIPTION"), (640, "HSN/SAC"),
        (790, "QTY"), (860, "UOM"), (975, "RATE"), (W - M, "AMOUNT")]
d.rectangle([M, y, W - M, y + 40], fill="#eef1f6")
for x, label in COLS:
    if label in ("AMOUNT", "RATE", "QTY"):
        rt(x if label == "AMOUNT" else x + 60, y + 11, label, "sb", MUTED)
    else:
        txt(x + 10, y + 11, label, "sb", MUTED)

items = [
    ("1", "Managed hosting - production cluster", "998315", "12", "Month", "4,500.00", "54,000.00"),
    ("2", "On-site engineer support visit", "998713", "6", "Visit", "2,750.00", "16,500.00"),
    ("3", "SSL certificate renewal (wildcard)", "998319", "3", "Nos", "1,200.00", "3,600.00"),
]
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

# ── totals ───────────────────────────────────────────────────────────────
ty = y + 30
tot = [("Taxable Value", "74,100.00", "n"), ("CGST @ 9%", "6,669.00", "n"),
       ("SGST @ 9%", "6,669.00", "n"), ("Round Off", "0.00", "n")]
for k, v, kind in tot:
    txt(790, ty, k, kind, MUTED)
    rt(W - M, ty, v, kind)
    ty += 32

d.rectangle([760, ty + 6, W - M, ty + 62], fill=ACCENT)
txt(780, ty + 22, "GRAND TOTAL", "b", "white")
rt(W - M - 16, ty + 20, "INR 87,438.00", "big", "white")

ty += 90
txt(M, ty, "Amount in words: Rupees Eighty Seven Thousand Four Hundred Thirty Eight Only", "s", MUTED)
txt(M, ty + 30, "Reverse charge applicable: No", "s", MUTED)

# ── footer ───────────────────────────────────────────────────────────────
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

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test-invoice-alpha-systems.png")
img.save(out, "PNG")

taxable = 54000 + 16500 + 3600
cgst = sgst = round(taxable * 0.09, 2)
assert taxable == 74100, taxable
assert cgst == 6669.0, cgst
assert taxable + cgst + sgst == 87438.0
print("arithmetic OK  taxable=%s cgst=%s sgst=%s grand=%s" % (taxable, cgst, sgst, taxable + cgst + sgst))
print(out)
