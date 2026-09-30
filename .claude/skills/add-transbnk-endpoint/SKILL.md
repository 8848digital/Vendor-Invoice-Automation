---
name: add-transbnk-endpoint
description: Wires a TransBnk/TBX API spec PDF into this app's vendor-onboarding integration (TRANSBNK_ENDPOINTS registry + the stage1-5 requirement-point modules), following the exact pattern already used for the other ~110 endpoints. Use this whenever the user hands over one or more TransBnk API spec PDFs (filenames typically look like "VX-##-###_<Product> API.pdf") and wants the endpoint added, wired up, "created", or made callable — not just documented. Also use it if they ask to fill a gap flagged as NOT_AVAILABLE in list_requirement_points() once they've found a PDF that covers it.
---

# Add a TransBnk endpoint from its spec PDF

This app already has a full TransBnk integration: a HOP-proxy client, a registry of
allowlisted endpoints, and one whitelisted function per vendor-onboarding requirement
point. Adding a new endpoint from a PDF means extending that existing structure by a
line or two — never introducing a new pattern, client, or abstraction next to it.

Read these four files before touching anything, in this order, so every edit matches
established conventions instead of guessing at them:

1. `vendor_invoice_automation/integrations/transbnk_endpoints.py` — the
   `TRANSBNK_ENDPOINTS` registry (`key -> {"path", "stage", "label", "method"?}`) and,
   critically, its module docstring. That docstring documents *deliberate* exclusions
   (every money-movement/collection product, card/GPR issuance — different auth
   contract entirely) and known gaps. Never register an endpoint from either excluded
   category, even if the PDF is right there — flag it to the user instead.
2. `vendor_invoice_automation/api/v1/onboarding/_shared.py` — `_endpoint(path, name,
   doc, method="POST")` builds a whitelisted, rate-limited proxy function;
   `_unavailable(name, reason)` builds a stub that returns a clean `NOT_AVAILABLE`
   error; `_register_stage(stage, globals())` (called once at the bottom of each stage
   file) auto-collects every point in that module.
3. One `api/v1/onboarding/stageN_*.py` file end to end (stage1 is the shortest) — this
   is the exact style to match: one `name = _endpoint(...)` or `name =
   _unavailable(...)` assignment per requirement point, multi-line docstrings that
   read like a spec summary, `_register_stage(N, globals())` at the end.
4. `vendor_invoice_automation/integrations/transbnk.py` — the client itself. Read it to
   understand the auth contract (`x-api-key` only) and confirm the PDF's endpoint
   fits it. **Never edit this file** — an endpoint needing a different auth scheme
   (e.g. card products use `x-client-id`/`x-username`/`x-client-password`) is out of
   scope for this proxy, full stop; tell the user rather than forcing it in.

## What to extract from each PDF

Read the whole PDF, not just the request-body table: HTTP method, path, full request
payload (required/optional fields, types, example values), response shape, which
product/stage it belongs to, and any UAT-vs-PROD base-path or auth note. If the PDF's
text extraction looks glitchy in places (ligatures rendering oddly, a table cell
splitting mid-word), say so rather than silently picking one reading — the existing
registry already has two entries flagged this way (`itr_download_profile`,
`bsa_retrieve_report`), which is the standard to match, not something to clean up.

## Wiring it in

1. **Dedupe first.** Search `TRANSBNK_ENDPOINTS` for the same `path`. If it's already
   there, you're done at the registry level — check instead whether the stage modules
   are missing a named point for it.
2. **Check for a matching `_unavailable(...)` stub.** Grep the stage files for related
   requirement-point names (e.g. a PDF for "PAN to Director DIN Lookup" should be
   checked against `pan_to_director_din_lookup` in stage1). If the PDF's response body
   genuinely answers that point, flip the stub to `_endpoint(...)` — read the stub's
   existing `_unavailable` reason first, since some were deliberately left unavailable
   *after* checking a related endpoint's full response schema (see the
   `mca_director_din_profile` alias in stage1 for what that looks like when it
   resolves the other way, as a field on an existing response rather than a new call).
3. **Pick the stage** using `STAGE_LABELS` in `transbnk_endpoints.py` — match the
   endpoint's subject matter to what's already grouped there (identity/business docs
   -> stage 1, tax/statutory -> stage 2, identity/address/KYC -> stage 3, bank/payment
   readiness -> stage 4, risk/compliance/final approval -> stage 5).
4. **Add the registry entry** in `transbnk_endpoints.py`, in the comment-delimited
   block for that stage, near related entries — not appended at the end of the dict.
   Only add `"method": "GET"` when the PDF says GET; POST is the default.
5. **Add or update the stage-file line** with `_endpoint(...)`. If there's no obvious
   requirement-point name for it (a capability the requirement list never named), it's
   fine to stop at step 4 — the registry entry alone makes it callable through
   `call_transbnk(endpoint=...)`, and inventing a requirement-point name just to have
   one is worse than not having it.
6. **Flag anything uncertain** in the docstring/comment right next to what you added —
   an unverified HTTP method, an ambiguous field, a PDF extraction artifact — the same
   way the existing two flagged entries do. A silent guess here is worse than an
   honest caveat.
7. **Update `TRANSBNK_API_REFERENCE.md`** at the repo root with the new endpoint if
   it's missing from that reference doc. Secondary to the code wiring — don't let it
   block finishing.

## After wiring

Run the existing test suite (or at least import-sanity-check it) rather than declaring
done on inspection alone:

```
bench --site <site> run-tests --app vendor_invoice_automation --module vendor_invoice_automation.tests.test_onboarding
```

If a full test run isn't practical in the current environment, at minimum confirm the
module still imports and `list_requirement_points()` still returns cleanly (no
exceptions, the new/changed point shows up with the right `available` flag) — that
catches typos and import errors, which is the main way this kind of edit breaks.

Report back as a short diff summary: what got added, what got flipped from
unavailable to available, and anything you flagged as uncertain — not a rewritten copy
of the PDF's contents, and don't write a standalone demo/example script to show it
working; the test suite is the check.
