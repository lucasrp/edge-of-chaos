"""grill_gate — the post-grill stage-(ii) enforcement (docs/briefing-lifecycle-audit.md).

The briefing is Memento's tattoo (ADR-0009): the amnesiac beat orients only from it. The audit's
stage-(ii) acceptance FAILS if, **after a grill**, Objective, Direction, or Direcionamento is still
empty — those feeders (`set_objective` / direction set-or-propose / `report_direction`) must have run.
Empty-on-fresh is correct; **empty-post-grill is the bug** (issue #26's done-criterion).

Plan 2026-07-13 (mentor posture + leveling-state): steers alone are **not** mentor-done. The
leveling-store floor also lands: a `grill.leveling` event must be at least as recent as the latest
steer feeder (honest diario "sem update de persona" counts). Without this, the phenotype optimizes
the steers gate and skips knowing the mentee.
"""
import sys

import cortex
import eventlog

# The stage-(ii) REQUIRED pieces and the feeder that fills each (the audit table).
# wayfind (operator 2026-07-28): Direction is the direção, the wayfind is the MAPA —
# complementary, and BOTH are updated by every mentor (by the close, not necessarily at
# the session's start: knowing first is good).
PIECES = ("objective", "direction", "direcionamento", "leveling", "wayfind")

# Event types that establish the three steers on the log — DELIBERATE acts only.
# direction.proposed fica de fora do relogio do leveling: proposta e fila de ratificacao
# (o sweep de topic-threads propoe sozinho, id topic-7d:*) — se contasse como steer, o
# proprio beat trancaria o install pos-grill (auto-lock turing/sandbox 2026-07-25).
_STEER_TYPES = frozenset({
    "objective.set",
    "direction.set",
    "direction.report",
})


def _filled(s):
    return bool(s and s.strip())


def _max_seq(log, types):
    best = -1
    for event in eventlog.read(log=log):
        if event.get("type") in types:
            seq = event.get("seq")
            if isinstance(seq, int) and seq > best:
                best = seq
    return best


def grill_complete(log=eventlog.LOG):
    """Return the list of stage-(ii) pieces still missing after a grill (empty list = complete).

    A piece is present when its feeder landed an event with a **stripped-non-empty body** (Codex gate
    finding [high]): an empty/whitespace body is no stage-(ii) content, so it does NOT count as landed
    even if a grill appended such an event directly (the write helpers also refuse it at the source):
    - **objective** — `cortex.objective_at()` body is non-empty (a `set_objective` ran);
    - **direction** — `cortex.direction_at()` has a `set` OR `proposed` item with a non-empty body;
    - **direcionamento** — `cortex.report_at()` latest report has a non-empty body;
    - **leveling** — a `grill.leveling` event exists with seq >= max seq among steer feeders
      (persona writeback; diario "sem update de persona" is valid).
    """
    missing = []
    if not _filled((cortex.objective_at(log=log) or {}).get("body")):
        missing.append("objective")
    d = cortex.direction_at(log=log) or {"set": [], "proposed": []}
    if not any(_filled(i.get("body")) for i in d.get("set", []) + d.get("proposed", [])):
        missing.append("direction")
    if not _filled(((cortex.report_at(log=log) or {}).get("latest") or {}).get("body")):
        missing.append("direcionamento")

    max_steer = _max_seq(log, _STEER_TYPES)
    max_level = _max_seq(log, frozenset({"grill.leveling"}))
    if max_level < 0 or (max_steer >= 0 and max_level < max_steer):
        missing.append("leveling")
    # wayfind — the MAPA, complementary to Direction and updated by EVERY mentor
    # (operator 2026-07-28): same recency clock as leveling — a map event landed and at
    # least as recent as the latest steer feeder (the map moves when the direção moves).
    # Whole map family: the portfolio bound surface lands `map.opened`; state updates
    # land `map.state` (field failure 2026-07-29: the gate blocked a close that had mapped).
    max_map = _max_seq(log, frozenset({"map.state", "map.opened"}))
    if max_map < 0 or (max_steer >= 0 and max_map < max_steer):
        missing.append("wayfind")
    return missing


def assert_grill_complete(log=eventlog.LOG):
    """Raise ValueError naming the gaps if any stage-(ii) piece is missing; pass silently otherwise.

    The grill MUST call this at its close: empty-post-grill is a stage-(ii) failure, not acceptable.
    """
    missing = grill_complete(log=log)
    if missing:
        raise ValueError(
            "grill incomplete — stage-(ii) briefing section(s) left empty: "
            f"{', '.join(missing)} (briefing-lifecycle-audit.md + mentor leveling-state 2026-07-13). "
            "A grill is not done until objective + direction + direcionamento have landed on the log, "
            "a grill.leveling writeback is at least as recent as the latest steer feeder "
            "(honest diario 'sem update de persona' counts), and the wayfind MAPA (map.state) is "
            "at least as recent as the steers — direção and mapa are complementary, both updated."
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
