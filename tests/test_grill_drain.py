"""Slice 2 — the voz.resolved lifecycle + the grill drain loop (AUDIT.md gap B, ADR-0017).

The drain directs answers back on its own — no hand-appended replies. It captures a start cursor +
the actionable set, loads a deterministic harm-ranked CAPPED batch, generates a `voz.reply` per
loaded comment via a PLUGGABLE reply-generator (stubbed here — NO real LLM call in any test), and
appends each chat's close (`voz.reply` + a terminal `voz.resolved`, or a non-terminal `voz.clarify`,
or `direction.set` + `voz.resolved{folded-to-direction}` for a standing Directive) in ONE idempotent
`append_batch` keyed by `comment_id` + `grill_run_id` under the version guard.

`open_comments()` keys on the absence of a TERMINAL `voz.resolved` (not `voz.reply`). The lifecycle
switch is shipped atomically with an idempotent legacy back-fill so historical reply-only comments
are not re-opened by the switch and never reprocessed.

Every test stubs the reply-generator. Zero real LLM calls — running the drain live would spend the
edge's OpenAI API (the chat router, gpt-5.4, on ~/edge/secrets/openai.env).
"""
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

BLOG = Path(__file__).resolve().parent.parent / "blog"
sys.path.insert(0, str(BLOG))


def _ev(seq, ts, type_, subject, payload):
    return json.dumps({"seq": seq, "ts": ts, "type": type_, "subject": subject, "payload": payload})


class _Base(unittest.TestCase):
    """A drain over a temp log seeded with two published slugs. The reply-generator is always a
    stub — a real one would spend the edge's OpenAI API."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.log = root / "log.jsonl"
        self.log.write_text("\n".join([
            _ev(1, "2026-06-10T09:00:00+00:00", "artefato.published", "artefato:alpha-post",
                {"slug": "alpha-post", "cites": [], "distills": [], "proposes": []}),
            _ev(2, "2026-06-10T09:00:01+00:00", "intent.kernel", "artefato:alpha-post",
                {"slug": "alpha-post", "intent": "open: alpha."}),
            _ev(3, "2026-06-12T15:30:00+00:00", "artefato.published", "artefato:beta-post",
                {"slug": "beta-post", "cites": [], "distills": [], "proposes": []}),
        ]) + "\n")
        os.environ["EDGE_BLOG_LOG"] = str(self.log)
        os.environ["EDGE_BLOG_ENTRIES"] = str(root)
        os.environ["EDGE_BLOG_STATIC"] = str(root)
        os.environ["EDGE_DASH_AUTH"] = "off"
        import server
        importlib.reload(server)
        self.server = server
        import grill_drain
        importlib.reload(grill_drain)
        self.drain = grill_drain

    def tearDown(self):
        os.environ.pop("EDGE_BLOG_LOG", None)
        os.environ.pop("EDGE_DASH_AUTH", None)
        self.tmp.cleanup()

    def _events(self, type_=None):
        out = []
        for line in self.log.read_text().splitlines():
            if line.strip():
                e = json.loads(line)
                if type_ is None or e.get("type") == type_:
                    out.append(e)
        return out

    def _add(self, type_, subject, payload):
        """Append directly through the canonical primitive (seeding a fixture state)."""
        import eventlog
        return eventlog.append(type_, subject, payload, log=self.log)

    def _comment(self, body, target_ref=None, **extra):
        import uuid
        cid = extra.pop("comment_id", uuid.uuid4().hex[:12])
        p = {"target_ref": target_ref, "comment_id": cid, "body": body}
        p.update(extra)
        self._add("voz.comment", f"voz:{target_ref or 'chat'}", p)
        return cid

    @staticmethod
    def _reply_stub(text="stubbed reply"):
        """A reply-generator stub: callable(comment) -> a plan dict. NO LLM. Default = a plain
        replied close. Tests override `outcome`/`direction` to drive the folding."""
        def gen(comment):
            return {"reply": f"{text}: {comment['body'][:20]}"}
        return gen


class TestOpenCommentsKeyOnResolved(_Base):
    """`open_comments()` keys on the absence of a TERMINAL `voz.resolved`, NOT on `voz.reply`
    presence (ADR-0017 / SURFACE.md). A reply alone does not close; a `voz.resolved` does."""

    def test_a_replied_comment_with_no_resolved_is_still_open(self):
        cid = self._comment("steer the framing", "alpha-post")
        self._add("voz.reply", "voz:alpha-post", {"comment_id": cid, "body": "noted"})
        opens = [c["comment_id"] for c in self.server.open_comments()]
        self.assertIn(cid, opens)  # reply is presentation only — still open

    def test_a_terminally_resolved_comment_leaves_open_comments(self):
        cid = self._comment("steer the framing", "alpha-post")
        self._add("voz.resolved", "voz:alpha-post",
                  {"comment_id": cid, "outcome": "replied", "grill_run_id": "g1"})
        opens = [c["comment_id"] for c in self.server.open_comments()]
        self.assertNotIn(cid, opens)

    def test_a_parked_clarify_chat_stays_open(self):
        cid = self._comment("ambiguous", "alpha-post")
        self._add("voz.clarify", "voz:alpha-post",
                  {"comment_id": cid, "clarify_id": "q1", "question": "which?", "grill_run_id": "g1"})
        opens = [c["comment_id"] for c in self.server.open_comments()]
        self.assertIn(cid, opens)  # parked is non-terminal — still open


if __name__ == "__main__":
    unittest.main(verbosity=2)
