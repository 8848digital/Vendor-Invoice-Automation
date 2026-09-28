# Test fixtures

Four synthetic GST tax invoices for exercising `/invoice-extract`, `/invoice-fraud` and
`/invoice-duplicate` end to end. All four come out of `make_test_invoice.py` (needs Pillow —
use the bench env, `frappe-bench/env/bin/python`).

| File | Invoice no. | Expected outcome |
| --- | --- | --- |
| `test-invoice-alpha-systems.png` | ALS/2026-27/0412 | every check that can run, passes |
| `test-invoice-gst-mismatch.png` | ALS/2026-27/0418 | **V-GST-12/13 Fail** (Error) — verdict red |
| `test-invoice-wrong-gstin.png` | ALS/2026-27/0425 | **V-FAKE-01 Fail** (Error) — verdict red |
| `test-invoice-duplicate.png` | ALS/2025-26/0118 | **V-DUP-01 Fail** (Error) — verdict red |

The first three share one supplier, one buyer and one set of line items, so each failing
fixture differs from the clean one in exactly the thing it tests and nothing else. The
duplicate fixture is different in kind: it is copied off a Purchase Invoice that is really
booked on the site, so it is matched against real history rather than a seeded row.

## Shared choices

Chosen so the skill's steps actually resolve rather than stalling on the demo site:

- **Supplier `Alpha Systems Ltd`** is a real Supplier record on 8848hrms-demo, so §3's
  resolve step finds exactly one match.
- **Buyer `8848 DIGITAL`** is the only Company there.
- GSTINs are synthetic but carry correct NIC check digits, so india_compliance's
  `validate_gstin` accepts them: supplier `27AAACI1195H1ZM` (PAN AAACI1195H),
  buyer `27AABCU9603R1ZN`. Both Maharashtra, so every one of these is an **intra-state**
  supply and must carry CGST+SGST rather than IGST (V-GST-12/13).
- Arithmetic is exact and asserted in the generator, so V-EXT-03 and V-EXT-04 pass:
  74,100 taxable + 18% tax = 87,438.00, whichever head carries it.
- The PO field deliberately prints `— (non-PO)` rather than being blank. Real invoices print
  placeholders (`—`, `N/A`, `Nil`) constantly, and a first live run showed the model
  transcribing that string as the `po_number` *value* — which is truthy, so routing would
  have sent a non-PO invoice into PO and GRN matching against an order that does not exist.
  The line stays as the test for the skill's placeholder rule. Correct behaviour is to omit
  `po_number` entirely and route Non-PO.
- The first two are dated Aug 2026: inside the 180-day window and not in the future (V-INT-07). They will
  age out — regenerate, or expect a V-INT-07 warning once they pass 180 days.

## 1. `test-invoice-alpha-systems.png` — the clean one

The baseline. Nothing on it is wrong; anything red in a run against this is the pipeline's
finding, not the fixture's.

## 2. `test-invoice-gst-mismatch.png` — fails the GST block

Identical to the clean invoice except for the invoice number, the date, and the one thing
under test: **a single IGST @ 18% line of 13,338.00 where CGST+SGST @ 9% each belong.**
Supplier state 27, place of supply 27-Maharashtra — intra-state, so IGST is the wrong head.

`gst._place_of_supply` fails it as V-GST-12/13, severity Error, so `verdict: "red"` and
`auto_create_allowed: false`.

The failure is deliberately *isolated*. The taxable value, the total and the arithmetic are
untouched, so V-EXT-03/04 still pass, and only IGST carries value so the xor in V-EXT-05
still passes too. Exactly one row goes red, and it is the GST one.

## 3. `test-invoice-wrong-gstin.png` — fails the fraud block

Identical to the clean invoice except for the invoice number, the date, and the one thing
under test: the printed supplier **GSTIN reads `29AAACI1195H1ZI` instead of the registered
`27AAACI1195H1ZM`.** Both carry PAN `AAACI1195H` — this is the same legal entity billing
under a different state's GST registration (Karnataka, not Maharashtra), not an impersonation
by a different company.

`fraud._gstin_is_the_suppliers` fails it as **V-FAKE-01**, severity Error. Because the PAN
inside the wrong GSTIN still matches, `fraud._pan_matches` (**V-FAKE-07**) passes — this is
the "V-FAKE-01 alone" row in `skills/invoice-fraud.md`'s bullet table, not the "V-FAKE-01 and
V-FAKE-07" one. Run it through `/invoice-fraud` (`blocks: ["intake", "fraud"]`) against the
`Alpha Systems Ltd` Supplier master, which must carry `gstin: 27AAACI1195H1ZM` for the check
to have anything to compare against — an empty master `gstin` fails V-INT-06 first instead.

## 4. `test-invoice-duplicate.png` — the duplicate case

This is the **supplier's own bill behind `PUR-INV-2026-90365`**, which is already booked on
the site (`docstatus: 1`). Every field V-DUP-01 keys on is copied from that record, so the
check runs against real history instead of a row someone has to seed first:

| On the image | On `PUR-INV-2026-90365` |
| --- | --- |
| Invoice Date `28-01-2026` | `posting_date: 2026-01-28` |
| Grand Total `INR 4,399.80` | `grand_total: 4399.8` |
| `PPR-0802-100` · 10 Nos · 439.98 · 4,399.80 | item `PII-8106f5a112`, same qty/uom/rate/amount |
| `GRN Ref: MAT-PRE-2026-00542` | item `purchase_receipt` |
| No GST line at all | `taxes: []`, `total_taxes_and_charges: 0` |

It is stamped *Duplicate for Supplier* with a reissue note, so it is a different file from
anything else here — deliberately. A byte-identical re-upload is caught by Jarvis's
`file_hash` check (V-INT-03) and never reaches the API, so it would test nothing; this one
has to be caught on its *content*, which is what `duplicate._exact` does.

### Before it can fail: stamp `bill_no` and `bill_date`

**`PUR-INV-2026-90365` carries neither field.** Both are load-bearing and the check is inert
without them:

- `/invoice-duplicate` queries `Purchase Invoice` filtered on `bill_no = {invoice_no}`. With
  `bill_no` empty the query returns nothing, `existing_invoices` is `[]`, and V-DUP-01
  **passes** — the duplicate is never seen.
- Even handed the row directly, `duplicate._matches` compares `hit["bill_date"]` and needs
  both sides non-empty. Empty `bill_date` makes `invoice_date` disagree, so the hit
  downgrades from V-DUP-01 (Error, reject) to **V-DUP-07** (Warning, "look at this") — which
  is correct behaviour, just not the case this fixture is for.

`ALS/2025-26/0118` is this repo's choice, not something the record dictates — the supplier's
bill number was never recorded. Stamp it, matching the image:

```bash
bench --site {your-site} set-value "Purchase Invoice" PUR-INV-2026-90365 bill_no "ALS/2025-26/0118"
```

```bash
bench --site {your-site} set-value "Purchase Invoice" PUR-INV-2026-90365 bill_date "2026-01-28"
```

If you would rather pick a different bill number, change it in this fixture's `FIXTURES`
entry and regenerate, so image and record keep saying the same thing.

`supplier_gstin` is empty on that record too, but that one is harmless: `_matches` reads a
blank GSTIN as an absent value, not a disagreement, so it does not clear the duplicate.

### Two checks fail alongside V-DUP-01, and both are the record's doing

Unlike the GST fixture, this one is not an isolated failure — because the real invoice it
copies is not a clean invoice:

- **V-INT-07** (Warning) — `2026-01-28` is 222 days before 2026-09-07, past
  `MAX_INVOICE_AGE_DAYS = 180`.
- **V-GST-12/13** (Error) — the record carries no tax at all, so the fixture cannot either
  without breaking the ₹4,399.80 amount match that is the entire point. Intra-state expects
  CGST+SGST; `_place_of_supply` finds `"no tax"` and fails. It has no branch for a
  nil-rated or exempt supply, so a genuinely zero-tax invoice fails this check today.

Both are real findings about that invoice, not fixture bugs. If you want the duplicate case
red on V-DUP-01 *alone*, book a fresh recent Purchase Invoice that carries GST and copy its
values instead — the generator takes items, tax heads and totals as parameters.

To exercise **V-DUP-07** instead, change `invoice_date` or the total in this fixture's entry
while leaving the invoice number alone.

## What to expect on the demo site

Extraction and the arithmetic checks should pass. Two things will NOT:

- No Supplier or Company there has a `gstin` set, so V-FAKE-01 / V-GST-07 / V-EXT-10
  have nothing to compare against.

`invoice-extract` and `invoice-duplicate` reach the API through `jarvis__run_method` (see
`skills/README.md`), not HTTP, so the verdict step itself runs fine wherever the API's
whitelisted method is reachable — end-to-end-tested against `test-invoice-alpha-systems.png`
using `_Test Company` / `_Test VIA Supplier` as the GSTIN-matched stand-ins for Alpha Systems
Ltd / 8848 DIGITAL on a site that lacks the demo names: verdict green, `invoice_ref` minted,
and `invoice-duplicate` correctly passed clean and failed V-DUP-01 once seeded as booked.

## 5. `test-travel-expense-taxi.png` — routing, not an invoice

A ride-hailing receipt (`render_taxi_receipt` in the same script), for `/document-check`.
Made out to a person, one trip, a fare and a total paid, no GSTIN pair and no line-item
table — so it must route to `doc-expense-claim` (there is no separate "travel expense"
doctype in HRMS; travel is just one `Expense Claim Type` value among others), never
`doc-purchase-invoice`. Upload it with no message.

The rider prints as `Ritik Sharma`. `V-TE-01` passes only if that is an **Active Employee**
on the site; otherwise regenerate with `render_taxi_receipt(rider="<a real employee_name>")`.
Zero or several matches make the skill ask rather than fail.
