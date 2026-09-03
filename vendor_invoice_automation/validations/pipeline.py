"""Composition: named validation blocks, and a runner that executes a sequence of them.

A block is `fn(ctx) -> rows`. `ctx` carries the payload and whatever an earlier block
decided (`mode`), so any block can be run alone or stacked in any order:

    validate(p)                             # every block, SPEC §5 order
    validate(p, ["intake"])                 # just intake
    validate(p, ["intake", "gst"])          # stack the ones you want
"""

from . import decision, extraction, fraud, gst, intake, matching, routing, tolerance
from .base import FAIL
from .routing import PO_MODES


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


def _matching(ctx):
	# Runs standalone too: route first if `routing` was not in the sequence.
	if "mode" not in ctx:
		_routing(ctx)
	return matching.run(ctx["mode"]) if ctx["mode"] in PO_MODES else []


def _tolerance(ctx):
	if "mode" not in ctx:
		_routing(ctx)
	return tolerance.run(ctx["invoice"], ctx["mode"])


BLOCKS = {
	"intake": _intake,
	"extraction": lambda ctx: extraction.run(ctx["invoice"]),
	"fraud": lambda ctx: fraud.run(ctx["invoice"]),
	"gst": lambda ctx: gst.run(ctx["invoice"]),
	"routing": _routing,
	"matching": _matching,
	"tolerance": _tolerance,
}

DEFAULT_SEQUENCE = ("intake", "extraction", "fraud", "gst", "routing", "matching", "tolerance")


def validate(p, blocks=None):
	"""Run `blocks` in order against the payload. Returns the full response body.

	`blocks` defaults to every block in SPEC §5 order. Unknown names raise ValueError.
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
