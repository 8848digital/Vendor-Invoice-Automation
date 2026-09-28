# Macro: Invoice check

Chains `invoice-extract` → `invoice-duplicate` → `invoice-fraud` in one run. Source of
truth for one `Jarvis Macro` record; Macros → New Macro, then copy the fields across.

## Record settings

| field | value |
|---|---|
| `macro_name` | `Invoice check` |
| `description` | Extract an attached vendor invoice, then check it for duplicates and confirm the supplier's identity. |
| `enabled` | on |
| `stop_on_error` | **on** — steps 2 and 3 both need step 1's `invoice_ref` (step 3 also needs the resolved Supplier name); a failed extraction must not let either check run against nothing. |
| `skip_confirmation` | **off** — it arms the uncarded-write bypass. Same boundary as `allow_approve_run` on the skills: an invoice image is untrusted input read by a model holding write tools, and the confirmation card on `create_doc` is what keeps a human in that loop. |
| `schedule_enabled` | off — a run is per-invoice, not per-day. |

**Do not press Summarize.** A merged macro runs all three steps as one turn, and the
whole point of the split is that step 1 mints the `invoice_ref` and steps 2 and 3
validate against it. `merged_prompt` set → `run_macro` executes the summary and the
checkpoint is gone.

## Steps

### 1. Extract — tag skill `invoice-extract`

```
Process the vendor invoice in the file named {invoice file name}. Read its pages with
jarvis__get_file_pages, transcribe it, validate the extraction and mint the invoice_ref.
End your reply with the invoice_ref and the resolved Supplier name, each on its own line,
or the word BLOCKED and one line saying why. Nobody is reading this conversation while it
runs: do not ask me anything — anything you cannot resolve goes to a Jarvis Approval
Request, then end the turn.
```

### 2. Duplicate check — tag skill `invoice-duplicate`

```
Take the invoice_ref from step 1 and run the duplicate check on it. If that step reported
BLOCKED or produced no invoice_ref, say so in one line and stop — do not re-read the
invoice and do not re-transcribe it. Report the failed checks as a table and create
nothing; a duplicate goes to a Jarvis Approval Request naming the existing document, then
end the turn.
```

### 3. Supplier identity check — tag skill `invoice-fraud`

```
Take the invoice_ref and resolved Supplier name from step 1 and run the supplier identity
check on it. If that step reported BLOCKED or produced no invoice_ref, say so in one line
and stop — do not re-read the invoice and do not re-transcribe it. Report the failed
checks as a table and create nothing; a failure goes to a Jarvis Approval Request naming
the supplier and the failed checks, then end the turn.
```

## `{invoice file name}` is literal

Macro prompts have no parameter substitution — a step's prompt is enqueued verbatim.
Edit step 1's filename before each run (Macros → the macro → Run), or drop the file in
the File Box instead, which routes to a different, already-directed path.

## Why the steps do not ask questions

`run_macro` opens a *fresh* conversation and chains the steps back to back. A question
in step 1 gets no answer before step 2 fires, so all three steps treat the run as
unattended and park anything human into a `Jarvis Approval Request` — the same fallback
all three skills already describe for the File Box.
