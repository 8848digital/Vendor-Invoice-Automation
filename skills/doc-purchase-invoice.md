---
name: doc-purchase-invoice
description: >
  Document-type profile, loaded by document-check — do not run directly. Purchase Invoice
  (supplier / vendor tax invoice, bill to our company). Recognise by: "Tax Invoice" heading,
  supplier and buyer GSTINs, invoice number and date, line items with HSN/SAC, qty, rate,
  amount, and CGST+SGST or IGST tax lines above a grand total.
user-invocable: false
---

# Profile: Purchase Invoice

## Recognise by

- Heading "Tax Invoice" (sometimes "Invoice" / "Bill of Supply"), issued **by** a supplier
  **to** our company.
- A supplier GSTIN and usually a buyer GSTIN; place of supply.
- A line-item table with HSN/SAC, qty, rate, amount.
- Taxable value, then CGST+SGST or IGST, then a grand total.

Not this profile: a delivery challan or goods receipt (no tax lines, quantities only), or a
retail / travel receipt made out to a person rather than the company.

## Extract

Follow `invoice-extract` §2–§3 exactly — its field shape and transcription rules are the
contract the API validates against.

## Checks

Follow these skills in order, all against the one `invoice_ref` the first one mints:

| step | skill | source | rows it produces |
|---|---|---|---|
| 1 | `invoice-extract` | api | V-EXT-* |
| 2 | `invoice-duplicate` | api | V-DUP-* |
| 3 | `invoice-fraud` | api | V-INT-*, V-FAKE-* |

If step 1 produces no `invoice_ref`, stop there and report what it returned — steps 2 and 3
have nothing to validate.

Collect **every** row from each receipt (not only the failed ones the individual skills
tabulate) into `document-check`'s table.

## Notes

- Each step is one gated `jarvis__run_method` call, so three confirmation cards in chat.
- einvoice, gst, itc, po-match and grn-match have no skill yet; add them as rows above when
  they are written.
