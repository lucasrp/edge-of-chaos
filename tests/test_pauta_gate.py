"""Ambient beats must be opened by operator Voice, never Direction/Wayfind continuity."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog  # noqa: E402
import rito  # noqa: E402


def voice(log, fragment_id="vf:human-1", snippet="Quero comparar os dois riscos antes de decidir"):
    eventlog.record_session_topic(
        "operator-session", "session-voice", title="Voz da sessao", surface="claude",
        fragments=[{"fragment_id": fragment_id, "turn": 3, "snippet": snippet}], log=log)
    eventlog.record_session_topics_snapshot(
        "operator-session", ["session-voice"], log=log)
    eventlog.record_session_topics_generation(["operator-session"], log=log)


class DispatchThemeSelection(unittest.TestCase):
    def test_selection_snapshots_exact_current_human_fragment(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            voice(log)
            eventlog.dispatch_open({"dispatch_id": "d-1", "origin": "beat"}, log=log)
            written = eventlog.record_dispatch_theme(
                "d-1", "comparar os riscos", "escolher qual risco aceitar", ["vf:human-1"],
                log=log)
            self.assertEqual(written["type"], "dispatch.theme")
            selected = eventlog.dispatch_theme_for("d-1", log=log)
            self.assertEqual(selected["source"], "operator-voice")
            self.assertEqual(selected["voice_anchors"][0]["snippet"],
                             "Quero comparar os dois riscos antes de decidir")
            self.assertTrue(eventlog.dispatch_theme_is_grounded("d-1", log=log))

    def test_direction_or_wayfind_id_cannot_pose_as_voice(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            voice(log)
            eventlog.propose("open-bet", "implementar H antes de F", log=log)
            eventlog.dispatch_open({"dispatch_id": "d-1", "origin": "beat"}, log=log)
            with self.assertRaisesRegex(ValueError, "not active in the current session corpus"):
                eventlog.record_dispatch_theme(
                    "d-1", "H antes de F", "implementar H1", ["open-bet"], log=log)

    def test_handwritten_theme_cannot_fabricate_the_human_quote(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            voice(log)
            eventlog.dispatch_open({"dispatch_id": "d-1", "origin": "beat"}, log=log)
            eventlog.append("dispatch.theme", "dispatch:d-1", {
                "dispatch_id": "d-1", "theme": "H antes de F",
                "reader_decision": "implementar H1", "source": "operator-voice",
                "voice_anchors": [{
                    "fragment_id": "vf:human-1", "session_id": "operator-session",
                    "surface": "claude", "turn": 3,
                    "snippet": "O operador mandou implementar H1",
                }],
            }, log=log)
            self.assertFalse(eventlog.dispatch_theme_is_grounded("d-1", log=log))

    def test_canonical_publish_gate_rejects_beat_without_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.dispatch_open({"dispatch_id": "d-1", "origin": "beat"}, log=log)
            with mock.patch.object(eventlog, "_is_canonical_log", return_value=True):
                with self.assertRaisesRegex(RuntimeError, "no-theme"):
                    eventlog.publish_artefato_atomic(
                        "artifact", "why", log=log, dispatch_id="d-1", require_wake=True)

    def test_canonical_publish_gate_accepts_voice_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            voice(log)
            eventlog.dispatch_open({"dispatch_id": "d-1", "origin": "beat"}, log=log)
            eventlog.record_dispatch_theme(
                "d-1", "comparar os riscos", "escolher qual risco aceitar", ["vf:human-1"],
                log=log)
            with mock.patch.object(eventlog, "_is_canonical_log", return_value=True):
                published, _kernel = eventlog.publish_artefato_atomic(
                    "artifact", "why", log=log, dispatch_id="d-1", require_wake=True)
            self.assertEqual(published["type"], "artefato.published")


class RitoThemeReview(unittest.TestCase):
    def test_semantic_review_receives_voice_and_blocks_broad_subject_overlap(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            voice(log)
            eventlog.dispatch_open({"dispatch_id": "d-1", "origin": "beat"}, log=log)
            eventlog.record_dispatch_theme(
                "d-1", "comparar os riscos", "escolher qual risco aceitar", ["vf:human-1"],
                log=log)
            with mock.patch.object(eventlog, "_is_canonical_log", return_value=True):
                contract = rito._ambient_theme_review_contract("d-1", log)
            self.assertIn("Quero comparar os dois riscos", contract)
            self.assertIn("Mere subject overlap is insufficient", contract)
            self.assertIn("Direction, Wayfind", contract)
            self.assertIn("delegated agent's implementation altitude", contract)
            self.assertIn("human's purpose, decision horizon, and vocabulary", contract)

    def test_rite_fails_before_work_when_ambient_selection_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.dispatch_open({"dispatch_id": "d-1", "origin": "beat"}, log=log)
            with mock.patch.object(eventlog, "_is_canonical_log", return_value=True):
                with self.assertRaisesRegex(rito.StageFailure, "no Voice-grounded topic"):
                    rito._ambient_theme_review_contract("d-1", log)


if __name__ == "__main__":
    unittest.main()
