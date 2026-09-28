# Purchase Invoice Validation API — Contract Spec

The one file to hand a developer implementing **either side** of this API: a caller
integrating with it, or a from-scratch reimplementation of the same checks elsewhere.
Current, correct, and self-contained — it does not assume you've read the others.

Companions, if you need more:
- [`CONTEXT.md`](CONTEXT.md) — exact queries to fetch each `context` key
- [`VALIDATION_API_MAP.md`](VALIDATION_API_MAP.md) — build status, what's still unbuilt, backlog
- [`SPEC.md`](SPEC.md) — the original design doc. Superseded where it disagrees with this file.

---

## 1. What it does

One call validates one extracted Purchase Invoice against a fixed catalog of checks and
returns a pass/fail verdict plus a per-check audit trail. **Stateless and read-only** — it
writes nothing, and it holds no business data of its own (no Supplier, PO, GST return
data, etc.). Everything a check compares against arrives in the request as `context`,
fetched by the caller from the caller's own site.

The only state is a ~1 hour Redis cache behind `invoice_ref`, so a multi-step caller
(e.g. one block per turn) can re-validate the same extracted payload without restating it.

Purchase Invoice *creation* is not part of this contract — see [§11](#11-what-this-api-does-not-do-yet).

---

## 2. Endpoints

```
POST /api/method/vendor_invoice_automation.api.v1.invoice.validate_invoice
```
`allow_guest=True`, rate-limited to 60 calls/min per caller. Guest-allowed means this
endpoint does not itself enforce a Frappe session — put it behind your own auth/network
boundary if that matters for your deployment.

```
POST /api/method/vendor_invoice_automation.api.v1.invoice.validation_blocks
```
No arguments. Returns the block names, the default sequence, and the `context` keys each
block needs — call this at runtime instead of hardcoding the contract.

---

## 3. Request — `invoice`

A dict, or a JSON-encoded string. All fields are the *extracted* values from the document
(never re-derived from context).

| Field | Type | Notes |
| --- | --- | --- |
| `supplier` | str | Supplier name — required |
| `company` | str | Required for V-EXT-09 / V-EXT-10 |
| `invoice_no` | str | Supplier's bill number |
| `invoice_date` | str | `YYYY-MM-DD` |
| `supplier_gstin` | str | GSTIN printed on the document |
| `company_gstin` | str | Buyer GSTIN printed on the document |
| `place_of_supply` | str | `"NN-State Name"` |
| `po_number` | str | Absent means non-PO |
| `irn` | str | If e-invoiced |
| `currency` | str | |
| `taxable_value`, `cgst`, `sgst`, `igst`, `cess`, `round_off`, `grand_total` | number | |
| `declared` | dict | What the uploader typed by hand, e.g. `{"grand_total": …}` — optional, enables V-EXT-07 |
| `qr_payload` | str | Signed QR/e-invoice JWS, if present — enables Stage 2c |
| `items` | list[dict] | `{item_code, hsn_sac, qty, uom, rate, amount, warehouse, batch_no, serial_no, description}` |

## 3a. Request — `blocks`

Which validation blocks to run, **in the order given**. A list, a JSON array string, or a
comma-separated string. Omit it to run every block in the default order:

```
intake → extraction → duplicate → fraud → einvoice → gst → itc → routing → po_match → grn_match
```

Running a subset is legal (e.g. re-check just `"gst"` after a supplier GSTIN correction),
but the response is then marked `partial: true` and can never set `auto_create_allowed`
— see [§8](#8-decision-gate).

## 3b. Request — `context`

Everything the checks compare against. This API does not query your database; you do,
and you send the results. See [`CONTEXT.md`](CONTEXT.md) for the exact query/API call
behind every key below.

**One rule, and it's load-bearing:**

| You send | Means | You get |
| --- | --- | --- |
| key **absent** | "I did not look" | `Skipped`, `unrun: true` — forces `auto_create_allowed: false` |
| `null` / `[]` | "I looked, there is nothing" | the real check runs — `Pass` or `Fail` |
| a value | "I looked, this is it" | the real check runs |

Never send `null` for something you didn't fetch — `"supplier": null` asserts the
Supplier doesn't exist and fails V-INT-04, which stops the whole pipeline.

| Block | `context` keys it reads |
| --- | --- |
| `intake` | `supplier` |
| `extraction` | `fiscal_year`, `company_gstins` |
| `duplicate` | `existing_invoices`, `irn_hits` |
| `fraud` | `supplier` |
| `einvoice` | *(none — verifies the signed QR against the payload itself)* |
| `gst` | `supplier`, `hsn_codes`, `inward_supply`, `gstin_status` (optional) |
| `itc` | `inward_supply` |
| `routing` | `items` |
| `po_match` | `po`, `items`, `settings` |
| `grn_match` | `grn`, `items`, `settings` |

## 3c. Request — `invoice_ref` / `contract_version`

Send `invoice` once; the response carries an `invoice_ref` token. Pass that instead of
`invoice` on later calls so every block validates the byte-identical payload extracted
once — important when a multi-step caller (e.g. an LLM agent) would otherwise restate the
invoice from memory between calls, and could drift.

```jsonc
// first call
{"invoice": {...}, "context": {...}}
// later calls
{"invoice_ref": "the-token-you-got-back", "blocks": ["gst"], "context": {...}}
```

An expired or unknown `invoice_ref` returns `BAD_REQUEST` — never a silent no-op
validation. Optionally send `contract_version: "1.0"`; a mismatch is refused rather than
silently validated against a contract you don't have.

---

## 4. The validation catalog

Every check below runs as `checks[]` in the response unless marked **caller-owned**, in
which case it happens before this API is ever called and never appears there at all.

`Severity` determines what a `Fail` does to the verdict (§8). `Result` is one of
`Pass | Fail | Skipped`.

### Stage 0 — Intake

| ID | Severity | Asserts | Computed by |
| --- | --- | --- | --- |
| V-INT-01 | — | File extension allowed, size ≤ max, page count ≤ max | **Caller** — never reaches this API |
| V-INT-02 | — | PDF opens cleanly, not password-protected | **Caller** |
| V-INT-03 | — | `file_hash` (SHA-256) not seen before | **Caller** — this API keeps no upload history |
| V-INT-04 | Error | Resolves to exactly one Supplier | This API |
| V-INT-05 | Error | Supplier enabled, not on hold | This API |
| V-INT-06 | Error | Supplier has GSTIN + PAN on file | This API |
| V-INT-07 | Warning | Invoice date not future, within the accepted window | This API |

A V-INT-04 **Fail** (Supplier definitely does not resolve) stops the pipeline —
everything downstream needs the Supplier master. A V-INT-04 *Skipped* (caller sent no
`supplier` key) does **not** stop it.

### Stage 1 — Extraction

Extraction itself (OCR/LLM/QR/XML parse) is the caller's job; only the checks *on* the
extracted result live here.

| ID | Severity | Asserts | Computed by |
| --- | --- | --- | --- |
| V-EXT-02 | Error | Extracted fields agree with the signed QR / e-invoice ground truth | This API — folded into Stage 2c, see V-FAKE-04 |
| V-EXT-03 | Error | `qty × rate = amount`, per line | This API |
| V-EXT-04 | Error | `Σtaxable + Σtax + round_off = grand_total` (±₹1) | This API — total is recomputed, never trusted |
| V-EXT-05 | Error | CGST+SGST xor IGST, never both | This API |
| V-EXT-06 | — | Double-extraction agreement (LLM path) | **Caller** — the caller extracts, so the caller compares |
| V-EXT-07 | Warning | Declared vs extracted grand total within ₹1 | This API — `Skipped` if `invoice.declared` absent |
| V-EXT-08 | Warning | HSN/SAC present, valid length | This API |
| V-EXT-09 | Error | Invoice date falls in an open Fiscal Year | This API — needs `context.fiscal_year` |
| V-EXT-10 | Error | `company_gstin` is a registered GSTIN of `company` | This API — needs `context.company_gstins` |

> **Not yet built:** V-EXT-01 (full payload schema conformance beyond "is it a dict").

### Stage 2a — Duplicate

One query (`context.existing_invoices`) fetches every Purchase Invoice already booked
under this bill number for this supplier — **not** filtered on `docstatus`, because a
cancelled invoice was still seen.

| ID | Severity | Asserts | Computed by |
| --- | --- | --- | --- |
| V-DUP-01 | Error | Same GSTIN + invoice no + date + amount already booked | This API |
| V-DUP-02 | Error | Same IRN already reported against a *different* invoice | This API — silently skipped if the invoice carries no IRN |
| V-DUP-07 | Warning | Invoice number seen before with different details | This API — names which fields differ |

> **Not yet built:** V-DUP-05/06 (same QR / same file hash seen before) — need an upload
> history this API does not keep. Deliberately unimplemented, not silently missing.

### Stage 2b — Identity / fraud

| ID | Severity | Asserts | Computed by |
| --- | --- | --- | --- |
| V-FAKE-01 | Error | Document GSTIN = Supplier master GSTIN | This API |
| V-FAKE-07 | Error | PAN embedded in the GSTIN = Supplier's PAN on file | This API |
| V-FAKE-08 | Error | *(see source — flags known-fraud patterns)* | This API |

### Stage 2c — e-Invoice (QR verification)

Only runs if `invoice.qr_payload` is present. Decoding and signature verification are
separate: decoding proves the printed page agrees with its own QR (catches alteration);
the RSA signature check proves NIC actually issued it (catches forgery). Verification
needs `via_nic_public_certificate` in `site_config.json` — without it, V-FAKE-02 reports
`Skipped`, never `Pass`.

| ID | Severity | Asserts | Computed by |
| --- | --- | --- | --- |
| V-FAKE-02 | Error | QR's JWS signature verifies against NIC's certificate | This API |
| V-FAKE-04 | Error | QR header values (no., total, date) = the printed document's | This API |
| V-GST-08 | Error | Seller GSTIN on the QR = the document's | This API |
| V-GST-09 | Error | Buyer GSTIN on the QR = our company GSTIN | This API |
| V-GST-10 | Error / Warning* | IRN on the document = IRN inside the signed QR | This API — *Warning severity on the "matches" Pass row only |

### Stage 3 — GST

Thin wrapper over `india_compliance` — nothing here reimplements GSTIN/HSN logic.

| ID | Severity | Asserts | Computed by |
| --- | --- | --- | --- |
| V-GST-01/02 | Error | GSTIN format, check digit, state code | This API |
| V-GST-03 | Error | GSTIN status is Active, right now | This API — `Skipped` if no local `GSTIN` row and GSTN API not enabled |
| V-GST-04a | Error | GSTIN was Active **as of the invoice date** | This API |
| V-GST-05 | Error | Composition-scheme supplier charges zero tax | This API |
| V-GST-07 | Error | PAN embedded in GSTIN = Supplier's PAN | This API |
| V-GST-12/13 | Error | Place of supply is real; CGST/SGST vs IGST is correct for it | This API |
| V-GST-14 | Warning | HSN/SAC exists in the master (rate check is in Stage 4a instead) | This API |
| V-GST-15 | Warning (Fail is Error-severity) | Reverse-charge flag correct | This API — blocking: decides who pays the tax |
| V-GST-16 | Info | Invoice reflected in GSTR-2B and values agree | This API — non-blocking by design |
| V-GST-17 | Warning | Supplier has filed the GSTR-1 carrying this invoice | This API — unfiled is a timing issue, not an invalid invoice |
| V-ITC-01 | Info | ITC status: Eligible / Blocked / RCM / ISD / Ineligible / Provisional | This API — GSTN's own determination, never re-derived |

> **Unknown is not invalid.** When there's no local `GSTIN` row and the GSTN API isn't
> enabled, V-GST-03/04a return `Skipped`, never `Fail`. A missing status must never reject
> a legitimate supplier.

### Stage 4 — Routing (a decision, not a check — emits no row)

```
po_number present + any stock line   → "3-Way"    → run Stage 4a + Stage 5
po_number present, no stock line     → "2-Way"    → run Stage 4a only
no po_number                         → "Non-PO"   → no further matching checks
```

### Stage 4a — PO matching (2-Way and 3-Way)

Runs ERPNext's own `purchase_order.mapper.make_purchase_invoice(po)` and diffs against
it — "what's still billable" is never re-derived here, so a verdict here can't disagree
with what ERPNext's own `insert()` would do.

| ID | Severity | Asserts | Computed by |
| --- | --- | --- | --- |
| V-PO-01 | Error | PO exists, submitted, open, has something left to bill | This API |
| V-PO-03/04/05 | Error | Supplier, company, currency match the PO | This API |
| V-PO-07 | Error | Every invoice line is still billable against the PO | This API |
| V-PO-09 | Error | UOM matches | This API |
| V-PO-10 | Error/Warning by tolerance | Quantity within `over_delivery_receipt_allowance` | This API |
| V-PO-11 | Error/Warning | Rate variance (0.01 epsilon, no percentage band — see `Buying Settings.maintain_same_rate`) | This API |
| V-PO-12 | Error/Warning by tolerance | Amount within `over_billing_allowance` | This API |

### Stage 5 — GRN matching (3-Way only)

Same shape, driven by `purchase_receipt.mapper.make_purchase_invoice(pr)` for every
submitted receipt against the order (merged, since one invoice can cover several partial
receipts).

| ID | Severity | Asserts | Computed by |
| --- | --- | --- | --- |
| V-GRN-02 | Error | ≥1 submitted Purchase Receipt with something left to invoice | This API |
| V-GRN-05/06/07/08 | Error | Warehouse/batch/serial match, where the invoice states them | This API |
| V-GRN-07/09/10/11/12 | Error/Warning | Material, UOM, quantity, rate, amount vs what was received | This API |

> **Not yet built:** V-GRN-09 (Quality Inspection accepted), V-GRN-10 (PR date ≤ invoice
> date).

### Non-PO checks

**Not implemented.** A clean non-PO invoice returns `auto_create_allowed: true` from
Stage 0–3 checks alone — there is no non-PO ceiling, expense-account, or TDS-section gate
in this API today. If your integration needs that, build it on your side for now.

---

## 5. Severity vocabulary

| Severity | Effect of a `Fail` |
| --- | --- |
| `Error` | Pushes verdict to `red`. Always blocks `auto_create_allowed`. |
| `Warning` | Pushes verdict to `yellow` (unless already `red`). Blocks creation unless the site has opted into auto-create-on-yellow. |
| `Info` | Never affects the verdict. Informational only (e.g. ITC classification, 2B reflection). |

---

## 6. Response

The house envelope, validation result under `data`:

```json
{
  "status": "error",
  "message": "Fraud Suspected",
  "timestamp": "2026-09-23 18:04:11",
  "data": {
    "ok": false,
    "verdict": "red",
    "auto_create_allowed": false,
    "review_required": true,
    "matching_mode": "2-Way",
    "exception_type": "Fraud Suspected",
    "failed":  ["V-FAKE-01"],
    "skipped": ["V-GST-03"],
    "unrun": [],
    "partial": false,
    "checks": [
      {
        "check_id": "V-FAKE-01",
        "stage": "fraud",
        "severity": "Error",
        "result": "Fail",
        "expected": "27AAACI1195H1ZM",
        "found": "29AAACI1195H1ZI",
        "message": "GSTIN on the document is not the supplier's registered GSTIN.",
        "unrun": false
      }
    ],
    "invoice_ref": "…",
    "contract_version": "1.0"
  }
}
```

| `data` field | Meaning |
| --- | --- |
| `ok` | `true` iff no `Error`-severity check failed. Ignores the yellow-verdict setting — don't gate writes on this. |
| `verdict` | `"green" \| "yellow" \| "red"` — see §8 |
| `auto_create_allowed` | **Gate every write on this field, and only this field.** See §8 |
| `review_required` | `true` whenever verdict isn't green, or a required check didn't run, or the call was partial |
| `matching_mode` | `"Non-PO" \| "2-Way" \| "3-Way"` |
| `exception_type` | Human label for the most serious failure — see §8's table — or `null` if nothing failed |
| `failed` / `skipped` / `unrun` | Lists of `check_id` |
| `partial` | `true` if `blocks` was a subset of the default sequence, or the pipeline stopped early (Stage 0 short-circuit) |
| `checks` | Every row that ran — the full audit trail |
| `invoice_ref` | Token to reuse on later calls (§3c) |
| `contract_version` | Echoes the version this response was computed against |

Each row in `checks[]`:

| Field | Meaning |
| --- | --- |
| `check_id` | e.g. `"V-GST-03"` |
| `stage` | e.g. `"gst"` |
| `severity` | `Info \| Warning \| Error` |
| `result` | `Pass \| Fail \| Skipped` |
| `expected` / `found` | Stringified, or `null` |
| `message` | Human-readable explanation |
| `unrun` | `true` only when this check couldn't run because its `context` key was never supplied — see §8 |

---

## 7. Errors

Malformed input returns `status: "error"` with an `error_code` and **no `data` key** —
distinguishable from an invoice that was validated and rejected (which always has `data`).

| `error_code` | When |
| --- | --- |
| `BAD_REQUEST` | `invoice`/`context` isn't valid JSON or isn't an object; `blocks` isn't a list; unknown block name; `invoice_ref` expired/unknown with no `invoice` supplied; `contract_version` mismatch |
| `PERMISSION_DENIED` | The calling user lacks read access to `company` — V-EXT-10 calls `india_compliance`'s `get_gstin_list`, which checks permission and throws rather than returning a row |

---

## 8. Decision gate

```
any Error-severity check Fails         → verdict = "red"
else any Warning-severity check Fails  → verdict = "yellow"
else                                    → verdict = "green"

auto_create_allowed =
    (verdict == "green" OR (verdict == "yellow" AND site allows auto-create-on-yellow))
    AND unrun is empty
    AND not partial
```

**`unrun` is the trap this exists to close.** Every comparison value now arrives as
`context` you assembled — send none, and every check either resolves trivially or
`Skips`, which on its own would read as a flawless invoice. `unrun` lists every
`Error`-severity check whose `context` key was simply never supplied, and its presence
alone forces `auto_create_allowed: false`, regardless of `verdict`.

**`partial` closes the same hole from the other side.** Running one block on its own
means every *other* block emitted no rows at all — not even `Skipped` ones — so `unrun`
can't see them missing. Any non-default `blocks` subset therefore forces
`auto_create_allowed: false` outright. To actually authorize creation, make one final
call with the full default sequence and a fully-populated `context`.

**A `Skipped` `Error`-severity row is not automatically "unrun".** V-GST-03 (status
genuinely unknown) and V-FAKE-02 (no NIC certificate configured) are legitimately
`Skipped` even on a fully-populated request — the response reports them in `skipped[]`,
not `unrun[]`, and they do not by themselves block creation. Only a *missing-context*
skip is `unrun`.

### `exception_type`

Derived from the first prefix match below against the failed check IDs — checked in this
order (most serious first), not in the order checks happened to fail:

| Check ID prefix(es) | `exception_type` |
| --- | --- |
| `V-FAKE-*`, `V-GST-08`, `V-GST-09`, `V-GST-10` | `"Fraud Suspected"` |
| `V-DUP-01`, `V-DUP-02` | `"Duplicate"` |
| `V-DUP-*` (other) | `"Suspected Duplicate"` |
| `V-GST-03`, `V-GST-04a` | `"Suspended GST"` |
| `V-GST-01/02`, `V-GST-07` | `"Invalid GSTIN"` |
| `V-GST-12/13`, `V-GST-15` | `"Invalid Tax"` |
| `V-GST-14`, `V-EXT-08` | `"Invalid HSN"` |
| `V-GST-16` | `"2B Unavailable"` |
| `V-GST-17` | `"Return Not Filed"` |
| `V-GRN-05`, `V-GRN-09` | `"UOM Mismatch"` / `"GRN Mismatch"` (see source order) |
| `V-GRN-07`, `V-GRN-10` | `"Qty Mismatch"` |
| `V-GRN-11`, `V-GRN-12` | `"Price Mismatch"` |
| `V-GRN-*` (other) | `"GRN Mismatch"` |
| `V-PO-01`, `V-PO-03` | `"Missing PO"` |
| `V-PO-07` | `"Item Not On PO"` |
| `V-PO-09` | `"UOM Mismatch"` |
| `V-PO-10` | `"Qty Mismatch"` |
| `V-PO-11`, `V-PO-12` | `"Price Mismatch"` |
| `V-PO-*` (other) | `"Missing PO"` |
| `V-ITC-*` | `"ITC Unavailable"` |
| `V-EXT-*` (other) | `"OCR Failure"` |
| `V-INT-*` | `"Intake Failed"` |

Exact order is `validations/decision.py::EXCEPTION_BY_CHECK` — treat this table as a
convenience copy, that file as truth.

---

## 9. Worked example

```jsonc
// Request
POST /api/method/vendor_invoice_automation.api.v1.invoice.validate_invoice
{
  "invoice": {
    "supplier": "Acme Traders",
    "company": "My Company",
    "invoice_no": "INV-2043",
    "invoice_date": "2026-09-10",
    "supplier_gstin": "27AAACI1195H1ZM",
    "company_gstin": "29AAACI1195H1ZI",
    "po_number": "PO-00123",
    "taxable_value": 10000, "cgst": 900, "sgst": 900, "igst": 0, "cess": 0,
    "round_off": 0, "grand_total": 11800,
    "items": [{"item_code": "ITEM-01", "hsn_sac": "8471", "qty": 10,
               "uom": "Nos", "rate": 1000, "amount": 10000}]
  },
  "blocks": ["intake", "extraction", "gst"],
  "context": {
    "supplier": {"name": "Acme Traders", "disabled": 0, "on_hold": 0,
                 "gstin": "27AAACI1195H1ZM", "pan": "AAACI1195H"},
    "fiscal_year": {"name": "2026-2027"},
    "company_gstins": ["29AAACI1195H1ZI"],
    "hsn_codes": [{"name": "8471"}],
    "inward_supply": null
  }
}
```

Because `blocks` is a subset, this response is informational only —
`auto_create_allowed` is `false` regardless of outcome:

```jsonc
{
  "status": "success",
  "message": "Validation green.",
  "data": {
    "ok": true, "verdict": "green",
    "auto_create_allowed": false,   // ← partial: true forces this
    "review_required": true,
    "matching_mode": null,           // "routing" wasn't in blocks
    "partial": true,
    "checks": [ /* … */ ],
    "invoice_ref": "…"
  }
}
```

To get a real `auto_create_allowed`, re-call with `blocks` omitted (the full default
sequence) and `context` covering every block you intend to run — reusing `invoice_ref`
from this call so the payload can't drift between the two.

---

## 10. Implementation notes for a caller

- **Gate every write on `data.auto_create_allowed` — never on `ok` or `verdict`.** A
  green verdict only says nothing failed; it says nothing about what ran.
- **`skipped[]` is not `passed[]`.** A skipped fraud check is not a cleared one — surface
  it to whoever reviews the invoice.
- Rate limit is 60/min; back off on `429` like any other Frappe endpoint.
- If you call block-by-block across a multi-turn flow, always finish with one full-sequence
  call before treating the invoice as clean.

---

## 11. What this API does not do (yet)

- **No Purchase Invoice creation.** This is a validation contract only. Creating the
  draft PI is a separate, unbuilt phase (`VALIDATION_API_MAP.md` Stage 7) that will live
  in this app's own Python, off ERPNext's mappers — not something a caller does with the
  validation result today.
- **No persistence / upload history.** Checks that need "have we seen this file/QR
  before" (V-DUP-05/06) are unimplemented for that reason.
- **No non-PO gating** beyond the generic Stage 0–3 checks.

See [`VALIDATION_API_MAP.md`](VALIDATION_API_MAP.md) §6 for the current build backlog if
you're picking up work here rather than just calling the API.
