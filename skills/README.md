# Jarvis skills for vendor invoice validation

One skill per validation block, mirroring the API's `blocks` parameter — so each is
independently usable in chat, and a Jarvis Macro can chain them into the whole flow.

These files are the source of truth. Each maps 1:1 onto a `Jarvis Custom Skill` record:
frontmatter `name` → `skill_name`, `description` → `description`, body → `instructions`.

| file | block(s) | status |
|---|---|---|
| `invoice-extract.md` | `extraction` | ready |
| `invoice-duplicate.md` | `duplicate` | ready |
| intake, fraud, einvoice, gst, itc, po-match, grn-match | — | not written yet |

`macro-invoice-check.md` is not a skill — it is the source of truth for a `Jarvis Macro`
record that chains `invoice-extract` into `invoice-duplicate`.

## Installing one

Skills → New Skill, then copy the fields across. Record settings, for every skill here:

- `enabled` on, `user_invocable` on
- `allow_approve_run` **off** — it arms the `_SKILL_AUTORUN_COVERED` bypass, which lets
  writes apply without a confirmation card. Leaving it off is what keeps `create_doc`
  human-gated, and that gate is the real prompt-injection boundary: an invoice image is
  untrusted input read by a model holding write tools.
- `scope` **Org**, with no `allowed_roles` rows — only Org-scope, unrestricted, enabled,
  non-learned rows are eligible for the container push. A User- or Role-scoped skill is
  never written to disk, so the model cannot auto-match it by description.

Deployment is not automatic: someone with the skill-reviewer right runs
`custom_skills_api.apply_custom_skills()`, which pushes to the tenant container and
restarts it.

## How the skills reach the API

Through `jarvis__run_method`, not HTTP. `validate_invoice` is a `@frappe.whitelist()` method
on this same site, so `run_method` calls it in-process under the chatting user's identity —
which is why the skills name no URL. There is nothing to configure and no SSRF surface: the
model supplies a method *name*, and `run_method` refuses anything that is not whitelisted.

**This is a stopgap, not the intended shape.** `run_method` only works because
`vendor_invoice_automation` is installed on the same bench as Jarvis — Jarvis has no
outbound-HTTP tool today (confirmed against `jarvis/tools/registry.py`'s full tool list; a
live chat once *claimed* an `exec`/`web_fetch`/`browser` tool when asked directly — that was
a hallucination, none of those names exist in the registry). The intended architecture is
`vendor_invoice_automation` as a genuinely separate, standalone API server — it's already
built for that (`allow_guest=True`, rate-limited, no local DB reads). The Jarvis team has
been asked to add a real outbound-HTTP call path; when that lands, §4's call site becomes an
HTTP POST to an operator-configured URL instead, and `vendor_invoice_automation` no longer
needs installing alongside Jarvis at all.

Two consequences, both load-bearing:

- **Every call parks a confirmation card.** `run_method` is in `_GATED_WRITES` and always
  gates, even though ours is a pure read. In attended chat that is one extra click per
  block. **Unattended it stalls** — nobody clicks a card raised from the File Box or a
  scheduled run, so those paths hang at the first validation call until someone opens the
  conversation. This is the same limitation that already kept `invoice-po-match` and
  `invoice-grn-match` to attended chat; it now applies to every skill here. Uncarding it
  means arming `allow_approve_run` or macro `skip_confirmation`, and both also uncard
  `create_doc` — see the settings above for why that trade is refused.
- **The response arrives in the receipt, not as a tool result.** A gated call returns
  nothing inline; after Confirm, Jarvis feeds the model a line reading
  `… succeeded. Returned: {…}` carrying the full, untruncated payload. The skills say to
  read `invoice_ref` and the check rows out of that receipt and nowhere else — a model that
  narrates a result it never saw is the failure mode this wording exists to prevent.

If an operator sets `jarvis_run_method_allowlist` in `site_config.json` (recommended, and
unset on this bench), it must include `vendor_invoice_automation.api.v1.invoice.*` or every
skill here fails closed with a PermissionDeniedError.

One rough edge: `validate_invoice` carries `@rate_limit(limit=60, seconds=60)`, which frappe
keys by request IP. Reached through `run_method`, that IP is the agent container's, so the
whole tenant shares one 60-per-minute bucket instead of one per user.

## Why `invoice-extract` also runs the `extraction` block

The plan had a separate `invoice-extraction-check`. Minting an `invoice_ref` requires an API
call, and the natural call to make while extracting is the one that validates the extraction
— arithmetic, tax split, HSN shape, fiscal year, buyer GSTIN. Splitting it would mean two
calls to do one thing, so the skills are ten, not eleven.

## The contract

`CONTEXT.md` in the repo root is the full per-key contract: what each block needs and
exactly how to fetch it. `validation_blocks()` returns the same table at runtime.
