import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import close  # noqa: E402
import eventlog  # noqa: E402


def _art():
    return {
        "slug": "author-risk",
        "skill": "report",
        "intent": "open: risky insight; bet: mark the risk instead of amputating it",
        "content": {"sections": [{"title": "Body", "blocks": [
            {"type": "paragraph", "text": "A terse but honest observation; therefore the next bet is clear."},
        ]}]},
        "cites": [{"ref": "paper:1", "kind": "mundo", "relevant": True,
                   "snippet": "external reference"}],
        "proposes": [{"body": "test the risk-tag path", "kind": "constraint"}],
        "distills": ["cluster:reportrite"],
    }


def _reviewer(identity, risks=None):
    def r(artefato, complete_fn=None):
        return {"pass": True, "scores": {"didactic_clarity": 4}, "rationales": {},
                "strikes": [], "risk_tags": risks or [], "overall": 4.0}
    r.identity = identity
    return r


class AuthorRiskTags(unittest.TestCase):
    def test_parser_keeps_risk_tags_non_blocking(self):
        verdict = close._parse_verdict(
            '{"pass": true, "scores": {}, "strikes": [], '
            '"risk_tags": [{"tag": "potential_overclaim", "note": "mentor-risk"}]}'
        )
        self.assertTrue(verdict["pass"])
        self.assertEqual(verdict["strikes"], [])
        self.assertEqual(verdict["risk_tags"][0]["tag"], "potential_overclaim")

    def test_run_close_publishes_with_visible_author_risk_section(self):
        published = []
        proof = close.run_close(
            _art(),
            produce_fn=_art,
            reviewers=(
                _reviewer(close.FEYNMAN_REVIEWER_ID, [
                    {"tag": "potential_overclaim",
                     "note": "the bridge is plausible but not settled across 1 2 3 checks"}
                ]),
                _reviewer(close.REGULAR_REVIEWER_ID),
            ),
            complete_fn=lambda *a, **k: "",
            publish_fn=lambda art, p: published.append((art, p)),
        )
        self.assertTrue(proof["pass"])
        self.assertEqual(proof["author_risk"][0]["tag"], "potential_overclaim")
        self.assertEqual(proof["author_risk"][0]["reviewer"], close.FEYNMAN_REVIEWER_ID)
        art, minted = published[0]
        self.assertEqual(minted["author_risk"][0]["tag"], "potential_overclaim")
        self.assertEqual(minted["author_risk"][0]["reviewer"], close.FEYNMAN_REVIEWER_ID)
        sections = art["content"].get("additional_sections") or []
        self.assertTrue(any(s.get("title") == "Riscos autorais assumidos" for s in sections))
        self.assertEqual([v for v in close.check_genus(art) if v.startswith("old-edge-rite")], [])

    def test_author_risk_persists_in_event_and_corpus_fold(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            risk = [{"tag": "potential_overclaim", "note": "author keeps the bridge explicit"}]
            eventlog.publish_artefato_atomic(
                "risk-fold", "open: x; bet: y", spec={"sections": []},
                log=log, author_risk=risk,
            )
            events = eventlog.read(log=log)
            published = [e for e in events if e["type"] == "artefato.published"][0]
            self.assertEqual(published["payload"]["author_risk"], risk)
            self.assertEqual(eventlog.corpus_at(log=log)[0]["author_risk"], risk)


if __name__ == "__main__":
    unittest.main(verbosity=2)
