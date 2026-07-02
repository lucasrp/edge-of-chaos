"""predispatch — the mechanical entry-driver of every dispatch (ADR-0016). Genotype tool.

The wake stops being a prose-only contract: this driver performs the mechanical pre-dispatch
floor — digestion sweep to currency (fail-loud store, ADR-0015) → compose the briefing → render
the recall brief — and stamps `dispatch.open` in the Tier-0 log. The publisher refuses to publish
without a `dispatch.open` that MINTED the artefato's `dispatch_id` and is not yet consumed (identity-held gate, E1): **no wake, no publish**. The skill
prose *describes* the wake; this driver *performs* it.

Delta is NOT here (ADR-0001/0011): the world-read is agentic judgment, fanned by the skill when
it judges it needs the world — it never gates and is never stamped.

Degrade contract: a RAISING sweep aborts before the stamp (a dispatch that could not wake must
not look woken — e.g. the transcript store is missing, ADR-0015). A degraded *brief* still
stamps — the gate proves the wake ran, not that the world cooperated (a graph outage darkens the
recall brief honestly; `compose_recall_brief` itself never raises, the wrap here is defense in
depth). A raising briefing compose aborts too: `BriefingIdentityError` is a lobotomized install
(ADR-0009 fail-closed), not an outage. A crash anywhere in the sweep→stamp gap is safe by the
same shape: the sweep's effects are durable and idempotent, no stamp means the publisher refuses,
and re-running this driver recovers.
"""
import argparse
import contextlib
import io
import os
import secrets
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog   # noqa: E402


def mint_dispatch_id():
    """Mint the dispatch's IDENTITY (S2, E1): a lexicographically-sortable unique id — a
    zero-padded ms timestamp prefix + 64 random bits. The repo has no ULID helper and the house
    rules forbid a new dep, so this is the ULID-equivalent: the timestamp prefix keeps ids
    monotonic across dispatches (sortable like a seq), the random suffix makes concurrent mints
    collision-free. Minted ONCE per dispatch at entry and CARRIED explicitly through
    close/publish — never reconstructed from "the last dispatch.open before the publish" (E1)."""
    return f"{int(time.time() * 1000):013d}-{secrets.token_hex(8)}"


def run(sweep_fn=None, briefing_fn=None, recall_fn=None, log=eventlog.LOG,
        dispatch_id=None, theme=None, intent=None, geometry=None):
    """The mechanical floor, in order: sweep → briefing → recall brief → stamp. Returns
    (briefing_text, recall_text) for the dispatch to read. Injectable (house style) so it runs
    offline in tests; real runs use the genotype tools.

    S2 (E1) — the stamp now carries the dispatch's IDENTITY + SESSION ANCHOR: `dispatch_id`
    (minted here when not handed in; main() mints and prints it machine-readable, because the
    live path is CLI → skill-snippet across processes and an in-process return does not cross),
    `session_id` (CLAUDE_CODE_SESSION_ID when present, else null — never fabricated), and the
    optional DECLARED fields theme/intent/geometry (attribution tier `declared`). The MONOTONIC
    anchor is the dispatch.open event's own `seq` (stamped by append) — S4's harvest maps rows
    by (session anchor, dispatch interval), so no extra cursor is persisted here. Geometry:
    predispatch cannot see its caller (separate process), so it is declared — default `ambient`
    (the heartbeat entry), flipped to `themed` when a theme is declared; an explicit geometry
    always wins."""
    if sweep_fn is None:
        import sweep as _sweep
        sweep_fn = _sweep.run
    if briefing_fn is None:
        import briefing as _briefing
        briefing_fn = _briefing.compose_briefing
    if recall_fn is None:
        import recall as _recall
        recall_fn = _recall.compose_recall_brief
    swept = sweep_fn()                      # raises on a missing store (ADR-0015) — no stamp
    briefing_text = briefing_fn()           # raises on a lobotomized identity — no stamp
    try:
        recall_text = recall_fn()
    except Exception as e:  # noqa: BLE001 — a dark brief is honest; the wake still ran
        recall_text = (f"# Recall — the memory-salient brief\n\n_Recall leg DARK "
                       f"({type(e).__name__}: {e}) — orient from the briefing; recall on demand "
                       f"(`skills/_shared/memory.md`) when the graph is reachable._\n")
    if dispatch_id is None:
        dispatch_id = mint_dispatch_id()
    if geometry is None:
        geometry = "themed" if theme else "ambient"
    eventlog.dispatch_open({"swept_sessions": swept, "dispatch_id": dispatch_id,
                            "session_id": os.environ.get("CLAUDE_CODE_SESSION_ID"),
                            "theme": theme, "intent": intent, "geometry": geometry}, log=log)
    return briefing_text, recall_text


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="predispatch — the mechanical entry-driver (ADR-0016); mints the "
                    "dispatch_id and prints it machine-readable (S2, E1)")
    parser.add_argument("--theme", default=None,
                        help="declared theme of this dispatch (tier declared; flips the "
                             "default geometry to themed)")
    parser.add_argument("--intent", default=None,
                        help="declared intent of this dispatch (tier declared)")
    parser.add_argument("--geometry", default=None, choices=("ambient", "themed"),
                        help="explicit geometry (default: ambient, themed when --theme is "
                             "declared — predispatch cannot see its caller, so it is declared)")
    args = parser.parse_args(argv)
    dispatch_id = mint_dispatch_id()
    # machine-readable FIRST (S2, E1 + gate D2): the skill-snippet reads this exact line off
    # the wake's stdout — but the real floor (sweep/recall degrades) PRINTS warnings of its
    # own, so run()'s stdout is CAPTURED and flushed AFTER the DISPATCH_ID line. The noise is
    # preserved (never swallowed), just ordered. A floor that RAISES before the stamp prints
    # NO DISPATCH_ID (a dispatch that could not wake must not look woken) — the captured
    # output still surfaces for diagnosis before the raise propagates.
    floor_out = io.StringIO()
    try:
        with contextlib.redirect_stdout(floor_out):
            briefing_text, recall_text = run(dispatch_id=dispatch_id, theme=args.theme,
                                             intent=args.intent, geometry=args.geometry)
    except BaseException:
        sys.stdout.write(floor_out.getvalue())
        raise
    print(f"DISPATCH_ID={dispatch_id}")
    sys.stdout.write(floor_out.getvalue())
    print(briefing_text)
    print("\n\n---\n")
    print(recall_text)


if __name__ == "__main__":
    main()
