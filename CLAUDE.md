# vendor_invoice_automation

## Third-party integrations that need IP whitelisting → HOP

Some third parties (TransBnk today) require the calling server's IP to be whitelisted.
Since this app's own egress IP isn't whitelisted, those calls proxy through a shared
relay ("HOP") instead of calling the third party directly.

When you add a **new** third-party integration and the user says something like "this
will call the HOP server" / "this needs whitelisting" / "route this through HOP":

1. Reuse `vendor_invoice_automation.integrations.hop.call(url, method, headers, payload, use_hop)` —
   don't re-implement the proxy envelope. It POSTs `{"url","method","headers","payload"}` to
   `HOP Settings.hop_url` (bearer-auth'd with `HOP Settings.hop_token`) when `use_hop` is
   true, or calls `url` directly when it's false.
2. Add a `use_hop` Check field to *that integration's own* settings doctype (default `1`
   if whitelisting is actually required, `0` otherwise) — don't add anything to `HOP
   Settings` itself, it only holds the shared relay credentials (`hop_url`/`hop_token`),
   used by every integration.
3. Reference implementation: `vendor_invoice_automation/integrations/transbnk.py`
   (`_settings()` + `call()`) — build target url/headers yourself, call `hop.call(...)`,
   then handle `(body, error, duration_ms)` with your own log doctype / thrown exception,
   same shape as `TransBnk Call Log` / `TransBnkError`.

Don't route a call through HOP that doesn't need whitelisting — e.g. `india_compliance`
validation (`validations/gst_utils.py`) is a plain in-process Python import, never HTTP,
and has nothing to do with HOP.
