# Test fixtures

`test-invoice-alpha-systems.png` — a synthetic GST tax invoice for exercising
`/invoice-extract` end to end. Regenerate with `make_test_invoice.py` (needs Pillow).

Chosen so the skill's steps actually resolve rather than stalling on the demo site:

- **Supplier `Alpha Systems Ltd`** is a real Supplier record on 8848hrms-demo, so §3's
  resolve step finds exactly one match.
- **Buyer `8848 DIGITAL`** is the only Company there.
- GSTINs are synthetic but carry correct NIC check digits, so india_compliance's
  `validate_gstin` accepts them: supplier `27AAACI1195H1ZM` (PAN AAACI1195H),
  buyer `27AABCU9603R1ZN`. Both Maharashtra, so it is intra-state and must carry
  CGST+SGST rather than IGST (V-GST-12/13).
- Arithmetic is exact and asserted in the generator, so V-EXT-03 and V-EXT-04 pass:
  74,100 taxable + 6,669 CGST + 6,669 SGST = 87,438.00.
- No PO number → routes Non-PO, so PO and GRN matching skip.
- Dated 28-08-2026: inside the 180-day window and not in the future (V-INT-07). It will
  age out — regenerate, or expect a V-INT-07 warning once it passes 180 days.

## What to expect on the demo site

Extraction and the arithmetic checks should pass. Two things will NOT:

- No Supplier or Company there has a `gstin` set, so V-FAKE-01 / V-GST-07 / V-EXT-10
  have nothing to compare against.
- The skill stops at its POST step — there is still no outbound-HTTP tool in Jarvis.

So this tests reading and transcription, not the full verdict.
