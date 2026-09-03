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
| **SKIPPED** | Emits `result: "Skipped"` — an unbuilt utility, a missing field, or genuinely unknown data |
| **CALLER** | Jarvis owns it and passes the result in. **Never appears in `checks[]`** |
| **DROPPED** | Impossible while stateless, and unassigned |
| **REMOVED** | Deliberately deleted from scope |
| **PENDING** | Designed, not written |

> **On CALLER rows:** the API does not accept an attestation that Jarvis ran these. There
> is no `intake_ok: true` field and there should not be — emitting `Pass` on someone
> else's word would launder an unverified claim into our audit trail.

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
| V-EXT-02 | Extracted fields agree with QR/e-invoice ground truth | — | future `qr.py` | **PENDING** |
| V-EXT-03 | qty × rate = amount, per line | `extraction.run` | `frappe.utils.flt` | **BUILT** |
| V-EXT-04 | Σtaxable + Σtax + round_off = grand_total (±₹1) | `extraction.run` | `Settings.monetary_agreement_tolerance` | **BUILT** — total recomputed, never trusted |
| V-EXT-05 | CGST+SGST xor IGST, never both | `extraction.run` | — | **BUILT** |
| V-EXT-06 | Double-extraction agreement (LLM path) | — | — | **CALLER** — Jarvis extracts, so Jarvis compares |
| V-EXT-07 | Declared vs extracted grand total within ₹1 | `extraction.run` | `payload["declared"]["grand_total"]` | **BUILT** — `Skipped` when no declared value is sent |
| V-EXT-08 | HSN/SAC present, valid length | `extraction.run` | `india_compliance.gst_india.constants.VALID_HSN_LENGTHS` | **BUILT** (Warning) |
| V-EXT-09 | Invoice date in an open Fiscal Year | `extraction._fiscal_year` | `erpnext.accounts.utils.get_fiscal_year` | **PARTIAL** — Period Closing Voucher not consulted |
| V-EXT-10 | `company_gstin` is a registered company GSTIN | `extraction._company_gstin` | `india_compliance.gst_india.utils.get_gstin_list(company, "Company")` | **BUILT** |

### Stage 2 — Duplicate & fraud · `validations/fraud.py`

Every layer runs; it does not stop at the first hit.

| ID | Asserts | Our function | Calls | Status |
| --- | --- | --- | --- | --- |
| V-DUP-02 | Same IRN exists elsewhere | `fraud.run` | — | **SKIPPED** — Purchase Invoice has no `irn` column even with india_compliance; see §4 |
| V-DUP-03 | Same (GSTIN, invoice no, date, total) exists | `fraud.run` | — | **DROPPED** — needs upload history |
| V-DUP-04 | Same supplier + `bill_no` already on a PI (incl. cancelled) | `fraud.run` | `frappe.get_all("Purchase Invoice", …)` — no docstatus filter | **BUILT** |
| V-DUP-05 | Invoice no. differs by ≤2 chars from an existing one | `fraud.run` | — | **DROPPED** — needs upload history |
| V-DUP-07 | Same invoice no., different amount | `fraud.run` | — | **DROPPED** — needs upload history |
| V-FAKE-01 | Document GSTIN = Supplier master GSTIN | `fraud.run` | `Supplier.gstin` | **BUILT** |
| V-FAKE-02 | QR JWS signature verifies against NIC public key | `fraud.run` | future `qr.py` + NIC cert | **SKIPPED** — highest-value unbuilt piece, see §6 |
| V-FAKE-04 | QR payload = document's own header values | `fraud.run` | future `qr.py` | **SKIPPED** |
| V-FAKE-07 | PAN in GSTIN = Supplier PAN | `fraud.run` | `gst_utils.pan_of` + `Supplier.pan` | **BUILT** — meaningful now that `pan` is a real, independent field |

> **V-DUP-03/05/07 are the same capability as V-INT-03.** All four need a history of prior
> uploads, and Jarvis now owns that history. If it stores the extracted header alongside
> the file hash, these three come nearly free on the same index — and they catch what a
> hash cannot: the *same invoice re-sent as a different file* (rescanned, re-exported,
> one pixel changed). **Unassigned today — decide who owns them.**

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
| V-GST-11a | E-invoice-mandated supplier carries an IRN | `gst.run` | needs a per-supplier turnover flag | **SKIPPED** — no such field on Supplier |
| V-GST-12/13 | Place of supply real; CGST/SGST vs IGST correct | `gst._place_of_supply` | `india_compliance.gst_india.utils.get_state` | **BUILT** |
| V-GST-14 | HSN/SAC valid, tax rate matches | `gst._hsn_registered` | `GST HSN Code` DocType | **PARTIAL** — existence only; the rate half arrives with Stage 4a's PO tax comparison |
| V-GST-15 | Reverse charge correctness | `gst.run` | — | **SKIPPED** — `is_reverse_charge` is not in the payload contract yet |
| V-GST-16 | GSTR-2B presence | `gst._gstr_2b` | `GST Inward Supply` by `supplier_gstin` + `bill_no` | **BUILT** — Info severity, non-blocking by design |

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

### Stage 4a — PO matching · **entirely PENDING**

`matching.run()` emits `V-PO-PENDING` (Error/Fail) so a PO invoice can never
come back green while this is unbuilt. **Fails closed by design.**

| ID | Asserts | Will call | Status |
| --- | --- | --- | --- |
| V-PO-01/02 | PO submitted, not closed/cancelled/on hold | `Purchase Order.docstatus`, `.status` | **PENDING** |
| V-PO-03/04 | Supplier + company match the PO | `Purchase Order.supplier` / `.company` | **PENDING** |
| V-PO-06 | PO not already fully billed | `Purchase Order.per_billed` | **PENDING** |
| V-PO-07/08/09 | Every line resolves to a PO line | `Purchase Order Item.item_code` / `.gst_hsn_code` / `.uom` + our `Supplier Item Mapping` | **PENDING** |
| V-PO-11 | Rate variance within tolerance | `Buying Settings.maintain_same_rate` / `_action` / `role_to_override_stop_action` | **BUILT** — `tolerance.run`, ERPNext's own 0.01 threshold |
| V-PO-12 | Amount variance within tolerance | `Item.over_billing_allowance` → `Accounts Settings.over_billing_allowance`, waived by `role_allowed_to_over_bill` | **BUILT** — `tolerance.run`, cumulative via `Purchase Order Item.billed_amt` |
| V-PO-10 | Qty variance within tolerance | — | **SKIPPED** — ERPNext has no Purchase Invoice qty allowance; `Stock Settings.over_delivery_receipt_allowance` governs the receipt, so it belongs to GRN matching |
| V-PO-13 | GST rate matches PO tax template | `Purchase Order Item.igst_rate` / `.cgst_rate` / `.sgst_rate` | **PENDING** |
| V-PO-14 | Cumulative billed + this invoice ≤ PO qty | `Purchase Order Item.billed_amt` / `.qty` | **PARTIAL** — the amount half is V-PO-12 above; qty is unavailable, see V-PO-10 |
| V-PO-16 | No invoice lines absent from the PO | `Purchase Order Item` | **PENDING** |

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

### Stage 5 — GRN matching · **entirely PENDING** (3-Way only)

`matching.run()` emits `V-GRN-PENDING` for 3-Way. Fails closed.

| ID | Asserts | Will call | Status |
| --- | --- | --- | --- |
| V-GRN-02 | ≥1 submitted Purchase Receipt against this PO | `Purchase Receipt Item.purchase_order`, `docstatus=1` | **PENDING** |
| V-GRN-03 | Received qty − already-invoiced qty ≥ this invoice's qty | `Purchase Receipt Item.received_qty` / `.qty` / `.rejected_qty` | **PENDING** |
| V-GRN-05/06 | Item + warehouse match | `Purchase Receipt Item.item_code` / `.warehouse` | **PENDING** |
| V-GRN-07/08 | Batch/serial availability | `Purchase Receipt Item.batch_no` / `.serial_no` | **PENDING** |
| V-GRN-09 | Quality Inspection accepted, if required | `Purchase Receipt Item.quality_inspection` | **PENDING** |
| V-GRN-10 | PR date ≤ invoice date | `Purchase Receipt.posting_date` | **PENDING** (Warning) |
| V-GRN-11 | Partial receipt policy | `Settings.partial_receipt_policy` | **PENDING** — the setting exists, the logic does not |

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
| V-PI-07 | `bill_no` still unique at insert time | **PENDING** — re-run V-DUP-04 |
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
    "failed":  ["V-FAKE-01", "V-PO-PENDING"],
    "skipped": ["V-DUP-02", "V-DUP-03", "V-FAKE-02", "V-GST-03", "V-GST-04a"],
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
- **Deduplication beyond a byte-identical file.** V-DUP-03/05/07 are unassigned; only
  V-DUP-04 survives here. A resubmitted invoice with one byte changed validates clean.
- **All non-PO gating.** V-NPO-01…12 are removed; nothing here checks a non-PO invoice's
  ceiling, expense account, TDS section, or whether stock items snuck in without a PO.
- **Reading `skipped[]`.** `ok: true` with a non-empty `skipped[]` means *nothing caught
  it and several things never looked*. A skipped fraud check is not a passed one.

**Permissions note:** `get_gstin_list` calls `frappe.has_permission("Company", …,
throw=True)`. The user calling `validate_invoice` needs read access to the Company, or
V-EXT-10 raises rather than returning a check row.

---

## 6. Build order from here

| # | Work | Unblocks | Needs first |
| --- | --- | --- | --- |
| 1 | **QR/JWS verification utility** (`qr.py`, offline, NIC public cert) | V-FAKE-02, V-FAKE-04, V-EXT-02 | NIC public certificate |
| 2 | **Stage 4a — PO matching** | V-PO-01…16; removes `V-PO-PENDING` | — |
| 3 | **Stage 5 — GRN matching** | V-GRN-02…11; removes `V-GRN-PENDING` | V-GRN-11 partial-receipt policy decision (SPEC §10) |
| 4 | **Stage 7 — create the Draft PI** | V-PI-01…10 | auto-create-on-Yellow default (SPEC §10); v17 TDS model per §4 |
| 5 | **Custom field `irn` on Purchase Invoice** | V-DUP-02 | — |
| 6 | **Enable the GSTN API** in `GST Settings` | turns V-GST-03/04a from `Skipped` into live checks | India Compliance Account credits |

Step 1 is first for the reason SPEC §9 gives: highest fraud-protection-per-line-of-code
in the project, and it needs no external service.

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
