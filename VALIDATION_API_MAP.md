# Validation ↔ API Map

Companion to [`SPEC.md`](SPEC.md). For every validation ID in SPEC §5: **what
implements it, what it calls, and whether it works today.**

Bench: Frappe/ERPNext **v17-dev**, `india_compliance` **develop** (installed).
Both differ from what SPEC.md assumes — see [§4 Corrections](#4-corrections-to-specmd).

---

## 1. Flow

This phase is **stateless**. The caller extracts the invoice and passes the values in;
the app validates and returns a status. Nothing is stored, nothing is written.

```
Jarvis: file intake + extraction        ← V-INT-01/02/03, V-EXT-06 happen HERE
   · extension / size / page count            and never reach this API
   · PDF opens cleanly
   · file_hash not seen before
   · extract (QR / e-invoice JSON / XML / text PDF / LLM)
        │
        │  POST /api/method/vendor_invoice_automation.api.v1.invoice.validate_invoice
        │  { "invoice": { supplier, company, invoice_no, invoice_date, supplier_gstin,
        │      company_gstin, place_of_supply, po_number, taxable_value, cgst, sgst,
        │      igst, cess, round_off, grand_total, declared:{…}, items:[…] },
        │    "blocks": ["intake", "gst"] }        ← optional; omit to run them all
        ▼
api/v1/invoice.py          parse · delegate · format   ← transport only, no rules
        │
        ▼
validations/pipeline.py    validate(p, blocks=None)   runs a sequence of BLOCKS
        │
        ├─ "intake"      Stage 0   V-INT-04…07
        ├─ "extraction"  Stage 1   V-EXT-03…10
        ├─ "fraud"       Stage 2   V-DUP-*, V-FAKE-*
        ├─ "gst"         Stage 3   V-GST-*      → india_compliance
        ├─ "routing"     Stage 4   → matching_mode (no rows; a decision, not a check)
        ├─ "matching"    Stage 4a/5  PO modes only (unbuilt, fails closed)
        └─ "tolerance"   Stage 4b  V-PO-10/11/12  → ERPNext's own limits
        │
        ▼
validations/decision.py    gate(rows, mode)          Stage 6
        │
        ▼
api/v1/response_formatter.py   api_response(success, data, message)
        │
        ▼
{ status, message, timestamp,
  data: { ok, verdict, auto_create_allowed, review_required,
          matching_mode, exception_type, failed[], skipped[], checks[] } }
```

**Layout** — `api/v1/` is transport only; every rule lives in `validations/`, one
module per SPEC stage, so a stage can be read, tested and changed on its own.

```
vendor_invoice_automation/
├── api/v1/
│   ├── invoice.py              @frappe.whitelist() — parse, delegate, format
│   └── response_formatter.py   the shared envelope
├── validations/
│   ├── base.py                 row(), severities, results, settings()
│   ├── gst_utils.py            glue over india_compliance (pan_of, gstin_error, …)
│   ├── intake.py               Stage 0
│   ├── extraction.py           Stage 1
│   ├── fraud.py                Stage 2
│   ├── gst.py                  Stage 3
│   ├── routing.py              Stage 4
│   ├── matching.py             Stage 4a/5 — pending, fails closed
│   ├── decision.py             Stage 6 gate + exception_type ranking
│   └── pipeline.py             orchestration
└── tests/
    └── test_validate_invoice.py
```

30 check rows are emitted on a clean non-PO invoice today; 11 come back `Skipped`.

**Three deliberate omissions in this phase:**

1. **No persistence.** Checks comparing against *previously uploaded* invoices are
   impossible — the `DROPPED` rows in §2.
2. **No non-PO gating.** The V-NPO-* family was removed — see §4.
3. **No Purchase Invoice creation.** Stage 7 is unbuilt. When it lands it runs here, in
   Python, off ERPNext's own mappers.

`pipeline.validate()` short-circuits after Stage 0 if the Supplier does not resolve:
nothing downstream is meaningful without the Supplier master.

**Blocks.** Each stage is a named block in `pipeline.BLOCKS`, taking a shared `ctx` and
returning audit rows. `validate(p, blocks)` runs the names you give, in the order you
give them; omitting `blocks` runs `DEFAULT_SEQUENCE` — the SPEC §5 order above.
`"matching"` routes itself when `"routing"` is not in the sequence, so any block stacks
alone. `validation_blocks()` returns the names over the API.

---

## 2. The map

`Our function` is in `vendor_invoice_automation/validations/`. Status legend:

| Status | Meaning |
| --- | --- |
| **BUILT** | Runs today at full fidelity |
| **PARTIAL** | Runs, but covers less than the spec asks |
| **SKIPPED** | Emits `result: "Skipped"` — genuinely unknown data for *this* invoice |
| **SILENT** | Emits no row at all. Held by decision, or its cause is already reported by another row — see the rule below |
| **CALLER** | Jarvis owns it and passes the result in. **Never appears in `checks[]`** |
| **DROPPED** | Impossible while stateless, and unassigned |
| **REMOVED** | Deliberately deleted from scope |
| **PENDING** | Designed, not written |

> **On CALLER rows:** the API does not accept an attestation that Jarvis ran these. There
> is no `intake_ok: true` field and there should not be — emitting `Pass` on someone
> else's word would launder an unverified claim into our audit trail.

> **What earns a `Skipped` row.** One rule: *a human could act on it, for this invoice.*
> A row that says the same thing in every response forever is a constant, not
> information, and it buries the two skips that do matter. So three kinds are silent:
> **held by decision** (V-DUP-05/06, V-GST-11a — recorded here instead), **absent
> optional input** (V-DUP-02 with no IRN), and **a cause another row already reports**
> (V-GST-15/17 and V-ITC-01 when there is no 2B row — V-GST-16 says so). Where several
> checks share one cause, one row carries it and names the others: no `qr_payload`
> yields a single V-FAKE-02, not five identical rows.
>
> **Silent is not Pass.** A silent check appears in neither `checks[]`, `skipped[]`, nor
> `failed[]`, so nothing claims it succeeded.

### Stage 0 — Intake · `validations/intake.py`

| ID | Asserts | Our function | Calls | Status |
| --- | --- | --- | --- | --- |
| V-INT-01 | Extension allowed, size ≤ max, pages ≤ max | — | — | **CALLER** — Jarvis holds the file |
| V-INT-02 | PDF opens cleanly, not password-protected | — | — | **CALLER** — Jarvis holds the file |
| V-INT-03 | `file_hash` (SHA-256) not seen before | — | — | **CALLER** — Jarvis keeps the upload history |
| V-INT-04 | Resolves to exactly one Supplier | `intake.run` | `frappe.db.exists("Supplier", …)` | **BUILT** |
| V-INT-05 | Supplier enabled, not on hold | `intake.run` | `Supplier.disabled` / `.on_hold` / `.hold_type` / `.release_date` | **BUILT** |
| V-INT-06 | Supplier has GSTIN + PAN on file | `intake.run` | `Supplier.gstin` / `.pan` | **BUILT** |
| V-INT-07 | Date not future, within N days back | `intake.run` | `Settings.max_invoice_age_days` | **BUILT** |

### Stage 1 — Extraction validations · `validations/extraction.py`

Extraction itself is the caller's job. Only the post-extraction validations live here.

| ID | Asserts | Our function | Calls | Status |
| --- | --- | --- | --- | --- |
| V-EXT-01 | Payload schema conformance | — | — | **PENDING** — only `dict`/JSON shape is enforced today |
| V-EXT-02 | Extracted fields agree with QR/e-invoice ground truth | `einvoice._agrees_with_document` | `jwt.decode` | **BUILT** — see Stage 2c (V-FAKE-04) |
| V-EXT-03 | qty × rate = amount, per line | `extraction.run` | `frappe.utils.flt` | **BUILT** |
| V-EXT-04 | Σtaxable + Σtax + round_off = grand_total (±₹1) | `extraction.run` | `Settings.monetary_agreement_tolerance` | **BUILT** — total recomputed, never trusted |
| V-EXT-05 | CGST+SGST xor IGST, never both | `extraction.run` | — | **BUILT** |
| V-EXT-06 | Double-extraction agreement (LLM path) | — | — | **CALLER** — Jarvis extracts, so Jarvis compares |
| V-EXT-07 | Declared vs extracted grand total within ₹1 | `extraction.run` | `payload["declared"]["grand_total"]` | **BUILT** — `Skipped` when no declared value is sent |
| V-EXT-08 | HSN/SAC present, valid length | `extraction.run` | `india_compliance.gst_india.constants.VALID_HSN_LENGTHS` | **BUILT** (Warning) |
| V-EXT-09 | Invoice date in an open Fiscal Year | `extraction._fiscal_year` | `erpnext.accounts.utils.get_fiscal_year` | **PARTIAL** — Period Closing Voucher not consulted |
| V-EXT-10 | `company_gstin` is a registered company GSTIN | `extraction._company_gstin` | `india_compliance.gst_india.utils.get_gstin_list(company, "Company")` | **BUILT** |

### Stage 2a — Duplicate · `validations/duplicate.py` — **requirement 7**

One query fetches every Purchase Invoice carrying this bill number for this supplier;
the four key fields are then compared in Python, because "same number, different
amount" is a different answer from "same everything". No `docstatus` filter — a
cancelled invoice was still seen.

| ID | Asserts | Our function | Calls | Status |
| --- | --- | --- | --- | --- |
| V-DUP-01 | Same GSTIN + invoice no + date + amount already booked | `duplicate._exact` | `frappe.get_all("Purchase Invoice", …)` on `supplier_gstin`/`bill_no`/`bill_date`/`grand_total` | **BUILT** — requirement 7's reject condition |
| V-DUP-02 | Same IRN reported against a different invoice | `duplicate._irn` | `GST Inward Supply.irn_number` | **BUILT** — 2B is the only store of an *inbound* IRN. Silent when the invoice carries no IRN |
| V-DUP-05 | Same QR seen before | — | — | **SILENT** — needs an upload history; decision on hold |
| V-DUP-06 | Same file hash seen before | — | — | **SILENT** — needs an upload history; decision on hold |
| V-DUP-07 | Invoice number seen before with different details | `duplicate._same_number_different_amount` | same query as V-DUP-01 | **BUILT** (Warning) — names which fields differ |

> **V-DUP-05/06 are one decision, not two.** Both need a `Vendor Invoice Log` keyed by
> `qr_hash` / `file_hash`; a unique index would then enforce them with no comparison
> code at all. Held deliberately — the rows say so rather than passing silently.

### Stage 2b — Identity · `validations/fraud.py`

| ID | Asserts | Our function | Calls | Status |
| --- | --- | --- | --- | --- |
| V-FAKE-01 | Document GSTIN = Supplier master GSTIN | `fraud._gstin_is_the_suppliers` | `Supplier.gstin` | **BUILT** |
| V-FAKE-07 | PAN in GSTIN = Supplier PAN | `fraud._pan_matches` | `gst_utils.pan_of` + `Supplier.pan` | **BUILT** — a same-PAN, different-state GSTIN is caught by V-FAKE-01, not here |

### Stage 2c — e-Invoice · `validations/einvoice.py` — **requirement 8**

The supplier's signed QR (`payload["qr_payload"]`), verified offline. **Decoding and
verifying are separate:** decoding proves the printed page agrees with its own QR
(catches alteration); only the RSA signature check proves NIC issued it (catches
forgery). Decoding always runs; verification needs a certificate and reports `Skipped`
without one — never `Pass`.

| ID | Asserts | Our function | Calls | Status |
| --- | --- | --- | --- | --- |
| V-FAKE-02 | QR JWS signature verifies against NIC's certificate | `einvoice._signature` | `jwt.decode` + `cryptography.x509`, cert from `base.nic_public_certificate()` | **BUILT** — `Skipped` until `via_nic_public_certificate` is in `site_config.json` |
| V-FAKE-04 | QR header values = the printed document's | `einvoice._agrees_with_document` | `jwt.decode` | **BUILT** — invoice no, total, date |
| V-GST-08 | Seller GSTIN on the QR = the document's | `einvoice._seller_gstin` | — | **BUILT** |
| V-GST-09 | Buyer GSTIN on the QR = our company GSTIN | `einvoice._buyer_gstin` | — | **BUILT** — an e-invoice issued to someone else is not ours to book |
| V-GST-10 | IRN on the document = IRN inside the signed QR | `einvoice._irn` | — | **BUILT** |

> **Why not NIC's `GetIRNDetails`?** `EInvoiceAPI.get_e_invoice_by_irn` sends
> `gstin: company_gstin` and is scoped to invoices *we* generated — india_compliance's
> own client lists `2283: "IRN details cannot be provided as it is generated more than
> 2 days ago"` as expected. It cannot verify a supplier's IRN. The QR can.

### Stage 3 — GST · `validations/gst.py`

Everything here calls into `india_compliance` rather than reimplementing it, per SPEC §5.
The app's own `gstin.py` stand-in has been **deleted**.

| ID | Asserts | Our function | Calls | Status |
| --- | --- | --- | --- | --- |
| V-GST-01/02 | GSTIN format, check digit, state code | `gst_utils.gstin_error` | `india_compliance.gst_india.utils.validate_gstin` | **BUILT** |
| V-GST-03 | GSTIN status Active (now) | `gst.run` | `…doctype.gstin.gstin.get_gstin_status` | **BUILT** — `Skipped` when no `GSTIN` row exists |
| V-GST-04a | GSTIN Active **as on the invoice date** | `gst.run` | `…doctype.gstin.gstin.validate_gstin_status(doc, transaction_date, throw=True)` | **BUILT** — already in india_compliance; SPEC is wrong that we must write it (§4) |
| V-GST-05 | Composition supplier → zero tax | `gst._composition` | `Supplier.gst_category == "Registered Composition"` | **BUILT** |
| V-GST-07 | PAN in GSTIN = Supplier PAN | `gst._supplier_pan` | `Supplier.pan` + `india_compliance…is_valid_pan` | **BUILT** |
| V-GST-11a | E-invoice-mandated supplier carries an IRN | — | needs a per-supplier turnover flag | **SILENT** — no such field on Supplier |
| V-GST-14b | Tax rate correct | `po_match` | `Purchase Order Item` rates | **MOVED** — a rate is only wrong against a reference; compared to the order in Stage 4a, so no row here |
| V-GST-12/13 | Place of supply real; CGST/SGST vs IGST correct | `gst._place_of_supply` | `india_compliance.gst_india.utils.get_state` | **BUILT** |
| V-GST-14 | HSN/SAC valid, tax rate matches | `gst._hsn_registered` | `GST HSN Code` DocType | **PARTIAL** — existence only; the rate half arrives with Stage 4a's PO tax comparison |
| V-GST-15 | Reverse charge correctness | `gst._reverse_charge` | `GST Inward Supply.is_reverse_charge` vs payload `is_reverse_charge` | **BUILT** — blocking: it decides who pays the tax |
| V-GST-17 | Supplier has filed the GSTR-1 carrying this invoice | `gst._return_filing_status` | `GST Inward Supply.gstr_1_filled` / `is_supplier_return_filed`, `gstin.get_gstr_1_filed_upto` | **BUILT** (Warning) — unfiled is a timing problem, not an invalid invoice |
| V-ITC-01 | ITC status: Eligible / Blocked / RCM / ISD / Ineligible / Provisional | `itc._classify` | `GST Inward Supply.itc_availability` / `reason_itc_unavailability` / `classification` | **BUILT** (Info) — GSTN's own determination, never re-derived |
| V-GST-16 | Invoice reflected in GSTR-2B, and the values agree | `gst._reflected_in_2b` | `gst_2b.inward_supply` — taxable value + each tax head | **BUILT** — Info severity, non-blocking by design |

> **Unknown is not invalid** (SPEC §8). When no local `GSTIN` row exists and the GSTN API
> is not enabled in `GST Settings`, V-GST-03 and V-GST-04a return `Skipped` — never
> `Fail`. A missing status must not reject a legitimate supplier.

### Stage 4 — Routing · `validations/routing.py` — **BUILT**

```python
po_number present + any stock line  → "3-Way"   → Stage 4a + Stage 5
po_number present, no stock line    → "2-Way"   → Stage 4a
no po_number                        → "Non-PO"  → no further checks
```

Calls `frappe.db.get_value("Item", …, "is_stock_item")`.

> SPEC's fuller **PO identification order** (extraction → IRN payload → unique open-PO
> match by supplier+amount → line-item overlap scoring) is **PENDING**. Today only an
> explicitly supplied `po_number` is used.

### Stage 4a — PO matching · `validations/matching.py` — **requirement 10**

Built on one call: `erpnext…purchase_order.mapper.make_purchase_invoice(po)` returns the
invoice ERPNext would itself create, so "what is still billable" is never re-derived
here. The block is then a diff, and tolerances are ERPNext's own via
`get_allowance_for` — the same function the mappers use, so a verdict here cannot
disagree with what `insert()` would later do.

| ID | Asserts | Reads | Status |
| --- | --- | --- | --- |
| V-PO-01 | PO exists, submitted, open, with something left to bill | the mapper's own `validation` + item `condition` | **BUILT** — a mapper refusal is a blocking Fail, never auto-created |
| V-PO-03/04/05 | Supplier, company and currency match the PO | the mapped doc | **BUILT** |
| V-PO-07 | Every invoice line is still billable | mapped items by `item_code` | **BUILT** — an unresolved line Skips the numeric checks rather than passing them |
| V-PO-09 | UOM matches | mapped `uom` | **BUILT** — blocking: a different unit makes every qty comparison meaningless |
| V-PO-10 | Quantity within tolerance | `get_allowance_for(item, "qty")` → `Item` then `Stock Settings.over_delivery_receipt_allowance` | **BUILT** — green / yellow / red |
| V-PO-11 | Rate variance | `Buying Settings.maintain_same_rate` / `_action` / `role_to_override_stop_action`, 0.01 epsilon | **BUILT** — see the caveat below |
| V-PO-12 | Amount within tolerance | `get_allowance_for(item, "amount")` → `Item` then `Accounts Settings.over_billing_allowance`, waived by `role_allowed_to_over_bill` | **BUILT** — green / yellow / red |
| V-PO-06 | PO not already fully billed | the mapper's item `condition` (`billed_amt`) | **BUILT** — implicit; a fully-billed line is simply not billable, so V-PO-07 catches it |

> **Rate has no percentage band, and cannot have one from ERPNext.**
> `maintain_same_rate` is a switch against a 0.01 epsilon, not a tolerance. Requirement
> 10's "Rate ±1%" is therefore *not expressible* under the ERPNext-settings-only
> decision. Qty and amount percentages are real and configurable
> (`over_delivery_receipt_allowance`, `over_billing_allowance`, global or per Item);
> rate is exact-match-or-flag. Reopening this means a setting of our own.

### Stage 4b — Non-PO · **REMOVED**

The entire V-NPO-01…12 family is deleted, along with `validations/non_po.py`. Non-PO invoices are created independently of this
pipeline, so there is nothing here to gate them on — `matching_mode` reports `"Non-PO"`
and only the generic Stage 0–3 checks apply.

**Consequences** — see §4 for what this leaves stranded:

- SPEC §5's rule *"Non-PO Ad-hoc never auto-creates, however clean every check comes
  back"* no longer holds. A clean non-PO invoice now returns
  `auto_create_allowed: true`. The independent-corroboration argument the spec makes for
  that rule has not gone away; it is simply no longer this API's problem.
- The `Expense Booking Rule` and `Recurring Expense Profile` DocTypes are now unused.

### Stage 5 — GRN matching · `validations/matching.py` — **requirement 11** (3-Way only)

Same shape, driven by `erpnext…purchase_receipt.mapper.make_purchase_invoice(pr)`, which
already nets received − rejected − returned − already-invoiced. Every submitted receipt
against the order is mapped and merged, because one invoice legitimately covers several
partial receipts.

| ID | Asserts | Reads | Status |
| --- | --- | --- | --- |
| V-GRN-02 | ≥1 submitted Purchase Receipt with something left to invoice | `Purchase Receipt Item.purchase_order`, `docstatus=1` | **BUILT** |
| V-GRN-07/09/10/11/12 | Material, UOM, quantity, rate, amount vs what was received | merged mapper output | **BUILT** — shares the Stage 4a diff |
| V-GRN-05/06/07/08 | Warehouse, batch and serial | `Purchase Receipt Item.warehouse` / `batch_no` / `serial_no` | **BUILT** — compared only where the invoice states them; silence is not a mismatch |
| V-GRN-09 | Quality Inspection accepted | `Purchase Receipt Item.quality_inspection` | **PENDING** |
| V-GRN-10 | PR date ≤ invoice date | `Purchase Receipt.posting_date` | **PENDING** (Warning) |

> Requirement 11's traffic light is severity: exact → `Pass` (green); differs but within
> ERPNext's allowance → `Fail`/`Warning` (yellow); beyond it → `Fail`/`Error` (red).
> `decision.gate` already turns those into the verdict, so nothing extra was added.

### Stage 6 — Decision gate · `validations/decision.py` — **BUILT**

```
any Error-severity Fail        → verdict "red",    auto_create_allowed = False
else any Warning-severity Fail → verdict "yellow", auto_create_allowed = Settings.auto_create_on_yellow
else                           → verdict "green",  auto_create_allowed = True
```

`exception_type` is derived by `decision.exception_type()` from the first failed ID, using
the `EXCEPTION_BY_CHECK` table in `validations/decision.py`.

### Stage 7 — Create Draft Purchase Invoice · **entirely PENDING**

Confirmed to live **in this app's Python**, not the caller's. Jarvis only reports.

| Path | Will call |
| --- | --- |
| GRN-backed | `erpnext.stock.doctype.purchase_receipt.mapper.make_purchase_invoice(pr_name)` |
| PO-backed, no GRN | `erpnext.buying.doctype.purchase_order.mapper.make_purchase_invoice(po_name)` |

| ID | Asserts before `insert()` | Status |
| --- | --- | --- |
| V-PI-01 | `pi.grand_total` = extracted total (±₹1) | **PENDING** |
| V-PI-02 | Tax breakup matches extracted CGST/SGST/IGST/Cess | **PENDING** |
| V-PI-03 | Every line has expense account + cost center | **PENDING** |
| V-PI-04 | Posting date in an open period | **PENDING** |
| V-PI-05 | Budget check passes, if enforced | **PENDING** |
| V-PI-06 | Mandatory dimensions populated | **PENDING** |
| V-PI-07 | `bill_no` still unique at insert time | **PENDING** — re-run the `duplicate` block |
| V-PI-08 | `docstatus` stays 0 — assert, never auto-submit | **PENDING** |
| V-PI-09 | TDS applied where 194Q applies | **PENDING** — `apply_tds` / `tax_withholding_group`, **not** `tax_withholding_category`; see §4 |
| V-PI-10 | MSME due date stamped if Udyam-registered | **PENDING** |

---

## 3. Response contract

Endpoint: `vendor_invoice_automation.api.v1.invoice.validate_invoice`
Argument: `invoice` — a dict, or a JSON string.

Responses use the house envelope (`api/v1/response_formatter.py`); the validation
result is under `data`.

```json
{
  "status": "error",
  "message": "Fraud Suspected",
  "timestamp": "2026-09-02 18:04:11",
  "data": {
    "ok": false,
    "verdict": "red",
    "auto_create_allowed": false,
    "review_required": true,
    "matching_mode": "2-Way",
    "exception_type": "Fraud Suspected",
    "failed":  ["V-FAKE-01", "V-PO-01"],
    "skipped": ["V-FAKE-02", "V-GST-03"],
    "checks": [
      {"check_id": "V-FAKE-01", "stage": "fraud", "severity": "Error", "result": "Fail",
       "expected": "27AAACI1195H1ZM", "found": "29AAACI1195H1ZI",
       "message": "GSTIN on the document is not the supplier's registered GSTIN."}
    ]
  }
}
```

`severity` ∈ `Info | Warning | Error` · `result` ∈ `Pass | Fail | Skipped`.

A malformed payload returns `status: "error"` with `error_code: "BAD_REQUEST"` and no
`data` — distinguishable from an invoice that was validated and rejected.

**Gate writes on `data.auto_create_allowed`, not on `data.ok`.** `ok` only means no
Error-severity check failed; it ignores the yellow-verdict setting. `status` mirrors
`ok`, so it carries the same caveat.

---

## 4. Corrections to SPEC.md

Verified against installed source. Each contradicts the spec.

| SPEC says | Actually, here |
| --- | --- |
| §1 Frappe/ERPNext **v15** | **v17-dev**. `india_compliance` needs its `develop` branch (`version-16` pins `frappe <17.0.0` and bench will refuse it) |
| §5 Stage 3: V-GST-04a **"You build this"** — the app only validates "now" | **False.** `validate_gstin_status(gstin_doc, transaction_date, throw)` already compares against `registration_date` and `cancelled_date`. It is a call, not an implementation |
| §5 Stage 7 `…purchase_receipt.purchase_receipt.make_purchase_invoice` | `erpnext.stock.doctype.purchase_receipt.**mapper**.make_purchase_invoice` |
| §5 Stage 7 `…purchase_order.purchase_order.make_purchase_invoice` | `erpnext.buying.doctype.purchase_order.**mapper**.make_purchase_invoice` |
| §5 Stage 7 / V-PI-09 "set `tax_withholding_category` on the created PI" | **PI has no such field in v17.** It has `apply_tds`, `tax_withholding_group`, and a `tax_withholding_entries` child table. `tax_withholding_category` is on **Supplier** only |
| §3.1 / §5 V-DUP-02 assume an IRN is recorded against booked invoices | **Purchase Invoice has no `irn` field, even with india_compliance.** IRNs live on `GST Inward Supply` (`irn_number`), which records what the supplier *filed*, not what we booked. V-DUP-02 needs a custom field before it can work |
| §5 Stage 5 V-GRN-03 "received qty" | **Purchase Receipt Item has no `accepted_qty`** — use `received_qty` / `qty` / `rejected_qty` |
| §5 Stage 0 cites **V-DUP-06** | **Never defined.** The Stage 2 table jumps 05 → 07. Dangling reference in the spec |
| §3.7 `Expense Booking Rule`, §3.8 `Recurring Expense Profile` | **Now unused.** Both existed only for the non-PO path, which has been removed. Delete them, or keep them for a future non-PO phase |
| §7 makes the non-PO ceiling and intake limits app settings | **Dead config.** `Vendor Invoice Settings`.`non_po_ceiling` (non-PO removed) and `.allowed_file_extensions` / `.max_file_size_mb` / `.max_page_count` (V-INT-01 is Jarvis's) are read by nothing |

---

## 5. What the caller owns

Confirmed as Jarvis's, and **absent from `checks[]`** — the API never sees the file:

- **V-INT-01** extension / size / page count
- **V-INT-02** PDF opens cleanly, not password-protected or corrupt
- **V-INT-03** `file_hash` (SHA-256) not seen before — Jarvis keeps the upload history
- **V-EXT-06** double-extraction agreement, since Jarvis does the extraction

Jarvis's by consequence, whether or not it was chosen:

- **Everything before extraction** — QR decode, e-invoice JSON/XML parse, LLM extraction.
- **Deduplication by QR or file hash.** V-DUP-05/06 need an upload history nothing
  stores today, so a *rescanned* copy of an invoice we already booked is caught only by
  V-DUP-01's four-field key — which is enough unless the resend also alters a field.
- **All non-PO gating.** V-NPO-01…12 are removed; nothing here checks a non-PO invoice's
  ceiling, expense account, TDS section, or whether stock items snuck in without a PO.
- **Reading `skipped[]`.** `ok: true` with a non-empty `skipped[]` means *nothing caught
  it and several things never looked*. A skipped fraud check is not a passed one.

**Permissions note:** `get_gstin_list` calls `frappe.has_permission("Company", …,
throw=True)`. The user calling `validate_invoice` needs read access to the Company, or
V-EXT-10 raises rather than returning a check row.

---

## 6. Build order from here

Requirements 7–11 are built. What is left:

| # | Work | Unblocks | Needs first |
| --- | --- | --- | --- |
| 1 | **Put NIC's public certificate in `site_config.json`** as `via_nic_public_certificate` | turns V-FAKE-02 from `Skipped` into real forgery detection — the highest fraud-protection-per-line-of-code left, and it is config, not code | the certificate |
| 2 | **Set the tolerances requirement 10 asks for** — `Stock Settings.over_delivery_receipt_allowance`, `Accounts Settings.over_billing_allowance` (both are `0` today, so *any* variance is red and nothing can ever be yellow) | requirement 10/11's yellow band | a decision on the numbers |
| 3 | **Stage 7 — create the Draft PI** | V-PI-01…10 | auto-create-on-Yellow default (SPEC §10); v17 TDS model per §4 |
| 4 | **`Vendor Invoice Log` DocType** (`qr_hash`, `file_hash`, composite key) | V-DUP-05/06 — with unique indexes, almost no code | the held decision |
| 5 | **Enable the GSTN API** in `GST Settings` | V-GST-03/04a from `Skipped` to live; keeps GSTR-2B current, which V-GST-15/16/17 and V-ITC-01 all read | India Compliance Account credits |
| 6 | **Quality Inspection + PR-date checks** | V-GRN-09, V-GRN-10 | — |

Items 1 and 2 are configuration, not code, and both change validation outcomes
materially. Do them before reading any verdict as authoritative.

---

## 7. Jarvis integration — SPEC §6.1 answered

**A Skill has no action field.** `Jarvis Custom Skill` is `skill_name` + `description` +
`instructions` (Long Text) — prose for the agent. There is no declarative
"action = call this method". An agent reaches this app through the generic `run_method`
tool (`jarvis/jarvis/tools/run_method.py`), which takes a dotted path to any
`@frappe.whitelist()` method.

**A Trigger can watch a field-level change.** `Jarvis Trigger` carries `target_doctype`,
`doc_event` (`validate`, `after_insert`, `on_update`, …), a Python `condition`, and
`action_type` of `Script` (with `script_body` or a linked `Server Script`) or `LLM`.
A field transition is `on_update` + a condition comparing against `get_doc_before_save()`.
**`action_type: Script` keeps the LLM out of the path entirely.**

**`run_method` and `create_doc` both park a confirmation card.** Both are in
`_GATED_WRITES` (`jarvis/jarvis/api.py:744`) and skip confirmation only inside an armed
Macro or an approved Skill run (`_ARMED_SKIP_COVERED`, `jarvis/jarvis/api.py:792`).
Consequence: **caller-side PI creation is not unattended automation** — a human confirms
every invoice. Part of why Stage 7 belongs in this app's Python.

**`Jarvis Approval Request` is an ask surface, not an exception store.** Rows are
materialised from a ` ```jarvis-ask ` fence in an assistant turn
(`jarvis/jarvis/chat/chat_asks.py`) and are scoped to a `Jarvis Conversation`. It carries
`ref_doctype` / `ref_name`, so a future hold record can be **pointed at** from it rather
than stored in it.
