"""grill_gate — the post-grill stage-(ii) enforcement (docs/briefing-lifecycle-audit.md).

The briefing is Memento's tattoo (ADR-0009): the amnesiac beat orients only from it. The audit's
stage-(ii) acceptance FAILS if, **after a grill**, Objective, Direction, or Direcionamento is still
empty — those feeders (`set_objective` / direction set-or-propose / `report_direction`) must have run.
Empty-on-fresh is correct; **empty-post-grill is the bug** (issue #26's done-criterion). The grill
skill sets the objective 'only when sharpened' and proposes Direction additively, so without a gate a
grill could complete leaving them empty. This is that gate: a grill is not 'done' until the three
have landed on the Tier-0 log (ADR-0006).

Reads only the log via eventlog's folds — no graph, no driver: the same durable truth the grill
already persists to, so the gate holds even offline-from-graph.
"""
import sys

import eventlog

# The three stage-(ii) REQUIRED briefing sections and the feeder that fills each (the audit table).
PIECES = ("objective", "direction", "direcionamento")


def grill_complete(log=eventlog.LOG):
    """Return the list of stage-(ii) pieces still missing after a grill (empty list = complete).

    A piece is present when its feeder landed an event with a **stripped-non-empty body** (Codex gate
    finding [high]): an empty/whitespace body is no stage-(ii) content, so it does NOT count as landed
    even if a grill appended such an event directly (the write helpers also refuse it at the source):
    - **objective** — `eventlog.objective_at()` body is non-empty (a `set_objective` ran);
    - **direction** — `eventlog.direction_at()` has a `set` OR `proposed` item with a non-empty body;
    - **direcionamento** — `eventlog.report_at()` latest report has a non-empty body.
    """
    def _filled(s):
        return bool(s and s.strip())

    missing = []
    if not _filled((eventlog.objective_at(log=log) or {}).get("body")):
        missing.append("objective")
    d = eventlog.direction_at(log=log) or {"set": [], "proposed": []}
    if not any(_filled(i.get("body")) for i in d.get("set", []) + d.get("proposed", [])):
        missing.append("direction")
    if not _filled(((eventlog.report_at(log=log) or {}).get("latest") or {}).get("body")):
        missing.append("direcionamento")
    return missing


def assert_grill_complete(log=eventlog.LOG):
    """Raise ValueError naming the gaps if any stage-(ii) piece is missing; pass silently otherwise.

    The grill MUST call this at its close: empty-post-grill is a stage-(ii) failure, not acceptable.
    """
    missing = grill_complete(log=log)
    if missing:
        raise ValueError(
            "grill incomplete — stage-(ii) briefing section(s) left empty: "
            f"{', '.join(missing)} (briefing-lifecycle-audit.md). A grill is not done until "
            "objective + direction + direcionamento have landed on the log."
        )


def main(argv=None):
    """CLI close: `grill_gate.py close [--log PATH]` — the DETERMINISTIC, runnable grill-close.

    Exits NONZERO naming the gaps if any stage-(ii) feeder didn't land; exits 0 when complete.
    Fail-closed at runtime regardless of agent prose-compliance — this is the step that decides
    'done', not the SKILL prose telling the agent to call a function.
    """
    import argparse

    ap = argparse.ArgumentParser(prog="grill_gate", description="post-grill stage-(ii) close gate")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("close", help="assert the three stage-(ii) feeders landed; exit nonzero on gaps")
    c.add_argument("--log", default=str(eventlog.LOG), help="event log to fold (default: the install log)")
    args = ap.parse_args(argv)

    try:
        assert_grill_complete(log=args.log)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    print("grill complete — objective + direction + direcionamento landed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
