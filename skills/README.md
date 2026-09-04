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

## Before these work

Each skill has a `CALL SITE` comment where it posts to the validation API. **Jarvis has no
outbound-HTTP tool yet** — that is being added. When it lands, replace that comment in each
file with the real call. The endpoint must come from operator config; a model-supplied URL
would turn a fixed-host call into a general SSRF primitive for anyone who can chat.

`invoice-po-match` and `invoice-grn-match` additionally need ERPNext's mappers, reachable
only through `run_method`, which is currently in `_GATED_WRITES` and parks a confirmation
card on every call — stalling the unattended File Box path. Until read-only `run_method` is
ungated, run those two only in attended chat.

## Why `invoice-extract` also runs the `extraction` block

The plan had a separate `invoice-extraction-check`. Minting an `invoice_ref` requires an API
call, and the natural call to make while extracting is the one that validates the extraction
— arithmetic, tax split, HSN shape, fiscal year, buyer GSTIN. Splitting it would mean two
calls to do one thing, so the skills are ten, not eleven.

## The contract

`CONTEXT.md` in the repo root is the full per-key contract: what each block needs and
exactly how to fetch it. `validation_blocks()` returns the same table at runtime.
