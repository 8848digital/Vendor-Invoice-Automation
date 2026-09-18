---
name: intake-purchase-invoice
description: >
  Intake profile, loaded by document-intake — do not run directly. Supplier / vendor tax
  invoice billed to our company. Recognise by: "Tax Invoice" heading, supplier and buyer
  GSTINs, invoice number and date, line items with HSN/SAC, qty, rate, amount, CGST+SGST or
  IGST above a grand total; or an e-invoice JSON with DocDtls / SellerDtls / ItemList.
user-invocable: false
---

# Intake profile: Purchase Invoice

## Recognise by

- Heading "Tax Invoice" (or "Invoice" / "Bill of Supply") issued **by** a supplier **to**
  our company; a supplier GSTIN, usually a buyer GSTIN and place of supply.
- A line-item table (HSN/SAC, qty, rate, amount), then taxable value, CGST+SGST or IGST, and
  a grand total. Often a PO number and a signed e-invoice QR code with an IRN.
- Or an NIC e-invoice JSON file.

Not this profile: a delivery challan or goods receipt (quantities, no tax), or a receipt made
out to a person (taxi, hotel, meal).

## Extract

Transcribe into this shape. **Transcribe, never compute.** Omit what is not printed.

```json
{
  "supplier": "…",            "supplier_gstin": "…",
  "company_gstin": "…",       "place_of_supply": "NN-State Name",
  "invoice_no": "…",          "invoice_date": "YYYY-MM-DD",
  "po_number": "…",           "irn": "…",          "currency": "INR",
  "taxable_value": 0, "cgst": 0, "sgst": 0, "igst": 0, "cess": 0,
  "round_off": 0, "grand_total": 0,
  "is_reverse_charge": false,
  "items": [
    {"description": "…", "supplier_part_no": "…", "hsn_sac": "…",
     "qty": 0, "uom": "…", "rate": 0, "amount": 0}
  ]
}
```

- `supplier` is the name **as printed**. Do not look it up — the server resolves supplier,
  company and item codes from GSTIN, name and the PO, and tells you what it matched.
- Read `qty`, `rate`, `amount` and each tax off the page. Do not add up, derive or correct a
  figure: a disagreement is a finding, and fixing it destroys the finding.
- A printed placeholder (`—`, `N/A`, `Nil`, `(none)`) means **absent** — omit the field.
  Especially `po_number`: a placeholder there routes the invoice into PO matching.
- A GSTIN is exactly 15 characters. If what you read is not, re-read that region; if still
  unclear, omit it rather than guess.
- Do not transcribe the QR code — the server decodes it from the file.
- For an e-invoice **JSON** file, send `{}` as the invoice: the server reads the file.

## Validate

One call:

```
jarvis__run_method
  method: vendor_invoice_automation.api.v1.intake.process_invoice
  args:   {"invoice": { …the extract… }, "file_name": "<attached file name>"}
```

Add `"intake": "<Document Intake name>"` when re-validating a saved record after a
correction. From the receipt, keep `data` — you need `data.save` below.

Report as document-intake §5 says, plus one line for `data.resolved` (what the server
matched the printed supplier / items to).

## Save

Always, whatever the verdict: make exactly the write in `data.save` — `data.save.tool`
(`jarvis__create_doc` or `jarvis__update_doc`) with its `doctype`, `name` (for an update)
and `values`. The values carry only an `intake_ref`; the server fills the record from it.
State the saved record's `name` from the receipt.

Then, by `data.confidence_band`:

- `auto` → continue to Actions.
- `review` → list `data.uncertain_fields` with the values you read, and ask the user to
  confirm or correct them. Corrections: re-Validate with `intake`, then Save again. Only
  continue once the user confirms.
- `manual` → the record is saved as **OCR Failed** in the exception queue. Say so and stop.

## Actions — approve the Draft Purchase Invoice

When `data.proposes_purchase_invoice` is **false**, nothing is proposed: say why in one line
from `data.status` / `data.exception_type` (e.g. "held: GRN Failed — Missing GRN; the uploader
is notified when the goods receipt is posted") and stop.

When it is **true**, saving the record already queued an **Intake Action** "Create Purchase
Invoice" for approval — you do not build the invoice. Find it:

```
jarvis__get_list
  doctype: Intake Action
  filters: {"intake": "<saved record name>", "status": "Pending"}
  fields:  ["name", "summary", "reason"]
```

Show its `summary` and `reason`, then ask the user: approve now, reject, or leave it for an
approver? Approvers also get a notification and can decide in the desk later — leaving it is
a normal answer, not a failure.

If the user decides now, one call:

```
jarvis__run_method
  method: vendor_invoice_automation.api.v1.intake.decide_action
  args:   {"action": "<Intake Action name>", "decision": "Approve", "note": "<the user's words, if any>"}
```

`decision` is `"Approve"` or `"Reject"`, exactly as the user said — never your own choice.
On Approve the server builds the Draft Purchase Invoice from ERPNext's own mapper, runs the
pre-insert checks (V-PI-01…10) and creates it as the approver. From the receipt report
`data.status`, `data.result_doc` (the new Purchase Invoice) or `data.error`, and the check
rows. A `Failed` status means a pre-insert check blocked it: nothing was created, and the
intake stays in its queue. The invoice is a **Draft**; never submit it.

If the intake's review flag is set (yellow verdict), say that Buyer Review should look at the
flagged differences before approving.

## Notes

- A clean invoice in chat is three confirmation cards: validate, save, decide.
- From the File Box nobody decides in chat: the Intake Action waits in **Pending Approvals**
  on the Invoice Inbox, and an approver acts on it there.
- Which checks run, and how severe each is, is configured per document type in **Intake
  Rule** — a check switched off there shows as Skipped, naming the rule.
- After creation the status follows the Purchase Invoice by itself: Workflow → Approved →
  Posted → Payment Pending → Paid.
