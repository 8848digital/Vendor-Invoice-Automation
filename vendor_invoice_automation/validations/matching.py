"""Requirements 10 & 11 — PO matching and GRN matching.

The whole design rests on one observation: **ERPNext already knows what a Purchase
Invoice against this PO or this receipt is supposed to look like.** Rather than
re-deriving "what is still billable" from `qty`, `billed_amt`, `received_qty`,
`rejected_qty` and `returned_qty` by hand, we ask ERPNext's own mapper to build the
expected invoice and diff the supplier's document against it.

    erpnext…purchase_order.mapper.make_purchase_invoice(po)
    erpnext…purchase_receipt.mapper.make_purchase_invoice(pr)

That single call already enforces, for free and consistently with what `insert()`
would later do: PO submitted, line not closed, line not already fully billed,
pending qty net of what is booked, received less rejected less returned, plus every
rate, UOM, conversion factor and tax the order carries.

Tolerances are ERPNext's, never ours, via `get_allowance_for` — the same function the
mappers themselves use. So a verdict here cannot disagree with the eventual insert.

Requirement 11's traffic light falls out of severity:

    exact                     Pass    green
    differs, within allowance Fail/Warning  yellow
    beyond allowance          Fail/Error    red
"""

import frappe
from frappe.utils import flt

from .base import ERROR, FAIL, PASS, SKIP, WARN, row, verdict

PO_STAGE, GRN_STAGE = "po_matching", "grn_matching"

# ERPNext's own rate threshold — utilities/transaction_base.py:validate_rate_with_reference_doc.
RATE_EPSILON = 0.01


# --------------------------------------------------------------------------- expected


def _expected(doctype, name):
	"""The invoice ERPNext would build from this document. Returns (doc, error).

	The mapper throws for a draft or cancelled source (its `validation` clause) and
	for a closed or on-hold order — which is the answer we want, as a message rather
	than a traceback.
	"""
	if doctype == "Purchase Order":
		from erpnext.buying.doctype.purchase_order.mapper import make_purchase_invoice
	else:
		from erpnext.stock.doctype.purchase_receipt.mapper import make_purchase_invoice

	try:
		return make_purchase_invoice(name), None
	except Exception as e:
		return None, frappe.utils.strip_html(str(e)) or type(e).__name__


def _by_item(doc):
	"""Expected lines folded by item_code, since a pre-insert OCR payload carries no
	`po_detail`/`pr_detail` row ids — `item_code` is the only key available.

	Quantities and amounts add up. Rates stay a set: the same item may sit on one
	order twice at two prices, and either is legitimate.
	"""
	out = {}
	for line in doc.get("items") or []:
		agg = out.setdefault(line.item_code, frappe._dict(
			rates=set(), qty=0.0, amount=0.0, uoms=set(), warehouses=set(), rows=[]))
		agg.rates.add(flt(line.rate))
		agg.qty += flt(line.qty)
		agg.amount += flt(line.qty) * flt(line.rate)
		if line.get("uom"):
			agg.uoms.add(line.uom)
		if line.get("warehouse"):
			agg.warehouses.add(line.warehouse)
		agg.rows.append(line)
	return out


def _allowance(item_code, qty_or_amount, **kwargs):
	"""ERPNext's Item-then-global allowance lookup. Returns a percentage."""
	from erpnext.controllers.status_updater import get_allowance_for

	return flt(get_allowance_for(item_code, qty_or_amount=qty_or_amount, **kwargs)[0])


# --------------------------------------------------------------------------- req 10


def po_match(p):
	"""Requirement 10 — compare the invoice against its Purchase Order."""
	po = p.get("po_number")
	if not po:
		return [row("V-PO-01", PO_STAGE, ERROR, SKIP, "Invoice carries no PO number.")]

	expected, error = _expected("Purchase Order", po)
	if error:
		# Not billable is a real answer, and a blocking one: never auto-create against
		# an order ERPNext itself refuses to invoice.
		return [row("V-PO-01", PO_STAGE, ERROR, FAIL,
			f"{po} cannot be invoiced: {error}", "a submitted, open, unbilled PO", po)]

	return [
		_party(p, expected, po),
		*_line_checks(p, _by_item(expected), PO_STAGE, "V-PO"),
	]


def _party(p, expected, po):
	"""V-PO-03/04/05 — supplier, company and currency, straight off the mapped doc."""
	off = []
	for field, claimed in (
		("supplier", p.get("supplier")),
		("company", p.get("company")),
		("currency", p.get("currency")),
	):
		want = expected.get(field)
		if claimed and want and claimed != want:
			off.append(f"{field}: invoice {claimed} vs order {want}")

	return row("V-PO-03/04/05", PO_STAGE, ERROR, verdict(not off),
		f"Invoice does not belong to {po}." if off
		else f"Supplier, company and currency match {po}.",
		"same supplier, company and currency", off or None)


# --------------------------------------------------------------------------- req 11


def grn_match(p):
	"""Requirement 11 — compare the invoice against what was actually received.

	Every submitted receipt against the order is mapped and the expected lines are
	merged, because one invoice legitimately covers several partial receipts.
	"""
	po = p.get("po_number")
	receipts = frappe.get_all("Purchase Receipt Item",
		filters={"purchase_order": po, "docstatus": 1}, pluck="parent", distinct=True) if po else []

	if not receipts:
		return [row("V-GRN-02", GRN_STAGE, ERROR, FAIL,
			f"No submitted Purchase Receipt against {po}; nothing was received to invoice.",
			"at least one submitted Purchase Receipt", "none")]

	merged, errors = {}, []
	for pr in receipts:
		expected, error = _expected("Purchase Receipt", pr)
		if error:
			errors.append(f"{pr}: {error}")
			continue
		for item_code, agg in _by_item(expected).items():
			into = merged.setdefault(item_code, frappe._dict(
				rates=set(), qty=0.0, amount=0.0, uoms=set(), warehouses=set(), rows=[]))
			into.rates |= agg.rates
			into.uoms |= agg.uoms
			into.warehouses |= agg.warehouses
			into.qty += agg.qty
			into.amount += agg.amount
			into.rows += agg.rows

	out = [row("V-GRN-02", GRN_STAGE, ERROR, verdict(bool(merged)),
		f"Receipts against {po} have nothing left to invoice: {errors}" if not merged
		else f"Received against {po}: {', '.join(receipts)}.",
		"receipted qty left to invoice", errors or list(receipts))]

	if merged:
		out += _line_checks(p, merged, GRN_STAGE, "V-GRN")
		out.append(_warehouse_batch_serial(p, merged))
	return out


def _warehouse_batch_serial(p, expected):
	"""V-GRN-05..08 — warehouse, batch and serial, only where the invoice states them.

	An invoice naming no warehouse is normal, not a mismatch; only a *disagreement*
	counts. Batch and serial live in two places depending on how the receipt was
	entered (`use_serial_batch_fields`), so both are gathered.
	"""
	off = []
	for line in p.get("items") or []:
		agg = expected.get(str(line.get("item_code") or ""))
		if not agg:
			continue

		if (wh := line.get("warehouse")) and agg.warehouses and wh not in agg.warehouses:
			off.append(f"{line['item_code']} warehouse: invoice {wh} vs received {sorted(agg.warehouses)}")

		for field in ("batch_no", "serial_no"):
			claimed = line.get(field)
			if not claimed:
				continue
			received = {r.get(field) for r in agg.rows if r.get(field)}
			if received and claimed not in received:
				off.append(f"{line['item_code']} {field}: invoice {claimed} vs received {sorted(received)}")

	return row("V-GRN-05/06/07/08", GRN_STAGE, ERROR, verdict(not off),
		"Invoice cites a warehouse, batch or serial that was not received." if off
		else "Warehouse, batch and serial agree with the receipts (or the invoice states none).",
		"same warehouse / batch / serial", off or None)


# --------------------------------------------------------------------------- the diff


def _line_checks(p, expected, stage, prefix):
	"""The shared diff: every line of the invoice against what is still billable."""
	lines = p.get("items") or []
	if not lines:
		return [row(f"{prefix}-07", stage, ERROR, FAIL, "Invoice has no lines to match.")]

	matched = [(line, expected[code]) for line in lines
		if (code := str(line.get("item_code") or "")) in expected]

	return [
		_material(lines, expected, stage, prefix),
		_quantity(matched, stage, prefix),
		_rate(matched, stage, prefix),
		_amount(matched, stage, prefix),
		_uom(matched, stage, prefix),
	]


def _material(lines, expected, stage, prefix):
	"""Material — every invoice line must be something still billable. A line that is
	not is either an unordered extra or an item ERPNext considers fully billed; both
	are blocking."""
	unknown = [str(line.get("item_code") or "(no item_code)") for line in lines
		if str(line.get("item_code") or "") not in expected]
	return row(f"{prefix}-07", stage, ERROR, verdict(not unknown),
		f"Invoice lines that are not billable here: {unknown}" if unknown
		else "Every invoice line resolves to something still billable.",
		"every line billable", unknown or None)


def _quantity(matched, stage, prefix):
	"""Quantity, against ERPNext's own over-receipt allowance."""
	if not matched:
		return row(f"{prefix}-10", stage, ERROR, SKIP, "No line resolved; nothing to compare.")

	exact, within, over = True, [], []
	for line, agg in matched:
		billed, pending = flt(line.get("qty")), flt(agg.qty)
		if abs(billed - pending) < RATE_EPSILON:
			continue
		exact = False
		allowance = _allowance(line["item_code"], "qty")
		ceiling = pending * (100 + allowance) / 100
		detail = f"{line['item_code']}: {billed} vs {pending} available (+{allowance}%)"
		(over if billed > ceiling else within).append(detail)

	return _traffic_light(f"{prefix}-10", stage, exact, within, over,
		"Quantity", "the billable quantity")


def _rate(matched, stage, prefix):
	"""Rate. ERPNext expresses this as a switch, not a band — `maintain_same_rate`
	against a 0.01 epsilon — so there is no percentage to widen it with."""
	if not matched:
		return row(f"{prefix}-11", stage, ERROR, SKIP, "No line resolved; nothing to compare.")

	enforced, action, override_role = frappe.get_cached_value("Buying Settings", None,
		["maintain_same_rate", "maintain_same_rate_action", "role_to_override_stop_action"])

	off = [f"{line['item_code']}: {flt(line.get('rate'))} vs {sorted(agg.rates)}"
		for line, agg in matched
		if all(abs(flt(line.get("rate")) - r) >= RATE_EPSILON for r in agg.rates)]

	if not enforced:
		return row(f"{prefix}-11", stage, WARN, verdict(not off),
			"Rate differs, but Buying Settings does not maintain the same rate through "
			"the purchase cycle." if off else "Every billed rate matches.",
			"the ordered rate", off or None)

	# "Warn", and a held override role, are both non-blocking in ERPNext. Mirror that
	# rather than turning red on a document ERPNext would accept.
	blocking = action == "Stop" and override_role not in frappe.get_roles()
	return row(f"{prefix}-11", stage, ERROR if blocking else WARN, verdict(not off),
		"Invoice rate differs from the ordered rate." if off else "Every billed rate matches.",
		"the ordered rate", off or None)


def _amount(matched, stage, prefix):
	"""Amount, against ERPNext's over-billing allowance."""
	if not matched:
		return row(f"{prefix}-12", stage, ERROR, SKIP, "No line resolved; nothing to compare.")

	override_role = frappe.get_cached_value("Accounts Settings", None, "role_allowed_to_over_bill")
	exact, within, over = True, [], []
	for line, agg in matched:
		billed, expected_amount = flt(line.get("amount")), flt(agg.amount)
		if abs(billed - expected_amount) < RATE_EPSILON:
			continue
		exact = False
		allowance = _allowance(line["item_code"], "amount")
		ceiling = expected_amount * (100 + allowance) / 100
		detail = f"{line['item_code']}: {billed:.2f} vs {expected_amount:.2f} billable (+{allowance}%)"
		(over if billed > ceiling else within).append(detail)

	if over and override_role in frappe.get_roles():
		# ERPNext would accept this document, so it must not go red.
		within, over = within + over, []

	return _traffic_light(f"{prefix}-12", stage, exact, within, over,
		"Amount", "the billable amount")


def _uom(matched, stage, prefix):
	"""UOM. A different unit makes every quantity comparison above meaningless, so it
	is blocking even though the numbers may look close."""
	off = [f"{line['item_code']}: {line.get('uom')} vs {sorted(agg.uoms)}"
		for line, agg in matched
		if line.get("uom") and agg.uoms and line["uom"] not in agg.uoms]
	return row(f"{prefix}-09", stage, ERROR, verdict(not off),
		"Invoice UOM differs from the order's." if off else "UOM matches on every line.",
		"the ordered UOM", off or None)


def _traffic_light(check_id, stage, exact, within, over, label, expected_text):
	"""Requirement 11's green / yellow / red, as one audit row."""
	if exact:
		return row(check_id, stage, ERROR, PASS, f"{label} matches exactly.", expected_text)
	if over:
		return row(check_id, stage, ERROR, FAIL,
			f"{label} exceeds what is billable, beyond ERPNext's allowance.",
			expected_text, over + within)
	return row(check_id, stage, WARN, FAIL,
		f"{label} differs but stays within ERPNext's allowance.", expected_text, within)
