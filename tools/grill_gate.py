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
import eventlog

# The three stage-(ii) REQUIRED briefing sections and the feeder that fills each (the audit table).
PIECES = ("objective", "direction", "direcionamento")


def grill_complete(log=eventlog.LOG):
    """Return the list of stage-(ii) pieces still missing after a grill (empty list = complete).

    A piece is present when its feeder landed a non-empty event on the log:
    - **objective** — `eventlog.objective_at()` is non-empty (a `set_objective` ran);
    - **direction** — `eventlog.direction_at()` has a `set` OR `proposed` item (set-or-propose);
    - **direcionamento** — `eventlog.report_at()` has a latest report (a `report_direction` ran).
    """
    missing = []
    if not (eventlog.objective_at(log=log) or {}).get("body"):
        missing.append("objective")
    d = eventlog.direction_at(log=log) or {"set": [], "proposed": []}
    if not (d.get("set") or d.get("proposed")):
        missing.append("direction")
    if not (eventlog.report_at(log=log) or {}).get("latest"):
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
