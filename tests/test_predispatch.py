"""ADR-0016 — no wake, no publish. The entry-driver (tools/predispatch.py) runs the mechanical
pre-dispatch floor (sweep → briefing → recall brief) and stamps `dispatch.open`; the publisher —
the one mechanical wall every real publish crosses (the close's publish stage) — refuses without
a stamp newer than the last `artefato.published`. One wake per publish. Delta stays agentic and
is never stamped nor gated (ADR-0001/0011)."""

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import eventlog    # noqa: E402
import publisher   # noqa: E402
import predispatch  # noqa: E402


class WakeFreshness(unittest.TestCase):
    """The fold: a dispatch.open newer than the last artefato.published = a fresh wake."""

    def test_no_stamp_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            self.assertFalse(eventlog.wake_fresh(log=log))

    def test_stamp_on_empty_log_is_fresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.dispatch_open(log=log)
            self.assertTrue(eventlog.wake_fresh(log=log))

    def test_stamp_is_consumed_by_a_publish_one_wake_per_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.dispatch_open(log=log)
            eventlog._append_orphan_published_for_test("a-slug", log=log)
            self.assertFalse(eventlog.wake_fresh(log=log),
                             "a stamp must not be reusable across publishes (ADR-0016)")
            eventlog.dispatch_open(log=log)
            self.assertTrue(eventlog.wake_fresh(log=log))


class NoWakeNoPublish(unittest.TestCase):
    """The publisher refuses without a fresh stamp — BEFORE proof verification, so the refusal
    names the real gap (`no-wake`), not a proof error."""

    def test_publish_without_stamp_raises_no_wake(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with self.assertRaises(RuntimeError) as ctx:
                publisher.publish("any-slug", "<h1>x</h1>", "intent", skill="report",
                                  verdict={"not": "a proof"}, log=log,
                                  blog_dir=Path(tmp) / "blog")
            self.assertIn("no-wake", str(ctx.exception))

    def test_fresh_stamp_releases_the_gate_to_the_proof_check(self):
        # with a stamp, the same call proceeds past the wake gate and fails on the fake proof
        # instead (ValueError from verify_proof) — proving gate order and release
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.dispatch_open(log=log)
            with self.assertRaises(ValueError):
                publisher.publish("any-slug", "<h1>x</h1>", "intent", skill="report",
                                  verdict={"not": "a proof"}, log=log,
                                  blog_dir=Path(tmp) / "blog")


class EntryDriver(unittest.TestCase):
    """predispatch.run — the mechanical floor, injectable (house style) so it runs offline."""

    def test_runs_the_floor_and_stamps_with_the_sweep_yield(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            briefing_text, recall_text = predispatch.run(
                sweep_fn=lambda: 7,
                briefing_fn=lambda: "BRIEFING",
                recall_fn=lambda: "RECALL",
                harvest_fn=lambda: 0,
                log=log)
            self.assertEqual((briefing_text, recall_text), ("BRIEFING", "RECALL"))
            evs = eventlog.read(types=["dispatch.open"], log=log)
            self.assertEqual(len(evs), 1)
            self.assertEqual(evs[0]["payload"].get("swept_sessions"), 7,
                             "the stamp carries the sweep yield (the read-side metric)")

    def test_stamp_lands_even_when_a_brief_degrades(self):
        # the gate proves the wake RAN, not that the world cooperated (ADR-0016): a degraded
        # brief (e.g. graph outage) still stamps — only a raising SWEEP (fail-loud store,
        # ADR-0015) aborts before the stamp
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"

            def dark_recall():
                raise RuntimeError("graph down")

            briefing_text, recall_text = predispatch.run(
                sweep_fn=lambda: 0, briefing_fn=lambda: "B", recall_fn=dark_recall,
                harvest_fn=lambda: 0, log=log)
            self.assertIn("DARK", recall_text)
            self.assertTrue(eventlog.wake_fresh(log=log))

    def test_a_failing_sweep_aborts_before_the_stamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"

            def loud_sweep():
                raise RuntimeError("transcript store not found")

            with self.assertRaises(RuntimeError):
                predispatch.run(sweep_fn=loud_sweep, briefing_fn=lambda: "B",
                                recall_fn=lambda: "R", harvest_fn=lambda: 0, log=log)
            self.assertFalse(eventlog.wake_fresh(log=log),
                             "a dispatch that could not wake must not look woken")


class HotCutoffLeg(unittest.TestCase):
    """A perna quente do briefing default: o window_start do quente (select_window) vira o
    hot_cutoff do compose_briefing (tempo-divide-donos). DEGRADE-DARK: qualquer falha no scan →
    None (clusters expandem; a perna quente nunca derruba nem atrasa o wake)."""

    def test_window_start_becomes_the_cutoff(self):
        self.assertEqual(
            predispatch._hot_cutoff(window_fn=lambda: ([{"id": "s"}], "2026-07-05T00:00:00Z")),
            "2026-07-05T00:00:00Z")

    def test_degrades_dark_to_none_on_a_failing_scan(self):
        def boom():
            raise RuntimeError("store gone")
        self.assertIsNone(predispatch._hot_cutoff(window_fn=boom))

    def test_empty_window_is_none_never_empty_string(self):
        # janela vazia (nenhuma sessão substancial) = sem quente → tudo expande; '' truthy-falso
        # no _section_clusters seria acidente, não contrato
        self.assertIsNone(predispatch._hot_cutoff(window_fn=lambda: ([], "")))

    def test_default_briefing_fn_threads_the_cutoff_into_compose(self):
        """A fiação real: run() sem briefing_fn injeta hot_cutoff=window_start no
        compose_briefing (stubs de módulo — o caminho default atravessado de ponta a ponta)."""
        import types
        seen = {}
        stub_briefing = types.ModuleType("briefing")

        def _compose(hot_cutoff=None):
            seen["hot_cutoff"] = hot_cutoff
            return "BRIEFING"
        stub_briefing.compose_briefing = _compose
        stub_quente = types.ModuleType("quente")
        stub_quente.select_window = lambda: ([{"id": "s"}], "2026-07-01T00:00:00Z")
        saved = {n: sys.modules.get(n) for n in ("briefing", "quente")}
        sys.modules["briefing"], sys.modules["quente"] = stub_briefing, stub_quente
        try:
            with tempfile.TemporaryDirectory() as tmp:
                log = Path(tmp) / "log.jsonl"
                text, _ = predispatch.run(sweep_fn=lambda: 0, recall_fn=lambda: "R",
                                          harvest_fn=lambda: 0, probe_fn=lambda spec: None,
                                          log=log)
        finally:
            for n, m in saved.items():
                if m is None:
                    sys.modules.pop(n, None)
                else:
                    sys.modules[n] = m
        self.assertEqual(seen.get("hot_cutoff"), "2026-07-01T00:00:00Z")
        self.assertIn("BRIEFING", text)


class WakeFreshnessRealPaths(unittest.TestCase):
    """Opus review — the consume semantic through the REAL atomic publish, and the
    two-stamps case (one wake per publish: extra stamps are spent by the next publish)."""

    def test_atomic_publish_consumes_the_stamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.dispatch_open(log=log)
            eventlog.publish_artefato_atomic("a-slug", "the why", log=log)
            self.assertFalse(eventlog.wake_fresh(log=log))
            eventlog.dispatch_open(log=log)
            self.assertTrue(eventlog.wake_fresh(log=log))

    def test_two_stamps_then_one_publish_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.dispatch_open(log=log)
            eventlog.dispatch_open(log=log)
            eventlog.publish_artefato_atomic("a-slug", "the why", log=log)
            self.assertFalse(eventlog.wake_fresh(log=log),
                             "a publish spends ALL prior stamps (global max), not just one")


class WakeGateIsAuthoritativeUnderTheLock(unittest.TestCase):
    """Codex gate (BLOCKING) — the early wake_fresh check in publisher.publish is a fast-fail
    TOCTOU: two concurrent publishers could both observe one stamp as fresh and BOTH publish.
    The authoritative check lives INSIDE publish_artefato_atomic's locked critical section:
    one stamp admits exactly one publish, no matter how many callers passed the early check."""

    def test_atomic_publish_with_require_wake_refuses_without_a_stamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with self.assertRaises(RuntimeError) as ctx:
                eventlog.publish_artefato_atomic("a", "why", log=log, require_wake=True)
            self.assertIn("no-wake", str(ctx.exception))
            self.assertEqual(eventlog.read(log=log), [], "a refused publish must write NOTHING")

    def test_one_stamp_admits_exactly_one_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.dispatch_open(log=log)
            eventlog.publish_artefato_atomic("first", "why", log=log, require_wake=True)
            with self.assertRaises(RuntimeError) as ctx:
                eventlog.publish_artefato_atomic("second", "why", log=log, require_wake=True)
            self.assertIn("no-wake", str(ctx.exception))
            slugs = [e["payload"]["slug"] for e in
                     eventlog.read(types=["artefato.published"], log=log)]
            self.assertEqual(slugs, ["first"],
                             "the second publish must lose even though a caller-side check "
                             "could have raced past (the lock-held check is authoritative)")


class EntryDriverRealWiring(unittest.TestCase):
    """Opus review — the lazy-import production wiring and the REAL degrade paths,
    not only the injected stand-ins."""

    def test_lazy_default_wiring_resolves_the_real_modules(self):
        from unittest import mock
        import sweep as _sweep
        import briefing as _briefing
        import recall as _recall
        import harvest as _harvest
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with mock.patch.object(_sweep, "run", return_value=3), \
                 mock.patch.object(_briefing, "compose_briefing", return_value="B"), \
                 mock.patch.object(_recall, "compose_recall_brief", return_value="R"), \
                 mock.patch.object(_harvest, "harvest", return_value=5):
                b, r = predispatch.run(log=log)
            self.assertEqual((b, r), ("B", "R"))
            evs = eventlog.read(types=["dispatch.open"], log=log)
            self.assertEqual(evs[0]["payload"].get("swept_sessions"), 3)
            # #62: harvested moved off the identity stamp to its own dispatch.grounding event
            g = eventlog.read(types=["dispatch.grounding"], log=log)
            self.assertEqual(g[0]["payload"].get("harvested"), 5,
                             "the harvest leg lazily resolves the real harvest.harvest default")

    def test_real_recall_dark_marker_flows_through(self):
        import recall as _recall
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _, r = predispatch.run(sweep_fn=lambda: 0, briefing_fn=lambda: "B",
                                   recall_fn=lambda: _recall.compose_recall_brief(subgraph=None),
                                   harvest_fn=lambda: 0, log=log)
            self.assertIn("DARK", r)
            self.assertTrue(eventlog.wake_fresh(log=log))

    def test_a_raising_briefing_aborts_before_the_stamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"

            def lobotomy():
                raise RuntimeError("BriefingIdentityError: thin agent.yaml")

            with self.assertRaises(RuntimeError):
                predispatch.run(sweep_fn=lambda: 0, briefing_fn=lobotomy,
                                recall_fn=lambda: "R", harvest_fn=lambda: 0, log=log)
            self.assertFalse(eventlog.wake_fresh(log=log),
                             "a lobotomized install must not look woken")


class TheDriverIsPinnedInProse(unittest.TestCase):
    """Every producer's SKILL.md carries the entry snippet; the pipeline names the stamp."""

    def test_producers_run_the_entry_driver(self):
        for producer in ("report", "research", "map", "plan", "discovery"):
            skill = (REPO / "skills" / producer / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("predispatch.py", skill,
                          f"skills/{producer} is missing the ADR-0016 entry-driver snippet")

    def test_pipeline_names_the_stamp_and_the_gate(self):
        pipeline = (REPO / "skills" / "_shared" / "pipeline.md").read_text(encoding="utf-8")
        self.assertIn("predispatch.py", pipeline)
        self.assertIn("dispatch.open", pipeline)
        flat = " ".join(pipeline.lower().split())   # collapse wrapping
        self.assertIn("no wake, no publish", flat)


if __name__ == "__main__":
    unittest.main(verbosity=2)
