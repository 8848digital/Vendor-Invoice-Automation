# Vendor Invoice Automation — Implementation Spec

**Scope of this phase:** supplier uploads an invoice via Jarvis → system
extracts, validates, and auto-creates a **Draft Purchase Invoice** in
ERPNext. Nothing after Draft (no approval workflow, no dashboards, no
reports, no payment) — those are later phases.

Drop this file in the repo as `SPEC.md` or `CLAUDE.md` and build against it
section by section, in the order given in **§9 Build Order**. Each stage in
§5 is written so it can become its own PR with its own tests.

---

## 1. Stack & environment

- Frappe/ERPNext **v15**, single company, India GST, B2B/domestic invoices
  (import/SEZ out of scope for now).
- **`india_compliance`** app is already installed — reuse its GSTIN, HSN,
  and GSTR-2A/2B machinery (see §5, Stage 3). Do not build a parallel GST
  validation layer.
- **Jarvis** (`aerele/jarvis`, AGPL-3.0) is installed and is the *front
  door*: suppliers/staff upload invoices through Jarvis chat or File Box.
  Jarvis is a trigger, never a decision-maker — see §6.
- New custom app: **`vendor_invoice_automation`**. All DocTypes, pipeline
  code, and whitelisted API methods live here.
- Background jobs run on the `long` queue. Confirm dedicated worker
  capacity before load-testing (Jarvis's own agents share the same bench
  queues).
- Assumptions to verify at project start and correct if wrong:
  - Supplier master already carries GSTIN, PAN, GST category.
  - No GSP contract needed anywhere in this project (`india_compliance`
    bundles its own NIC/GSTN connectivity via India Compliance Account
    credits — pay-per-use, free on Frappe Cloud).

---

## 2. Architecture overview

```
Supplier uploads invoice (Jarvis chat / File Box)
        │
        ▼
Jarvis Trigger fires → Jarvis Skill calls
vendor_invoice_automation.api.submit()   ◄── the ONLY write entry point
        │
        ▼
submit() creates a `Vendor Invoice` record, enqueues background pipeline,
returns immediately (status: processing)
        │
        ▼
Background job runs Stage 1 → 7 (extraction, dedup/fraud, GST, PO/non-PO
match, GRN match, decision gate, create Draft Purchase Invoice)
        │
        ▼
Vendor Invoice.status changes → a second Jarvis Trigger (or polling via
get_status()) reports the outcome back into chat / Approval Board
```

**The one rule that shapes everything below:** validation and creation
happen inside `vendor_invoice_automation`, authenticated as its own
service logic, never as a decision the LLM makes. Jarvis's Skill has no
ERPNext write tools of its own — see §6.

---

## 3. Data model

### 3.1 `Vendor Invoice` (not submittable — plain DocType with a status field)

Naming: `VIN-.YYYY.-.#####`

| Group | Fields |
| --- | --- |
| Source | `supplier`, `uploaded_by`, `source` (Jarvis File Box / Jarvis Chat / Portal / Email / Manual), `original_file` (Attach), `file_hash` (SHA-256, unique index), `file_type`, `idempotency_key` (unique index) |
| Declared (supplier-typed) | `declared_invoice_no`, `declared_invoice_date`, `declared_gstin`, `declared_grand_total`, `declared_tax_amount` |
| Extracted | `invoice_no`, `invoice_date`, `supplier_gstin`, `company_gstin`, `po_number`, `place_of_supply`, `taxable_value`, `cgst`, `sgst`, `igst`, `cess`, `round_off`, `grand_total`, `irn`, `qr_payload`, `currency` |
| Extraction meta | `extraction_method` (QR / E-Invoice JSON / XML / Text PDF / LLM), `field_provenance` (JSON — page + source text per field) |
| Results | `status`, `exception_type`, `review_required`, `matching_mode` (3-Way / 2-Way / Non-PO Recurring / Non-PO Ad-hoc), `gst_result`, `match_result`, `itc_status` (2B Pending/Matched/Missing) |
| Links | `purchase_order`, `purchase_receipts` (Table MultiSelect), `purchase_invoice`, `gst_inward_supply`, `recurring_expense_profile` |
| Audit | `checks` (child table — see 3.3) |

### 3.2 `Vendor Invoice Item` (child)

`item_code` (nullable), `supplier_part_no`, `description`, `hsn_sac`, `qty`,
`uom`, `rate`, `amount`, `gst_rate`, `tax_amount`, `po_detail`, `pr_detail`,
`match_status`, `variance_qty_pct`, `variance_rate_pct`, `expense_account`,
`cost_center` (last two used on the non-PO path).

### 3.3 `Vendor Invoice Check` (child — the audit trail; write one row per
validation ID as it runs)

`check_id` (e.g. `V-GST-04a`), `stage`, `severity` (Info/Warning/Error),
`result` (Pass/Fail/Skipped), `expected`, `found`, `message`, `timestamp`.

### 3.4 `Supplier Item Mapping`

`supplier`, `supplier_part_no`, `supplier_description`, `item_code`, `uom`,
`conversion_factor`. Populate as a side effect whenever a human resolves a
line manually.

### 3.5 `Vendor Invoice Settings` (Single)

Extraction confidence thresholds, tolerance defaults, auto-create-on-yellow
flag, GRN-required default, retry counts, non-PO ceiling, e-invoice
turnover threshold.

### 3.6 `Vendor Invoice Tolerance Rule`

`scope` (Supplier/Supplier Group/Item Group/Company), `qty_tolerance_pct`,
`rate_tolerance_pct`, `amount_tolerance_pct`, `absolute_floor`, `priority`
(most-specific-wins).

### 3.7 `Expense Booking Rule` (non-PO path)

`supplier`, `hsn_sac`, `description_pattern`, `item_code` (optional),
`expense_account`, `cost_center`, `department`, `project`,
`tax_withholding_category`, `priority`.

### 3.8 `Recurring Expense Profile` (non-PO path)

`supplier`, `expense_account`, `frequency` (Monthly/Quarterly),
`expected_amount`, `variance_tolerance_pct`, `auto_create_allowed`,
`last_invoice_amount`, `cost_owner` (User).

### 3.9 Reused from `india_compliance` — do not re-create

`GSTIN` DocType (status, registration/cancellation dates), `GST Inward
Supply`, `Purchase Reconciliation Tool`, `GST HSN Code`, and the custom
fields it adds to Purchase Invoice (`supplier_gstin`, `company_gstin`,
`place_of_supply`, `gst_category`, `is_reverse_charge`,
`eligibility_for_itc`, `itc_integrated_tax`, `itc_central_tax`,
`itc_state_tax`, `itc_cess_amount`).

---

## 4. Status state machine

```
Uploaded
  ├─→ Rejected (Intake Failed)
  └─→ Extracting
        ├─→ Extraction Failed
        ├─→ Needs Review ──(human fixes fields)──┐
        └─→ Extracted ───────────────────────────┤
                                                  ↓
                                          Fraud/Duplicate Check
                                             ├─→ Rejected (Duplicate)
                                             ├─→ Fraud Flag
                                             └─→ GST Validating
                                                    ├─→ GST Failed
                                                    └─→ Matching (routes by PO presence)
                                                           ├─→ PO Mismatch / PO Not Found
                                                           ├─→ Non-PO Hold
                                                           └─→ GRN Matching (3-way only)
                                                                  ├─→ GRN Mismatch
                                                                  ├─→ Awaiting GRN
                                                                  └─→ Ready to Invoice
                                                                         └─→ Invoice Created
```

Every red/hold state is **resumable**: a human fixes the record and
re-enters the pipeline at that exact stage (`resume()` in §6), never from
the top. Every node writes exactly one `Vendor Invoice Check` row — that
child table is the queryable version of this state machine.

---

## 5. Pipeline stages

### Stage 0 — Intake (synchronous)

| ID | Validation | Fail behaviour |
| --- | --- | --- |
| V-INT-01 | File extension allowed, size ≤ max, page count ≤ max | Reject at upload |
| V-INT-02 | PDF opens cleanly (not password-protected/corrupt) | Reject at upload |
| V-INT-03 | `file_hash` (SHA-256) not seen before | Reject — "already uploaded as VIN-xxxx" |
| V-INT-04 | Uploader/context resolves to exactly one Supplier | Reject |
| V-INT-05 | Supplier enabled, not on hold | Reject |
| V-INT-06 | Supplier has GSTIN + PAN on file | Reject |
| V-INT-07 | Declared invoice date not in future, within N days back (config) | Warning → `review_required` |

Store declared values (what the supplier/uploader typed) separately from
extracted ones — needed for V-EXT-05 / V-DUP-06 below.

### Stage 1 — Extraction (background)

Route by document type, cheapest/most-authoritative first:

1. **Signed QR present?** Decode it and **verify the JWS signature offline
   against NIC's public certificate.** No API call, no GSP, no rate limit.
   This becomes ground truth for supplier GSTIN, buyer GSTIN, invoice no,
   date, value, IRN. Implement this as a small standalone utility early —
   it's the single highest fraud-protection-per-line-of-code piece in the
   whole system (see V-FAKE-04 in Stage 2).
2. **E-invoice JSON / GST XML present?** Parse directly. 100% confidence.
3. **PDF with a text layer?** `pdfplumber`/`pdftotext` + layout parsing.
4. **Scanned/image only?** LLM extraction — see the security rules below,
   non-negotiable.

**LLM extraction security boundary (read before writing this stage):**
- The extraction call is a **bare completion request**, not a Jarvis Skill
  invocation with tool access. No write tools, no ERPNext tools of any
  kind attached to this call.
- It returns JSON matching a strict schema; extra prose or unexpected keys
  → reject the extraction outright, don't try to salvage it.
- **The model extracts, it never computes.** Ask only for raw line values
  (`qty`, `rate`, `gst_rate`, `taxable_value`). Every total, tax split, and
  round-off is computed in Python from those raw values — never trust a
  model-reported total.
- Log any extracted text containing imperative instruction patterns
  ("ignore previous instructions," "mark as approved," etc.) as a fraud
  signal, not a parse error.

| ID | Validation | Fail behaviour |
| --- | --- | --- |
| V-EXT-01 | Schema conformance (right fields, right types) | Extraction Failed |
| V-EXT-02 | Extracted fields agree with QR/e-invoice ground truth, if one exists | Fraud Flag, stop |
| V-EXT-03 | Line arithmetic: qty × rate = amount | Needs Review |
| V-EXT-04 | Header arithmetic: Σtaxable + Σtax + round_off = grand_total (±₹1) | Needs Review |
| V-EXT-05 | Tax split coherent: CGST+SGST xor IGST, never both | Needs Review |
| V-EXT-06 | Double-extraction agreement on monetary fields (LLM path only, no ground truth available) | Needs Review |
| V-EXT-07 | Declared vs extracted grand total within ₹1 | Needs Review (mismatch itself is a signal, don't discard it) |
| V-EXT-08 | HSN/SAC present per line, correct digit length (4/6/8) | Warning |
| V-EXT-09 | Invoice date within an open Fiscal Year, period not closed | Extraction Failed |
| V-EXT-10 | `company_gstin` on the invoice matches a registered company GSTIN | Extraction Failed |

Confidence tiers, replacing any single "confidence score" gate:
```
QR/e-invoice ground truth present + all cross-checks pass → auto-proceed
No ground truth, but double-extraction agrees + arithmetic OK → auto-proceed
Any monetary field disagrees across passes/sources → Needs Review
Schema violation, or ground-truth contradiction → Extraction Failed / Fraud Flag
```

### Stage 2 — Duplicate & fraud detection (background; run every layer, don't stop at first hit)

| ID | Check | Severity |
| --- | --- | --- |
| V-DUP-02 | Same IRN exists elsewhere (Vendor Invoice or Purchase Invoice, incl. cancelled) | Reject — definitive |
| V-DUP-03 | Same (GSTIN, invoice no, date, total) exists | Reject |
| V-DUP-04 | Same supplier+bill_no already on a PI (incl. cancelled PIs) | Reject |
| V-DUP-05 | Invoice no. differs by ≤2 chars from an existing one, same supplier/date/total | Suspected, review |
| V-DUP-07 | Same invoice no., different amount | Suspected, review |
| V-FAKE-01 | Document's GSTIN = Supplier master GSTIN | Fraud Flag, stop |
| V-FAKE-02 | QR JWS signature verifies against NIC public key | Fraud Flag, stop |
| V-FAKE-04 | QR-decoded payload = document's own header values (catches a real IRN copy-pasted onto a fake document) | Fraud Flag, stop |
| V-FAKE-07 | PAN embedded in GSTIN = Supplier PAN | Fraud Flag, stop |

### Stage 3 — GST validation (background — thin wrapper over `india_compliance`)

| ID | Validation | Source |
| --- | --- | --- |
| V-GST-01/02 | GSTIN format + checksum, valid state code | `india_compliance.gst_india.utils.validate_gstin` |
| V-GST-03 | GSTIN status = Active (now) | `india_compliance` `GSTIN` DocType |
| **V-GST-04a** | GSTIN was Active **as on the invoice date** | **You build this** — compare `invoice_date` against `GSTIN.registration_date`/`cancelled_date`; the app only validates "now" |
| V-GST-05 | Composition supplier → invoice carries zero tax | `gst_category` on Supplier |
| V-GST-07 | PAN in GSTIN = Supplier PAN | Existing PAN validation |
| **V-GST-11a** | If supplier is e-invoice-mandated (turnover flag), IRN is present | **You build this** — per-supplier flag |
| V-GST-12/13 | Place of supply valid; CGST/SGST vs IGST correct | `india_compliance` utils |
| V-GST-14 | HSN/SAC valid, tax rate matches | `GST HSN Code` DocType |
| V-GST-15 | Reverse charge: supplier did not charge tax where RCM applies | Existing transaction validations |
| V-GST-16 | GSTR-2B presence | `GST Inward Supply` — **non-blocking**, stamp `itc_status`, reconcile via scheduled job after the 14th |

Do not build GSTIN checksum/status/HSN/place-of-supply validation from
scratch — call into `india_compliance`. Verify exact function paths with
`grep -rn` in `apps/india_compliance` before wiring, since they shift
between minor versions.

### Stage 4 — Routing: PO vs non-PO

```python
if po_number_identified and any(line.is_stock_item for line in lines):
    matching_mode = "3-Way"
elif po_number_identified:
    matching_mode = "2-Way"          # all non-stock/service lines — skip Stage 5
elif matches_active_recurring_profile(supplier, lines):
    matching_mode = "Non-PO Recurring"
else:
    matching_mode = "Non-PO Ad-hoc"  # always ends in HOLD, see decision gate
```

**PO identification order:** `po_number` from extraction → IRN payload
reference field → unique open-PO match by supplier+amount → line-item
overlap scoring across open POs → give up, `PO Not Found`, human links it.

#### Stage 4a — PO matching (3-Way / 2-Way)

| ID | Validation | Severity |
| --- | --- | --- |
| V-PO-01/02 | PO submitted, not closed/cancelled/on hold | Error |
| V-PO-03/04 | Supplier + company match the PO | Error |
| V-PO-06 | PO not already fully billed | Error |
| V-PO-07/08/09 | Every line resolves to a PO line via item/HSN/UOM (use `Supplier Item Mapping`) | Error if unresolved |
| V-PO-10/11/12 | Qty/rate/amount variance within tolerance (scoped `Tolerance Rule`, absolute floor applied) | Yellow within, Red outside |
| V-PO-13 | GST rate matches PO tax template | Error |
| V-PO-14 | Cumulative billed + this invoice ≤ PO qty (+tolerance) — catches over-billing across invoices | Error |
| V-PO-16 | No invoice lines exist that aren't on the PO | Error |

#### Stage 4b — Non-PO checks

| ID | Validation | Severity |
| --- | --- | --- |
| V-NPO-01 | Supplier flagged `allow_non_po_invoice` | Error → Hold |
| V-NPO-02 | Invoice total ≤ non-PO ceiling for this supplier/category | Error → Hold |
| V-NPO-03 | No stock items on the invoice (a stock purchase without a PO is a process failure) | Error → Hold |
| V-NPO-04 | No asset/capex items (must go through PO → Asset creation) | Error → Hold |
| V-NPO-05/06/07 | Every line resolves to an `Expense Booking Rule`; cost center + dimensions resolvable | Error → Hold |
| V-NPO-09 | Matches an active `Recurring Expense Profile` | Routing — NO always forces `Non-PO Ad-hoc` |
| V-NPO-10 | Amount within the profile's variance tolerance vs last N invoices | Yellow within, Red outside |
| V-NPO-12 | TDS section resolvable (`Tax Withholding Category` on Supplier) | Error → Hold |

**`Non-PO Ad-hoc` never auto-creates, however clean every check comes
back.** There's no independent corroborating party for a non-PO invoice
the way a PO+GRN provides one — it always stops for a human. Don't let a
later refactor merge this path's outcome with the recurring path's.

Also capture (data only, no gating logic needed yet):
- **TDS/TCS**: set `tax_withholding_category` on the created PI wherever
  it resolves — 194Q (₹50L cumulative purchase threshold) and 206C(1H)
  interaction; ERPNext's existing withholding machinery handles the rate
  and cumulative tracking once the category is set correctly.
- **MSME (Section 43B(h))**: if supplier is Udyam-registered, stamp the
  45-day (or 15-day, no written agreement) due date on the PI at creation.
  Payment itself is out of scope, but the clock starts at booking.

### Stage 5 — GRN matching (3-Way only; skipped for 2-Way and non-PO)

| ID | Validation | Severity |
| --- | --- | --- |
| V-GRN-02 | ≥1 submitted Purchase Receipt against this PO | Error → Awaiting GRN |
| V-GRN-03 | Received qty − already-invoiced qty ≥ this invoice's qty | Error |
| V-GRN-05/06 | Item + warehouse match | Error |
| V-GRN-07/08 | Batch/serial availability, if tracked | Error |
| V-GRN-09 | Quality Inspection accepted, if required | Error |
| V-GRN-10 | PR date ≤ invoice date | Warning |
| V-GRN-11 | Partial receipt policy: **decide explicitly** — hold until fully received, or allow partial invoice against received qty. Config-driven, not a silent default. |

### Stage 6 — Decision gate

| Mode | GST | Match | Action |
| --- | --- | --- | --- |
| 3-Way / 2-Way | Pass | All Green | Auto-create |
| 3-Way / 2-Way | Pass | Any Yellow | Auto-create, `review_required=1` |
| Non-PO Recurring | Pass | Within variance | Auto-create, `review_required=1` |
| Non-PO Recurring | Pass | Outside variance | Hold |
| **Non-PO Ad-hoc** | — | — | **Hold — always** |
| Any | Fail / Red | — | Hold, `exception_type` set |

`exception_type` values: `OCR Failure`, `Invalid GSTIN`, `Suspended GST`,
`Duplicate`, `Fraud Suspected`, `Price Mismatch`, `Qty Mismatch`, `Missing
GRN`, `Missing PO`, `Invalid HSN`, `Invalid Tax`, `IRN Verification
Failed`, `2B Unavailable`, `Non-PO Ad-hoc (Review Required)`.

### Stage 7 — Create Draft Purchase Invoice (deterministic Python only — never the LLM, never Jarvis directly)

Build from ERPNext's own mappers — do not hand-build the document:
- GRN-backed: `erpnext.stock.doctype.purchase_receipt.purchase_receipt.make_purchase_invoice(pr_name)`
- PO-backed, no GRN: `erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_invoice(po_name)`
- Non-PO: build directly, setting `expense_account`/`cost_center` per line
  from the resolved `Expense Booking Rule`.

Overlay actual extracted values on the mapped doc:
`bill_no`, `bill_date`, `supplier_gstin`, `company_gstin`,
`place_of_supply`, `irn`, `tax_withholding_category`, correct posting date
(`set_posting_time=1`), attach original file, link back
`Vendor Invoice.purchase_invoice`.

| ID | Post-build validation (before `insert()`) | Severity |
| --- | --- | --- |
| V-PI-01 | `pi.grand_total` = extracted grand_total (±₹1) | Abort |
| V-PI-02 | Tax breakup matches extracted CGST/SGST/IGST/Cess | Abort |
| V-PI-03 | Every line has expense account + cost center | Abort |
| V-PI-04 | Posting date in an open period | Abort |
| V-PI-05 | Budget check passes, if enforced | Abort |
| V-PI-06 | Mandatory dimensions populated | Abort |
| V-PI-07 | `bill_no` still unique for this supplier at insert time | Abort |
| V-PI-08 | `docstatus` stays 0 (Draft) — assert, never auto-submit | Assert |
| V-PI-09 | `tax_withholding_category` set if 194Q/TDS applies | Warning if missing |
| V-PI-10 | MSME due date stamped if supplier is Udyam-registered | Warning if missing |

**Idempotency (non-negotiable — background jobs retry):**
```python
existing = frappe.db.get_value(
    "Vendor Invoice", vin.name, "purchase_invoice", for_update=True
)
if existing:
    return  # already created, nothing to do
```
Set `Vendor Invoice.purchase_invoice` in the same transaction/commit as the
PI `insert()`. Pass a deterministic `job_id` to `frappe.enqueue` so retried
enqueues dedupe at the queue level too.

---

## 6. Jarvis integration

**The rule:** Jarvis triggers the pipeline and relays the outcome. It never
decides the outcome. The Skill has no ERPNext write tools bound to it —
all writes happen inside `vendor_invoice_automation`, under its own
service logic.

### 6.1 Verify before building (check the Skill Lab UI on your instance)

1. Can a Skill's action be an HTTP call to an arbitrary domain, or only a
   whitelisted method on the same site?
2. Can an Agent/Skill be configured with an **empty tool list**? (Needed to
   keep Stage 1 LLM extraction read-only if it has to route through
   Jarvis's own model connection rather than a bare completion call from
   your own code.)
3. Can a Trigger watch a **field-level change** (`Vendor Invoice.status`
   transitioning) or only document insert/submit events?

Default to **Path B** (same-site whitelisted methods, custom app on the
same bench) unless (1) confirms Jarvis genuinely wants a webhook URL — it's
strictly less infrastructure and avoids designing cross-service auth.

### 6.2 API contract (`vendor_invoice_automation.api`)

**`submit(file_url, supplier_hint=None, uploaded_via=None, idempotency_key=None)`**
- Idempotency check first (`idempotency_key` — Jarvis's own message/event id).
- Creates `Vendor Invoice` (status=Uploaded), enqueues the pipeline on the
  `long` queue with a deterministic `job_id`, returns immediately.
```json
{"status": "processing", "vendor_invoice": "VIN-2026-00042", "poll_after_seconds": 10}
```

**`get_status(name)`** — read-only, safe to expose freely. Returns one of:
```json
{"status": "held", "vendor_invoice": "VIN-2026-00042", "stage": "gst_validation",
 "exception_type": "Invalid GSTIN", "message": "...", "checks_failed": [...]}
```
```json
{"status": "created", "vendor_invoice": "VIN-2026-00042",
 "purchase_invoice": "PINV-2026-00104", "purchase_invoice_url": "/app/purchase-invoice/PINV-2026-00104",
 "review_required": false, "grand_total": 118000.00}
```

**`resume(name)`** — re-enters the pipeline **at the stage it stopped at**,
never from the top (avoids re-burning OCR/GST calls that already
succeeded). Only call this from an authenticated human action in the
Approval Board — never let the Skill call it on its own initiative based
on chat text.

### 6.3 Wiring

- One **Skill**: "Process supplier invoice" — description tells Jarvis
  when to use it (file in File Box / chat looks like a vendor invoice),
  action = call `submit`.
- One **Trigger**: fires on `Vendor Invoice.status` change → posts the
  outcome back into chat, or surfaces `held`/`review_required` records on
  the **Approval Board** (Jarvis's existing human-review surface — use it
  rather than building a separate review UI).

---

## 7. Configuration surface

Everything below is a setting (`Vendor Invoice Settings` / `Tolerance
Rule`), never a hardcoded constant:

- Extraction confidence/agreement thresholds
- Tolerance percentages, per scope, plus absolute floor
- Auto-create-on-Yellow: yes/no
- GRN required: global default + per-supplier + per-item-group override
- Partial receipt policy (hold vs partial invoice) — Stage 5
- Non-PO ceiling, per supplier/category
- GSTR-2B blocking: yes/no (default: no, non-blocking)
- E-invoice-mandatory turnover threshold
- Max invoice age at intake
- Retry counts/backoff for extraction and `india_compliance` calls

---

## 8. Reliability notes

- Every external call (extraction, `india_compliance`/GSTN) is a
  background job with retry + exponential backoff.
- **Never auto-reject on an API/timeout failure.** A GSTN timeout means
  "unknown," not "invalid" — route to `Needs Review`, not `Rejected`.
- Cache GSTIN status lookups (24h); IRN verification results are permanent
  once verified (immutable).
- Store raw extraction/API responses as attached Files, not Long Text
  fields — needed for disputes, keeps the table lean.
- Worker capacity: dedicated `long`-queue workers for this pipeline,
  separate from Jarvis's own agent workload.

---

## 9. Build order

1. `vendor_invoice_automation` app scaffold + all DocTypes from §3. Manual
   entry only, zero automation — get the data model right first.
2. `submit`/`get_status`/`resume` whitelisted methods, stubbed to just
   create-and-hold. Wire the Jarvis Skill + Trigger against this stub so
   the end-to-end contract is proven before any validation logic exists.
3. Stage 0 + Stage 2 (intake + duplicate detection). Zero external
   dependencies, immediately useful on its own.
4. **QR/JWS verification utility** (offline, self-contained). Do this
   early — highest fraud-protection-per-line-of-code in the project.
5. Stage 1 for e-invoice JSON / XML / text-layer PDF only. **No LLM yet.**
6. Stage 4a + Stage 5 (PO/GRN matching) against clean, manually-entered
   test data — this is the hardest business logic; build it while inputs
   are trustworthy.
7. Stage 4b (non-PO branch): `Expense Booking Rule`, `Recurring Expense
   Profile`, TDS/MSME field capture.
8. Stage 7 (auto-create PI) via ERPNext's own mappers.
9. Stage 3 — thin wrapper over `india_compliance` + the two checks you own
   (V-GST-04a, V-GST-11a).
10. Stage 1 LLM extraction for scanned documents — **last**, once every
    deterministic path works and you have a validated corpus (from steps
    3–9) to measure extraction accuracy against.

Each numbered step above should land as its own PR with fixtures covering:
a clean pass, a failure at that exact stage (not earlier), and a
tolerance-boundary case where relevant — see the worktree validation doc
for the fixture pattern per checkpoint.

---

## 10. Open questions to resolve during development, not before

These don't block starting (§9 step 1–2 don't depend on them), but resolve
before the step that needs them:

- Jarvis Skill/Trigger capabilities (§6.1) — resolve before step 2.
- Partial receipt policy, V-GRN-11 (§5, Stage 5) — resolve before step 6.
- Auto-create-on-Yellow default (§6, decision gate) — resolve before step 8.
- GSTR-2B blocking policy confirmation with finance (§5, Stage 3) —
  resolve before step 9, default assumption is non-blocking.
