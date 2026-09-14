# The `context` contract

`validate_invoice` reads no business data. Everything it compares against travels in the
request as `context`, assembled by **you**, on **your** site, against **your** database.

This document is how to build it.

```jsonc
POST /api/method/vendor_invoice_automation.api.v1.invoice.validate_invoice
{
  "invoice": { ... },            // or "invoice_ref" from an earlier call
  "blocks":  ["duplicate"],      // omit to run everything
  "context": { ... },
  "contract_version": "1.0"
}
```

## The one rule

A **missing** key and a **null** value mean different things, and the API treats them
differently:

| you send | it means | you get |
|---|---|---|
| key absent | "I did not look" | `Skipped`, `unrun: true` — and `auto_create_allowed` is forced `false` |
| `null` / `[]` | "I looked, there is nothing" | the real check — `Pass` or `Fail` |
| a value | "I looked, this is it" | the real check |

Never send `null` for something you did not fetch. `"supplier": null` asserts the Supplier
does not exist, which fails V-INT-04 and stops the pipeline.

## What each block needs

Send only the keys for the blocks you are running.

| block | keys |
|---|---|
| `intake` | `supplier` |
| `extraction` | `fiscal_year`, `company_gstins` |
| `duplicate` | `existing_invoices`, `irn_hits` |
| `fraud` | `supplier` |
| `einvoice` | *(none — it verifies the signed QR against the payload)* |
| `gst` | `supplier`, `hsn_codes`, `inward_supply`, optionally `gstin_status` |
| `itc` | `inward_supply` |
| `routing` | `items` |
| `po_match` | `po`, `items`, `settings` |
| `grn_match` | `grn`, `items`, `settings` |

`validation_blocks()` returns this same table, so you can read it at runtime instead of
this file.

## How to fetch each key

All paths below are on **your** site. Everything is either a plain resource read or an
already-whitelisted method — you do not need this app installed to call any of them.

### `supplier`
```
GET /api/resource/Supplier/<name>
    ?fields=["name","disabled","on_hold","hold_type","release_date","gstin","pan","gst_category"]
```
Not found → send `"supplier": null`.

### `existing_invoices`
```
GET /api/resource/Purchase Invoice
    ?filters=[["bill_no","=",<invoice_no>],["supplier","=",<supplier>]]
    &fields=["name","docstatus","supplier_gstin","bill_date","grand_total"]
```
**Do not filter on `docstatus`.** A cancelled invoice was still seen, and re-uploading it is
exactly what V-DUP-01 exists to catch.

Match on `supplier` **or** `supplier_gstin`, not both: `supplier_gstin` is
`fetch_from: supplier_address.gstin`, so it is empty on any invoice booked without a
supplier address, and an `AND` would miss those.

### `irn_hits`
Only needed when the invoice carries an `irn`.
```
GET /api/resource/GST Inward Supply
    ?filters=[["irn_number","=",<irn>],["bill_no","!=",<invoice_no>]]
    &fields=["name","bill_no"]&limit_page_length=5
```
The `bill_no !=` is load-bearing: a 2B row for *our own* bill number is the supplier's
filing of this very invoice, not a duplicate.

### `inward_supply`
The GSTR-2B row, or `null` if the supplier has not filed yet (normal, not a defect).
```
GET /api/resource/GST Inward Supply
    ?filters=[["supplier_gstin","=",<supplier_gstin>],["bill_no","=",<invoice_no>]]
    &fields=["name","bill_no","bill_date","supplier_gstin","company_gstin",
             "taxable_value","cgst","sgst","igst","cess",
             "irn_number","is_reverse_charge","classification","doc_type","place_of_supply",
             "itc_availability","reason_itc_unavailability",
             "gstr_1_filled","gstr_1_filing_date","is_supplier_return_filed","sup_return_period"]
    &limit_page_length=1
```
This one must come from you: GSTR-2B is your own purchase return and needs your GSTN
authentication. GSTIN *status* is different — see `gstin_status`.

### `hsn_codes`
Which of **this invoice's** codes exist in the master — the API diffs the two.
```
GET /api/resource/GST HSN Code
    ?filters=[["name","in",[<every hsn_sac on the invoice>]]]&fields=["name"]
```

### `company_gstins`
```
POST /api/method/india_compliance.gst_india.utils.get_gstin_list
     {"party": <company>, "party_type": "Company"}
```

### `fiscal_year`
```
POST /api/method/erpnext.accounts.utils.get_fiscal_year
     {"date": <invoice_date>, "company": <company>, "as_dict": 1}
```
Throws when the date falls in no open year → send `"fiscal_year": null`.

### `items`
One read serves routing *and* both allowance lookups.
```
GET /api/resource/Item
    ?filters=[["name","in",[<every item_code on the invoice>]]]
    &fields=["name","is_stock_item","over_delivery_receipt_allowance","over_billing_allowance"]
```
Reshape to `{item_code: {is_stock_item, over_delivery_receipt_allowance,
over_billing_allowance}}`.

### `settings`
```json
{
  "over_delivery_receipt_allowance": 0,     // Stock Settings — global fallback
  "over_billing_allowance": 0,              // Accounts Settings — global fallback
  "maintain_same_rate": 1,                  // Buying Settings
  "maintain_same_rate_action": "Stop",      // Buying Settings
  "rate_override_held": false,
  "over_bill_override_held": false
}
```
The last two are booleans **you** resolve: does the user who will actually book this invoice
hold `Buying Settings.role_to_override_stop_action` / `Accounts Settings.
role_allowed_to_over_bill`? Resolve them for that user, not for whatever service account
makes the HTTP call — getting this wrong makes rate and over-billing findings more blocking
than ERPNext itself would be.

### `po`
Run ERPNext's own mapper. **Do not re-derive what is billable** — the mapper already
enforces submitted / not closed / not fully billed / pending qty net of what is booked, and
a hand-rolled version will drift from it.
```
POST /api/method/erpnext.buying.doctype.purchase_order.mapper.make_purchase_invoice
     {"source_name": <po_number>}
```
- success → `{"po": {"expected_invoice": <the returned doc>}}`
- it throws (draft, cancelled, closed, on hold, nothing left to bill) → `{"po": {"error": "<message>"}}`
  That is a real answer and a blocking one, not an error to swallow.

### `grn`
Every submitted receipt against the order, each mapped, because one invoice legitimately
covers several partial receipts.
```
GET  /api/resource/Purchase Receipt Item
     ?filters=[["purchase_order","=",<po_number>],["docstatus","=",1]]
     &fields=["parent"]&limit_page_length=0
POST /api/method/erpnext.stock.doctype.purchase_receipt.mapper.make_purchase_invoice
     {"source_name": <each parent>}
```
```json
{"grn": {"receipts": ["MAT-PRE-0001"], "expected_invoices": [ ... ], "errors": ["MAT-PRE-0002: ..."]}}
```

### `gstin_status` — optional
Leave it out and the validation site resolves GSTIN status itself through its own
india_compliance and GSP credentials. Send it only if you would rather use your own.

## `invoice_ref`

Send `invoice` once; the response carries an `invoice_ref`. Send that on later calls
instead of the payload:

```jsonc
{"invoice_ref": "…", "blocks": ["gst"], "context": {…}}
```

Every block then validates byte-identically the payload that was extracted once, which
matters when a multi-step caller would otherwise restate it from a chat transcript — one
wrong digit part-way through would silently validate something the invoice never said.

The ref is a bearer token into a Redis cache with a ~1 hour TTL. It is not a record:
nothing is queryable or durable, and it expires on its own. An expired or unknown ref is a
`BAD_REQUEST` telling you to re-extract — never a silent validation of nothing.

## Reading the response

```jsonc
{
  "verdict": "green",              // red = an Error failed, yellow = a Warning failed
  "ok": true,                      // no Error-severity failures
  "auto_create_allowed": false,    // ← gate every write on THIS
  "review_required": true,
  "failed": [], "skipped": [], "unrun": ["V-INT-04"], "partial": true,
  "checks": [ … ]
}
```

**Gate creation on `auto_create_allowed`, never on `ok` or `verdict`.** A green verdict only
says nothing failed; it does not say anything ran. `auto_create_allowed` is false whenever

- a check's context key was not supplied (`unrun`), or
- you ran a subset of the blocks (`partial`) — a per-block call can never authorise
  creation, because every other block did not run.

So to actually create a Purchase Invoice, make one final call with the whole sequence.
