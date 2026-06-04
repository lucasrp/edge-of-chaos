"""Idiom — the operator's language source (language subdivision of operator_pressure).

The operator's idiom (memory/operator-idiom.md) is injected so the beat frames the work
in the operator's language. Logic stays in skills; this tests the read + inject plumbing.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import _pipeline  # noqa: E402


class RecordingClient:
    """Records the prompts it is asked to complete; returns canned text."""
    def __init__(self, text):
        self.prompts = []
        prompts = self.prompts

        class Comp:
            def create(_self, **kw):
                prompts.append(kw["messages"][0]["content"])
                return type("R", (), {"choices": [type("C", (), {
                    "message": type("M", (), {"content": text})()})()]})()
        self.chat = type("Chat", (), {"completions": Comp()})()


CANNED = "## Executive summary\nText long enough to pass the structure gate floor easily.\n\n## A\nBody."


def _home(tmp, idiom=None):
    home = Path(tmp)
    (home / "threads").mkdir(parents=True)
    (home / "threads" / "t.md").write_text(
        "---\nid: t\ntitle: Deploy flow\nstatus: active\n---\nWork on the deploy flow.\n")
    if idiom is not None:
        (home / "memory").mkdir(parents=True)
        (home / "memory" / "operator-idiom.md").write_text(idiom)
    return home


class TestIdiom(unittest.TestCase):
    def test_read_empty_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(_pipeline.read_idiom(Path(tmp)), "")

    def test_read_returns_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIn("deploy", _pipeline.read_idiom(_home(tmp, "- deploy = clone -> issue -> PR")))

    def test_idiom_injected_into_prompts(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = _home(tmp, "- deploy = clone -> issue -> PR -> merge -> close")
            client = RecordingClient(CANNED)
            res = _pipeline.run_beat(home, client, "gpt-5.4")
            self.assertTrue(res["ok"], res)
            self.assertIn("clone -> issue -> PR", "\n".join(client.prompts),
                          "operator idiom must be injected into the beat prompts")

    def test_runs_without_idiom(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = _pipeline.run_beat(_home(tmp, None), RecordingClient(CANNED), "gpt-5.4")
            self.assertTrue(res["ok"], res)


if __name__ == "__main__":
    unittest.main(verbosity=2)
