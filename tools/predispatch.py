"""predispatch — the mechanical entry-driver of every dispatch (ADR-0016). Genotype tool.

The wake stops being a prose-only contract: this driver performs the mechanical pre-dispatch
floor — digestion sweep to currency (fail-loud store, ADR-0015) → compose the briefing → render
the recall brief — and stamps `dispatch.open` in the Tier-0 log. The publisher refuses to publish
without a stamp newer than the last `artefato.published`: **no wake, no publish**. The skill
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
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog   # noqa: E402


def run(sweep_fn=None, briefing_fn=None, recall_fn=None, log=eventlog.LOG):
    """The mechanical floor, in order: sweep → briefing → recall brief → stamp. Returns
    (briefing_text, recall_text) for the dispatch to read. Injectable (house style) so it runs
    offline in tests; real runs use the genotype tools."""
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
    eventlog.dispatch_open({"swept_sessions": swept}, log=log)
    return briefing_text, recall_text


def main():
    briefing_text, recall_text = run()
    print(briefing_text)
    print("\n\n---\n")
    print(recall_text)


if __name__ == "__main__":
    main()
