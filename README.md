### Vendor Invoice Automation

Supplier invoice intake, validation and Draft Purchase Invoice automation.

**This app is a stateless validation service.** It runs on its own site, separate from the
ERPNext bench whose invoices it validates, and reads no business data of its own — the
caller fetches whatever the checks compare against and sends it as `context`. Nothing is
stored: the only state is a short-lived Redis cache behind `invoice_ref`.

- [`CONTEXT.md`](CONTEXT.md) — the caller contract: what to send, and how to fetch it
- [`VALIDATION_API_MAP.md`](VALIDATION_API_MAP.md) — every validation ID, and what implements it
- [`SPEC.md`](SPEC.md) — the phase specification

Because it is stateless, callers need nothing installed on their own bench: every lookup
`CONTEXT.md` describes is either a plain `/api/resource/` read or an already-whitelisted
ERPNext method.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app vendor_invoice_automation
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/vendor_invoice_automation
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
