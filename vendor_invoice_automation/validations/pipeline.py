"""Composition: named validation blocks, and a runner that executes a sequence of them.

A block is `fn(ctx) -> rows`. `ctx` carries the payload and whatever an earlier block
decided (`mode`), so any block can be run alone or stacked in any order:

    validate(p)                             # every block, in order
    validate(p, ["duplicate"])              # just requirement 7
    validate(p, ["gst", "itc"])             # stack the ones you want
"""

from . import decision, duplicate, einvoice, extraction, fraud, gst, intake, itc, matching, routing
from .base import FAIL
from .routing import PO_MODES, THREE_WAY


def _intake(ctx):
	rows = intake.run(ctx["invoice"])
	# Nothing downstream is meaningful without a Supplier master, so stop the sequence.
	if any(r["check_id"] == "V-INT-04" and r["result"] == FAIL for r in rows):
		ctx["stop"] = True
	return rows


def _routing(ctx):
	"""Routing is a decision, not a check: it leaves `mode` in ctx and no rows."""
	ctx["mode"] = routing.run(ctx["invoice"])
	return []


def _mode(ctx):
	"""Every matching block runs standalone too, so route first if `routing` was not
	in the sequence."""
	if "mode" not in ctx:
		_routing(ctx)
	return ctx["mode"]


def _po_match(ctx):
	return matching.po_match(ctx["invoice"]) if _mode(ctx) in PO_MODES else []


def _grn_match(ctx):
	"""GRN matching is 3-Way only: a service PO has nothing to receive."""
	return matching.grn_match(ctx["invoice"]) if _mode(ctx) == THREE_WAY else []


BLOCKS = {
	"intake": _intake,
	"extraction": lambda ctx: extraction.run(ctx["invoice"]),
	"duplicate": lambda ctx: duplicate.run(ctx["invoice"]),
	"fraud": lambda ctx: fraud.run(ctx["invoice"]),
	"einvoice": lambda ctx: einvoice.run(ctx["invoice"]),
	"gst": lambda ctx: gst.run(ctx["invoice"]),
	"itc": lambda ctx: itc.run(ctx["invoice"]),
	"routing": _routing,
	"po_match": _po_match,
	"grn_match": _grn_match,
}

DEFAULT_SEQUENCE = (
	"intake",
	"extraction",
	"duplicate",
	"fraud",
	"einvoice",
	"gst",
	"itc",
	"routing",
	"po_match",
	"grn_match",
)


def validate(p, blocks=None):
	"""Run `blocks` in order against the payload. Returns the full response body.

	`blocks` defaults to every block. Unknown names raise ValueError.
	"""
	names = list(blocks or DEFAULT_SEQUENCE)
	unknown = [n for n in names if n not in BLOCKS]
	if unknown:
		raise ValueError(f"Unknown validation block(s): {unknown}. Known: {sorted(BLOCKS)}")

	ctx, rows = {"invoice": p}, []
	for name in names:
		rows += BLOCKS[name](ctx)
		if ctx.get("stop"):
			break

	return {**decision.gate(rows, ctx.get("mode")), "checks": rows}
