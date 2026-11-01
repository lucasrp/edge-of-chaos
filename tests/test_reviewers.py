"""The single advisory reviewer (Close architecture, S7; ADR-0013 blindfold; ADR-0025).

ADR-0025 (owner, 2026-11-01): "quero que o revisor só avise dos furos, e o edge pode ou corrigir
ou só mencionar a nota do revisor, à sua conveniencia". ONE reviewer points out furos; it never
scores, never vetoes. It stays BLIND (ADR-0013): it sees ONLY the artefato content + cites, never
the evidence, the session or the briefing. Its answer parse NEVER raises and NEVER blocks.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import close  # noqa: E402
import revisor  # noqa: E402


def _artefato_with_hidden_context():
    """An artefato carrying SECRET non-published fields (evidence/session/briefing) that a
    blind reviewer must never see, alongside its published content + cites."""
    return {
        "slug": "recall-report",
        "content": {
            "sections": [
                {"title": "What I found", "blocks": [
                    {"type": "paragraph",
                     "text": "Recall improved once the cursor became a per-session watermark."},
                ]},
            ],
        },
        "cites": [
            {"ref": "github:abc123", "kind": "atividade", "relevant": True,
             "snippet": "switched the cursor to a per-session watermark"},
        ],
        "proposes": [{"body": "name the full-read budget", "kind": "constraint"}],
        "distills": ["cluster:recall"],
        "intent": "open: budget unnamed; bet: name it next beat",
        # ── non-published fields a blind reviewer is DENIED ──
        "evidence": "SECRET_EVIDENCE_TOKEN raw exa dump the author read",
        "session": "SECRET_SESSION_TOKEN the mentee's transcript",
        "briefing": "SECRET_BRIEFING_TOKEN the wake context",
    }


def _capturing_completer(verdict_json):
    """A fake complete_fn: records the messages/prompt it was handed, returns canned JSON."""
    captured = {}

    def complete_fn(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return verdict_json

    complete_fn.captured = captured
    return complete_fn


def _seen_text(captured):
    """Flatten everything the completer was handed (positional + kw) into one string."""
    parts = []
    for a in captured.get("args", ()):
        parts.append(repr(a))
    for v in captured.get("kwargs", {}).values():
        parts.append(repr(v))
    return " ".join(parts)


class ReviewerIsBlindAndAdvisory(unittest.TestCase):
    def test_reviewer_sees_cites_content_but_never_evidence_session_or_briefing(self):
        fn = _capturing_completer('{"furos": []}')
        close.review(_artefato_with_hidden_context(), complete_fn=fn)
        seen = _seen_text(fn.captured)
        self.assertIn("switched the cursor to a per-session watermark", seen)
        self.assertIn("github:abc123", seen)
        self.assertNotIn("SECRET_EVIDENCE_TOKEN", seen)
        self.assertNotIn("SECRET_SESSION_TOKEN", seen)
        self.assertNotIn("SECRET_BRIEFING_TOKEN", seen)

    def test_prompt_carries_the_no_veto_contract(self):
        fn = _capturing_completer('{"furos": []}')
        close.review(_artefato_with_hidden_context(), complete_fn=fn)
        seen = _seen_text(fn.captured)
        self.assertIn("sem veto", seen)
        self.assertIn("fato sem fonte", seen)
        self.assertIn("o que faltou", seen)

    def test_furos_are_parsed(self):
        v = close.review(_artefato_with_hidden_context(),
                         complete_fn=_capturing_completer(
                             '```json\n{"furos": ["FURO 1: x", " ", "FURO 2: y"]}\n```'))
        self.assertEqual(v["furos"], ["FURO 1: x", "FURO 2: y"])
        self.assertNotIn("degraded", v)

    def test_any_malformed_answer_degrades_to_no_furos_never_raises(self):
        for raw in ("not json", "[]", "null", '"x"', '{"furos": "x"}', '{"pass": false}', ""):
            v = close._parse_furos(raw)
            self.assertEqual(v["furos"], [], raw)
            self.assertIn("degraded", v, raw)

    def test_canonical_identity(self):
        self.assertEqual(close.review.identity, close.REVIEWER_ID)


class SharedContract(unittest.TestCase):
    def test_furo_count_and_notes_heading_are_observations(self):
        self.assertEqual(revisor.count_furos("FURO 1: a\n- FURO 2: b\nSEM FUROS"), 2)
        self.assertEqual(revisor.count_furos("SEM FUROS"), 0)
        self.assertTrue(revisor.has_notes_section("texto\n\n## Notas do revisor\n\n- x"))
        self.assertFalse(revisor.has_notes_section("texto sem notas"))


if __name__ == "__main__":
    unittest.main()
