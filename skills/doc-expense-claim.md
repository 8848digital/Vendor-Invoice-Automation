---
name: doc-expense-claim
description: >
  Document-type profile, loaded by document-check — do not run directly. A receipt an
  employee claims back (one line of an HRMS Expense Claim — there is no separate "travel
  expense" doctype; travel is just one Expense Claim Type). Recognise by: a taxi/cab
  receipt, flight/train/bus ticket, hotel folio, fuel or meal bill, phone bill, or any
  personally-paid business expense — made out to a person, with an amount paid.
user-invocable: false
---

# Profile: Expense Claim

## Recognise by

- Made out to a **person** (passenger, guest, customer, cardholder), not to the company —
  and shows an amount **paid** by that person.
- Common shapes: taxi/cab/ride-hailing receipt, flight/train/bus ticket or boarding pass,
  hotel folio, fuel or toll receipt, meal bill, phone/communication bill, courier or
  stationery receipt, medical bill.
- No GSTIN pair between two registered businesses, and no HSN/SAC line-item table — that
  distinguishes it from `doc-purchase-invoice`.

There is no dedicated "travel expense" doctype in HRMS. Every one of the shapes above becomes
one row of an **Expense Claim** (`Employee` + child table `Expense Claim Detail`), classified
by `expense_type` — a Link to **Expense Claim Type**, where "Travel"/"Travel Expenses" is only
one of several values (alongside `Food`, `Accommodation`, `Medical`, `Communication`,
`Calls`, `Others`, and whatever else a site has configured).

Not this profile: a supplier tax invoice billed to the company with line items and GSTINs
on both sides — that is `doc-purchase-invoice`.

## Extract

Shaped on HRMS `Expense Claim` / `Expense Claim Detail`. Transcribe, never compute; omit
what is not printed.

```json
{
  "employee_name": "…",          "merchant": "…",
  "expense_date": "YYYY-MM-DD",  "receipt_no": "…",
  "expense_type_guess": "…",     "description": "…",
  "from": "…", "to": "…",        "currency": "INR",
  "merchant_gstin": "…",
  "amount": 0, "tax": 0, "total": 0,
  "payment_mode": "…"
}
```

- `employee_name` is the person the receipt is made out to (passenger / guest / cardholder).
- `expense_type_guess` is your reading of the kind of spend, in your own words (taxi, flight,
  hotel, fuel, meal, phone bill…) — **not** a claim that it matches an `Expense Claim Type`
  value on this site. Only `jarvis__get_list` on `Expense Claim Type` can confirm that; state
  the field it maps to only after you've looked, never before.

## Checks

| check_id | check | source | severity | how |
|---|---|---|---|---|
| V-EXP-01 | Employee exists and is Active | jarvis | Error | `jarvis__get_list` on `Employee`, filters `employee_name like %<employee_name>%`, fields `name, employee_name, status`. Pass: exactly one row with `status: Active`. Fail: one row, not Active. Skipped: `employee_name` not printed. Zero or several rows: ask (document-check §6) — do not pick one. |

<!-- ponytail: V-EXP-01 is a placeholder proving a jarvis-source check runs end to end.
     Replace with the real expense-claim checks (duplicate claim, policy limit per
     Expense Claim Type, employee's own trip/Travel Request dates, etc). Arithmetic
     checks (total = amount + tax) go to the API, not here — the model transcribes,
     it does not add up. -->

## Notes

- Read-only. Nothing creates an Expense Claim yet.
