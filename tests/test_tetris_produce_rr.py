"""Tetris produce RR — Ato-1 form pick, dente accepts beat.produce, C3 kernel write."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import _beat  # noqa: E402
import eventlog  # noqa: E402
import publisher  # noqa: E402

FORMS = ("report", "research", "discovery", "lazer", "map", "plan", "prototype")
CMD = ["claude", "-p", "-"]


class RoundRobinPersistsPerDispatch(unittest.TestCase):
    def test_roster_is_exactly_the_seven(self):
        self.assertEqual(_beat.PRODUCE_FORMS, FORMS)
        self.assertNotIn("critique", _beat.PRODUCE_FORMS)
        self.assertNotIn("experiment", _beat.PRODUCE_FORMS)

    def test_successive_dispatches_advance_and_same_beat_does_not_reroll(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            first = _beat.pick_produce("d1", tema="friction-a", intent="why-a", log=log)
            again = _beat.pick_produce("d1", tema="other", intent="nope", log=log)
            self.assertEqual(first["forma"], "report")
            self.assertEqual(again["forma"], "report")
            self.assertEqual(again["tema"], "friction-a")  # first write wins
            second = _beat.pick_produce("d2", tema="friction-b", intent="why-b", log=log)
            self.assertEqual(second["forma"], "research")
            seen = [_beat.pick_produce(f"d{i}", log=log)["forma"] for i in range(3, 10)]
            self.assertEqual(seen, ["discovery", "lazer", "map", "plan", "prototype",
                                    "report", "research"])

    def test_dispatch_plan_uses_rr_pick_not_sortear_message_as_trunk(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            pre = _beat.dispatch_plan("lead", "d1", runtime_command=CMD, log=log,
                                      require_pauta=False)
            self.assertIsNone(pre["decision"]["producer"])
            self.assertIn("pick-produce", pre["decision"]["pauta"])
            self.assertIn("not the trunk", pre["decision"]["pauta"])
            _beat.pick_produce("d1", tema="faro-x", intent="cut", log=log)
            plan = _beat.dispatch_plan("lead", "d1", runtime_command=CMD, log=log)
            self.assertEqual(plan["decision"]["producer"], "report")
            self.assertEqual(plan["decision"]["ato1"], "round-robin")
            self.assertEqual(plan["decision"]["tema"], "faro-x")
            bound = _beat.bind_dispatch_plan("go", plan)
            self.assertIn("AUTHORITATIVE DISPATCH PLAN", bound)
            self.assertNotIn("tools/pauta.py sortear", bound.split("END AUTHORITATIVE")[0])


class DenteAcceptsProducePick(unittest.TestCase):
    def test_assert_accepts_produce_and_rejects_bare_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.dispatch_open({"dispatch_id": "d1", "origin": "beat"}, log=log)
            before = 0
            gaps = _beat.assert_beat_produced(log, before, dispatch_id="d1")
            self.assertTrue(any("no new Artefato" in g for g in gaps))
            _beat.pick_produce("d1", tema="t", intent="why this cut", log=log)
            eventlog.publish_artefato_atomic(
                "report--cut", "why this cut", skill="report",
                dispatch_id="d1", log=log, _rite_authorized=True)
            gaps = _beat.assert_beat_produced(log, before, dispatch_id="d1")
            self.assertEqual(gaps, [])

    def test_wrong_skill_is_a_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.dispatch_open({"dispatch_id": "d1", "origin": "beat"}, log=log)
            _beat.pick_produce("d1", tema="t", intent="why", log=log)  # report
            eventlog.publish_artefato_atomic(
                "lazer--nope", "why", skill="lazer",
                dispatch_id="d1", log=log, _rite_authorized=True)
            gaps = _beat.assert_beat_produced(log, 0, dispatch_id="d1")
            self.assertTrue(any("report" in g and "lazer--nope" in g for g in gaps))


class PublishTetrisWritesKernel(unittest.TestCase):
    def test_publish_tetris_pairs_published_and_kernel(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            blog = Path(tmp) / "entries"
            html = Path(tmp) / "page.html"
            html.write_text("<!doctype html><title>t</title><p>ok</p>", encoding="utf-8")
            eventlog.dispatch_open({"dispatch_id": "d-t", "origin": "beat"}, log=log)
            _beat.pick_produce("d-t", tema="friction", intent="kernel-why", log=log)
            receipt = publisher.publish_tetris(
                "report--friction", html, intent="kernel-why", skill="report",
                dispatch_id="d-t", log=log, blog_dir=blog, project_fn=None)
            self.assertTrue((blog / "report--friction.html").is_file())
            published = eventlog.read(types=["artefato.published"], log=log)
            kernels = eventlog.read(types=["intent.kernel"], log=log)
            self.assertEqual(len(published), 1)
            self.assertEqual(len(kernels), 1)
            self.assertEqual(published[0]["payload"]["skill"], "report")
            self.assertEqual(published[0]["payload"]["spec"]["format"], "edge-tetris/v1")
            self.assertEqual(kernels[0]["payload"]["intent"], "kernel-why")
            self.assertEqual(receipt["kernel_seq"], kernels[0]["seq"])
            self.assertEqual(eventlog.artefatos_without_kernel(log=log), [])

    def test_publish_tetris_refuses_empty_intent(self):
        with tempfile.TemporaryDirectory() as tmp:
            html = Path(tmp) / "page.html"
            html.write_text("<html></html>", encoding="utf-8")
            with self.assertRaises(ValueError):
                publisher.publish_tetris(
                    "report--x", html, intent="  ", skill="report",
                    dispatch_id="d", log=Path(tmp) / "log.jsonl",
                    blog_dir=Path(tmp) / "e", project_fn=None)


class BeatSkillNamesTheThreeActs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (REPO / "skills" / "beat" / "SKILL.md").read_text(encoding="utf-8")
        cls.low = cls.text.lower()

    def test_seven_forms_and_no_critique_rotation(self):
        for form in FORMS:
            self.assertIn(form, self.low)
        self.assertIn("pick-produce", self.low)
        self.assertIn("review-gate", self.low)
        self.assertIn("publish_tetris", self.low)
        self.assertIn("intent.kernel", self.low)
        self.assertIn("not the trunk", self.low)
        self.assertIn("no `/ed-critique`", self.low)

    def test_authoritative_plan_mentions_rr_not_only_sortear(self):
        text = (REPO / "tools" / "_beat.py").read_text(encoding="utf-8")
        self.assertIn("AUTHORITATIVE DISPATCH PLAN", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
