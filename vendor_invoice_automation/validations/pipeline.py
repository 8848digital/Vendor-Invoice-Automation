"""Composition: named validation blocks, and a runner that executes a sequence of them.

A block is `fn(ctx) -> rows`. `ctx` carries the payload and whatever an earlier block
decided (`mode`), so any block can be run alone or stacked in any order:

    validate(p, context=c)                        # every block, in order
    validate(p, ["duplicate"], context=c)         # just requirement 7
    validate(p, ["gst", "itc"], context=c)        # stack the ones you want

`context` is everything the checks compare against, assembled by the caller on its own
site — this API reads no business data of its own. A block whose context key is absent
reports Skipped, never Fail. See CONTEXT.md.
"""

from . import decision, duplicate, einvoice, extraction, fraud, gst, intake, itc, matching, routing
from .base import ERROR, FAIL, unchecked
from .routing import PO_MODES, THREE_WAY, UNKNOWN


def _intake(ctx):
	rows = intake.run(ctx["invoice"], ctx["context"])
	# Nothing downstream is meaningful without a Supplier master, so stop the sequence.
	# A *Skipped* V-INT-04 is not that: it means the caller never looked, which says
	# nothing about whether the Supplier exists, so the sequence continues.
	if any(r["check_id"] == "V-INT-04" and r["result"] == FAIL for r in rows):
		ctx["stop"] = True
	return rows


def _routing(ctx):
	"""Routing is a decision, not a check: it leaves `mode` in ctx and no rows."""
	ctx["mode"] = routing.run(ctx["invoice"], ctx["context"])
	return []


def _mode(ctx):
	"""Every matching block runs standalone too, so route first if `routing` was not
	in the sequence."""
	if "mode" not in ctx:
		_routing(ctx)
	return ctx["mode"]


def _po_match(ctx):
	mode = _mode(ctx)
	if mode == UNKNOWN:
		return [unchecked("V-PO-01", "po_matching", ERROR, "items")]
	return matching.po_match(ctx["invoice"], ctx["context"]) if mode in PO_MODES else []


def _grn_match(ctx):
	"""GRN matching is 3-Way only: a service PO has nothing to receive."""
	mode = _mode(ctx)
	if mode == UNKNOWN:
		return [unchecked("V-GRN-02", "grn_matching", ERROR, "items")]
	return matching.grn_match(ctx["invoice"], ctx["context"]) if mode == THREE_WAY else []


BLOCKS = {
	"intake": _intake,
	"extraction": lambda ctx: extraction.run(ctx["invoice"], ctx["context"]),
	"duplicate": lambda ctx: duplicate.run(ctx["invoice"], ctx["context"]),
	"fraud": lambda ctx: fraud.run(ctx["invoice"], ctx["context"]),
	"einvoice": lambda ctx: einvoice.run(ctx["invoice"]),
	"gst": lambda ctx: gst.run(ctx["invoice"], ctx["context"]),
	"itc": lambda ctx: itc.run(ctx["invoice"], ctx["context"]),
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


def validate(p, blocks=None, context=None):
	"""Run `blocks` in order against the payload. Returns the full response body.

	`blocks` defaults to every block. Unknown names raise ValueError.
	`context` is the caller-supplied comparison data; omitting it is legal and yields a
	response of Skipped rows with `auto_create_allowed: false`.
	"""
	names = list(blocks or DEFAULT_SEQUENCE)
	unknown = [n for n in names if n not in BLOCKS]
	if unknown:
		raise ValueError(f"Unknown validation block(s): {unknown}. Known: {sorted(BLOCKS)}")

	ctx, rows = {"invoice": p, "context": context or {}}, []
	for name in names:
		rows += BLOCKS[name](ctx)
		if ctx.get("stop"):
			break

	# A subset of the sequence cannot authorise creation: the blocks left out emit no rows
	# at all, so `unrun` alone would not notice them missing.
	partial = set(names) != set(DEFAULT_SEQUENCE) or bool(ctx.get("stop"))
	return {**decision.gate(rows, ctx.get("mode"), partial=partial), "checks": rows}
