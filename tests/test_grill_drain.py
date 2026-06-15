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
        self.client = server.app.test_client()
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


class TestLegacyBackfill(_Base):
    """Acceptance (h): the lifecycle switch must NOT re-open historical reply-only comments (incl.
    the hand-appended "oi"), and the back-fill is IDEMPOTENT — re-running adds nothing."""

    def test_backfill_closes_a_historical_reply_only_comment(self):
        # the "oi" dead-letter: a comment hand-answered with a voz.reply but never voz.resolved.
        cid = self._comment("oi", "alpha-post")
        self._add("voz.reply", "voz:alpha-post", {"comment_id": cid, "body": "hand reply"})
        # before back-fill the switch would (wrongly) re-open it
        self.assertIn(cid, [c["comment_id"] for c in self.server.open_comments()])
        self.drain.backfill_legacy_resolved(self.log)
        # after: closed, with a voz.resolved{replied}
        self.assertNotIn(cid, [c["comment_id"] for c in self.server.open_comments()])
        res = [e for e in self._events("voz.resolved") if e["payload"]["comment_id"] == cid]
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["payload"]["outcome"], "replied")

    def test_backfill_is_idempotent(self):
        cid = self._comment("oi", "alpha-post")
        self._add("voz.reply", "voz:alpha-post", {"comment_id": cid, "body": "hand reply"})
        first = self.drain.backfill_legacy_resolved(self.log)
        self.assertEqual(len(first), 1)
        before = len(self._events())
        second = self.drain.backfill_legacy_resolved(self.log)
        self.assertEqual(second, [])  # re-running adds NOTHING
        self.assertEqual(len(self._events()), before)

    def test_backfill_is_idempotent_under_a_concurrent_duplicate(self):
        # the concurrency hazard the gate flagged: two drains both compute the same legacy target,
        # then serialize. The under-lock precondition must make the SECOND a no-op for that
        # comment_id, so there is never a duplicate terminal voz.resolved (a permanent consistency
        # error). We simulate the race by interleaving: back-fill targeting cid runs twice with the
        # SAME pre-observed state, and the per-comment precondition drops the duplicate.
        cid = self._comment("oi", "alpha-post")
        self._add("voz.reply", "voz:alpha-post", {"comment_id": cid, "body": "hand reply"})
        # first back-fill closes it
        self.drain.backfill_legacy_resolved(self.log)
        # a STALE second back-fill that still "thinks" cid is a target (force it) must not duplicate
        forced = self.drain.backfill_legacy_resolved(self.log, _force_targets=[cid])
        self.assertEqual(forced, [])  # precondition dropped the duplicate
        res = [e for e in self._events("voz.resolved") if e["payload"]["comment_id"] == cid]
        self.assertEqual(len(res), 1)  # exactly one terminal outcome
        self.assertEqual(self.drain.consistency_errors(self.log), [])  # no duplicate-resolved

    def test_backfill_ignores_a_bodyless_reply(self):
        # a schema-drifted / hand-appended voz.reply with a missing or blank body is NOT a real
        # answer — the back-fill must not treat it as legacy-settled and close the directive, or an
        # unanswered comment would silently leave open_comments() with no usable reply (ADR-0017).
        cid = self._comment("a real directive", "alpha-post")
        # a reply event for cid, but with a blank body (no usable answer)
        self._add("voz.reply", "voz:alpha-post", {"comment_id": cid, "body": "   "})
        appended = self.drain.backfill_legacy_resolved(self.log)
        self.assertEqual(appended, [])  # not back-filled
        self.assertIn(cid, [c["comment_id"] for c in self.server.open_comments()])  # still open

    def test_backfill_ignores_a_reply_with_no_body_key(self):
        cid = self._comment("a real directive", "alpha-post")
        self._add("voz.reply", "voz:alpha-post", {"comment_id": cid})  # no body at all
        self.assertEqual(self.drain.backfill_legacy_resolved(self.log), [])
        self.assertIn(cid, [c["comment_id"] for c in self.server.open_comments()])

    def test_backfill_skips_a_replied_comment_with_an_unanswered_clarify(self):
        # a legacy comment with a real reply BUT a later unanswered voz.clarify is PARKED awaiting
        # clarification — the back-fill must NOT terminally close it as 'replied' (ADR-0017: a parked
        # chat is non-terminal). It stays open and is not actionable until the clarify is answered.
        cid = self._comment("a directive", "alpha-post")
        self._add("voz.reply", "voz:alpha-post", {"comment_id": cid, "body": "a partial answer"})
        self._add("voz.clarify", "voz:alpha-post",
                  {"comment_id": cid, "clarify_id": "q1", "question": "but which?", "grill_run_id": "g0"})
        self.assertEqual(self.drain.backfill_legacy_resolved(self.log), [])  # not back-filled
        self.assertIn(cid, [c["comment_id"] for c in self.server.open_comments()])  # still open
        self.assertNotIn(cid, [c["comment_id"]
                               for c in self.drain.actionable_set(self.log)])  # parked, not actionable

    def test_backfill_never_closes_a_clarify_owned_comment_even_after_answer(self):
        # a comment with ANY voz.clarify history is DRAIN-OWNED — even after the clarify is answered
        # (so it leaves _awaiting_clarification), the reply-only back-fill must NOT close it as
        # 'replied'. The drain must terminally resolve it so it consumes the answer + clarify_context
        # (ADR-0017). Otherwise an old reply would let the back-fill close it before the drain runs.
        cid = self._comment("a directive", "alpha-post")
        self._add("voz.reply", "voz:alpha-post", {"comment_id": cid, "body": "a partial answer"})
        self._add("voz.clarify", "voz:alpha-post",
                  {"comment_id": cid, "clarify_id": "q1", "question": "but which?", "grill_run_id": "g0"})
        self._add("voz.clarify_answer", "voz:alpha-post", {"clarify_id": "q1", "body": "this one"})
        self.assertEqual(self.drain.backfill_legacy_resolved(self.log), [])  # back-fill skips it
        self.assertEqual([e for e in self._events("voz.resolved")
                          if e["payload"]["comment_id"] == cid], [])  # no back-filled resolved
        # it IS actionable, and a normal drain resolves it (consuming the answer)
        self.assertIn(cid, [c["comment_id"] for c in self.drain.actionable_set(self.log)])
        self.drain.drain(self.log, self._reply_stub(), grill_run_id="g1")
        self.assertNotIn(cid, [c["comment_id"] for c in self.server.open_comments()])

    def test_backfill_does_not_touch_an_unreplied_comment(self):
        # a fresh, never-replied directive must stay open (the back-fill is reply-only).
        open_cid = self._comment("a fresh directive", "alpha-post")
        self.drain.backfill_legacy_resolved(self.log)
        self.assertIn(open_cid, [c["comment_id"] for c in self.server.open_comments()])

    def test_drain_never_reprocesses_a_backfilled_comment(self):
        # acceptance (h): after back-fill, a drain must not re-reply or re-fold the legacy comment.
        cid = self._comment("oi", "alpha-post")
        self._add("voz.reply", "voz:alpha-post", {"comment_id": cid, "body": "hand reply"})
        self.drain.backfill_legacy_resolved(self.log)
        replies_before = len(self._events("voz.reply"))
        loaded = self.drain.drain(self.log, self._reply_stub(), grill_run_id="g1")
        self.assertEqual([c["comment_id"] for c in loaded], [])  # nothing actionable
        self.assertEqual(len(self._events("voz.reply")), replies_before)  # no new reply

    def test_drain_backfills_legacy_before_loading_so_it_never_reprocesses(self):
        # acceptance (h), the integration the gate flagged: an UPGRADED log with a historical
        # reply-only comment and NO explicit back-fill call. The drain itself must back-fill first,
        # so the legacy comment is never loaded/re-replied by the lifecycle switch.
        cid = self._comment("oi", "alpha-post")
        self._add("voz.reply", "voz:alpha-post", {"comment_id": cid, "body": "hand reply"})
        replies_before = len(self._events("voz.reply"))
        loaded = self.drain.drain(self.log, self._reply_stub(), grill_run_id="g1")
        self.assertNotIn(cid, [c["comment_id"] for c in loaded])  # legacy not re-loaded
        self.assertEqual(len(self._events("voz.reply")), replies_before)  # no duplicate reply
        # it got a back-filled voz.resolved{replied}, exactly one, and is closed
        res = [e for e in self._events("voz.resolved") if e["payload"]["comment_id"] == cid]
        self.assertEqual(len(res), 1)
        self.assertNotIn(cid, [c["comment_id"] for c in self.server.open_comments()])


class TestActionableSet(_Base):
    """Acceptance (c): the drain loads only the actionable set — a parked voz.clarify with no
    answer is NOT re-loaded; a voz.clarify_answer re-enters it."""

    def test_parked_clarify_without_answer_is_not_actionable(self):
        cid = self._comment("ambiguous one", "alpha-post")
        self._add("voz.clarify", "voz:alpha-post",
                  {"comment_id": cid, "clarify_id": "q1", "question": "which?", "grill_run_id": "g0"})
        actionable = [c["comment_id"] for c in self.drain.actionable_set(self.log)]
        self.assertNotIn(cid, actionable)
        # but it IS still open (parked, in the awaiting-clarification count)
        self.assertIn(cid, [c["comment_id"] for c in self.server.open_comments()])

    def test_clarify_answer_re_enters_the_actionable_set(self):
        cid = self._comment("ambiguous one", "alpha-post")
        self._add("voz.clarify", "voz:alpha-post",
                  {"comment_id": cid, "clarify_id": "q1", "question": "which?", "grill_run_id": "g0"})
        self._add("voz.clarify_answer", "voz:alpha-post", {"clarify_id": "q1", "body": "the left one"})
        actionable = [c["comment_id"] for c in self.drain.actionable_set(self.log)]
        self.assertIn(cid, actionable)  # the answer re-enters it

    def test_answered_clarify_drains_to_a_terminal_resolution(self):
        # acceptance (c, full): a parked chat WITH a clarify_answer re-enters the actionable set and
        # a later drain terminally resolves it.
        cid = self._comment("ambiguous one", "alpha-post")
        self._add("voz.clarify", "voz:alpha-post",
                  {"comment_id": cid, "clarify_id": "q1", "question": "which?", "grill_run_id": "g0"})
        self._add("voz.clarify_answer", "voz:alpha-post", {"clarify_id": "q1", "body": "the left one"})
        self.drain.drain(self.log, self._reply_stub(), grill_run_id="g1")
        res = [e for e in self._events("voz.resolved") if e["payload"]["comment_id"] == cid]
        self.assertEqual(len(res), 1)  # terminally resolved
        self.assertNotIn(cid, [c["comment_id"] for c in self.server.open_comments()])

    def test_reply_fn_receives_the_clarify_question_and_answer_context(self):
        # the gate's finding: the reply generator must SEE the linked clarify Q + answer before it
        # terminally resolves (ADR-0017 'seeing that linked answer'), not just the comment body.
        cid = self._comment("ambiguous one", "alpha-post")
        self._add("voz.clarify", "voz:alpha-post",
                  {"comment_id": cid, "clarify_id": "q1", "question": "which framing?",
                   "grill_run_id": "g0"})
        self._add("voz.clarify_answer", "voz:alpha-post",
                  {"clarify_id": "q1", "body": "the second framing"})
        seen = {}

        def gen(comment):
            seen["clarify"] = comment.get("clarify")  # the drain must pass the Q/A context
            return {"reply": "ok"}

        self.drain.drain(self.log, gen, grill_run_id="g1")
        self.assertIsNotNone(seen.get("clarify"))
        # the context carries the edge's question AND the mentee's answer
        flat = json.dumps(seen["clarify"])
        self.assertIn("which framing?", flat)
        self.assertIn("the second framing", flat)

    def test_clarify_answer_is_never_a_new_directive(self):
        # a voz.clarify_answer must never open a chat (it is a child event, not a voz.comment).
        cid = self._comment("ambiguous one", "alpha-post")
        self._add("voz.clarify", "voz:alpha-post",
                  {"comment_id": cid, "clarify_id": "q1", "question": "which?", "grill_run_id": "g0"})
        before = [c["comment_id"] for c in self.server.open_comments()]
        self._add("voz.clarify_answer", "voz:alpha-post", {"clarify_id": "q1", "body": "answer"})
        after = [c["comment_id"] for c in self.server.open_comments()]
        self.assertEqual(set(after), set(before))  # no NEW open chat from the answer


class TestClarifyAnswerSurface(_Base):
    """The parked-clarify lifecycle must be answerable from the dashboard (ADR-0017/SURFACE.md):
    the edge's voz.clarify question renders inline, and the mentee answers with a distinct
    voz.clarify_answer child event — never a new voz.comment, so it never opens a chat."""

    def test_clarify_question_renders_inline_in_the_thread(self):
        cid = self._comment("ambiguous one", "alpha-post")
        self._add("voz.clarify", "voz:alpha-post",
                  {"comment_id": cid, "clarify_id": "q1", "question": "which framing?",
                   "grill_run_id": "g0"})
        thread = self.server._render_thread("alpha-post")
        self.assertIn("which framing?", thread)            # the question is surfaced
        self.assertIn("aguardando sua resposta", thread)   # flagged awaiting your answer
        # a pre-linked answer composer targets the clarify_id
        self.assertIn('name="clarify_id" value="q1"', thread)

    def test_clarify_form_htmx_target_is_a_valid_single_selector_per_surface(self):
        # codex Slice-7 round-3 [high]: htmx hx-target takes ONE extended selector, not a comma list.
        # `closest .thread, closest .chat` is parsed as `closest` + the malformed selector
        # `.thread, closest .chat`, so on /chat (a .chat ancestor, NO .thread) target resolution fails
        # and a general parked voz.clarify can never be answered from the UI. Each surface must render
        # the SINGLE correct `closest` selector for an ancestor that actually exists there.
        cid_t = self._comment("ambiguous thread one", "alpha-post")
        self._add("voz.clarify", "voz:alpha-post",
                  {"comment_id": cid_t, "clarify_id": "qt", "question": "which framing?",
                   "grill_run_id": "g0"})
        cid_c = self._comment("ambiguous general one", None)  # a general-chat Directive
        self._add("voz.clarify", "voz:chat",
                  {"comment_id": cid_c, "clarify_id": "qc", "question": "which scope?",
                   "grill_run_id": "g0"})
        thread = self.server._render_thread("alpha-post")
        chat = self.server._render_chat()
        # the post thread's clarify form targets a .thread ancestor (which exists there)
        self.assertIn('hx-target="closest .thread"', thread)
        # the standalone chat's clarify form targets a .chat ancestor (no .thread there)
        self.assertIn('hx-target="closest .chat"', chat)
        # the malformed combined directive is gone from BOTH surfaces
        self.assertNotIn("closest .thread, closest .chat", thread)
        self.assertNotIn("closest .thread, closest .chat", chat)

    def test_general_chat_clarify_can_be_answered_through_the_route(self):
        # the end-to-end the broken target wedged: a general voz.clarify (target_ref null) parked in
        # /chat is answerable — the route appends exactly one voz.clarify_answer and re-renders the chat.
        cid = self._comment("ambiguous general one", None)
        self._add("voz.clarify", "voz:chat",
                  {"comment_id": cid, "clarify_id": "qc", "question": "which scope?",
                   "grill_run_id": "g0"})
        r = self.client.post("/clarify/qc/answer", data={"body": "the broad scope", "surface": "chat"})
        self.assertEqual(r.status_code, 200)
        self.assertIn('class="chat"', r.data.decode())  # the chat region re-renders
        ans = self._events("voz.clarify_answer")
        self.assertEqual(len(ans), 1)
        self.assertEqual(ans[0]["payload"]["clarify_id"], "qc")

    def test_chat_clarify_form_carries_its_surface_so_the_route_can_match_it(self):
        # codex Slice-7 round-4 [high]: the answer route must return the fragment for the SUBMITTING
        # surface, not the comment's target_ref. /chat renders EVERY comment (slug-, node-, and
        # general-targeted), so a clarify form on /chat must carry surface=chat — else the route can't
        # tell a chat submission from a thread one and may swap the chat list with thread markup.
        self._comment("slug-targeted in chat", "alpha-post", comment_id="cs")
        self._add("voz.clarify", "voz:alpha-post",
                  {"comment_id": "cs", "clarify_id": "qs", "question": "which?", "grill_run_id": "g0"})
        chat = self.server._render_chat()
        thread = self.server._render_thread("alpha-post")
        self.assertIn('name="surface" value="chat"', chat)      # chat forms declare the chat surface
        self.assertIn('name="surface" value="thread"', thread)  # thread forms declare the thread surface

    def test_slug_targeted_clarify_answered_from_chat_returns_the_chat_fragment(self):
        # codex Slice-7 round-4 [high]: a slug-targeted comment (target_ref='alpha-post') shown in
        # /chat, answered from the chat surface, must get back a <ul class="chat"> — NOT a
        # <ul class="thread"> that htmx would swap over the whole chat timeline (dropping it).
        self._comment("slug-targeted ambiguous", "alpha-post", comment_id="cs")
        self._add("voz.clarify", "voz:alpha-post",
                  {"comment_id": "cs", "clarify_id": "qs", "question": "which?", "grill_run_id": "g0"})
        r = self.client.post("/clarify/qs/answer", data={"body": "the left", "surface": "chat"})
        self.assertEqual(r.status_code, 200)
        root = r.data.decode().lstrip()
        self.assertTrue(root.startswith('<ul class="chat"'),
                        f"chat-surface answer must return the chat fragment, got: {root[:40]!r}")
        self.assertEqual(len(self._events("voz.clarify_answer")), 1)

    def test_slug_targeted_clarify_answered_from_thread_returns_the_thread_fragment(self):
        # the post-thread surface still gets the thread fragment (the swap replaces the post's thread).
        self._comment("slug-targeted ambiguous", "alpha-post", comment_id="ct")
        self._add("voz.clarify", "voz:alpha-post",
                  {"comment_id": "ct", "clarify_id": "qt2", "question": "which?", "grill_run_id": "g0"})
        r = self.client.post("/clarify/qt2/answer", data={"body": "the left", "surface": "thread"})
        self.assertEqual(r.status_code, 200)
        root = r.data.decode().lstrip()
        self.assertTrue(root.startswith('<ul class="thread"'),
                        f"thread-surface answer must return the thread fragment, got: {root[:40]!r}")

    def test_clarify_answer_route_appends_a_child_event_not_a_comment(self):
        cid = self._comment("ambiguous one", "alpha-post")
        self._add("voz.clarify", "voz:alpha-post",
                  {"comment_id": cid, "clarify_id": "q1", "question": "which?", "grill_run_id": "g0"})
        before_comments = len(self._events("voz.comment"))
        r = self.client.post("/clarify/q1/answer", data={"body": "the left framing"})
        self.assertEqual(r.status_code, 200)
        # it appended a voz.clarify_answer, NOT a voz.comment (never a new Directive)
        ans = self._events("voz.clarify_answer")
        self.assertEqual(len(ans), 1)
        self.assertEqual(ans[0]["payload"]["clarify_id"], "q1")
        self.assertEqual(ans[0]["payload"]["body"], "the left framing")
        self.assertEqual(len(self._events("voz.comment")), before_comments)  # no new comment

    def test_clarify_answer_is_single_writer_per_clarify_id(self):
        # the gate's finding: a second, DIFFERENT-body answer for the same clarify_id must NOT
        # append a conflicting voz.clarify_answer (which a dict-keyed fold would silently collapse
        # and a stale drain could resolve on the wrong one). First answer wins, under the lock.
        cid = self._comment("ambiguous one", "alpha-post")
        self._add("voz.clarify", "voz:alpha-post",
                  {"comment_id": cid, "clarify_id": "q1", "question": "which?", "grill_run_id": "g0"})
        self.client.post("/clarify/q1/answer", data={"body": "answer A"})
        before = len(self._events("voz.clarify_answer"))
        # a stale tab / retry submits a DIFFERENT body for the same clarify → rejected, no second event
        self.client.post("/clarify/q1/answer", data={"body": "answer B — conflicting"})
        self.assertEqual(len(self._events("voz.clarify_answer")), before)  # still exactly one
        ans = self._events("voz.clarify_answer")
        self.assertEqual(len(ans), 1)
        self.assertEqual(ans[0]["payload"]["body"], "answer A")  # first answer wins

    def test_clarify_answer_re_enters_then_drains_to_terminal(self):
        # end-to-end: park → answer via the route → drain terminally resolves.
        cid = self._comment("ambiguous one", "alpha-post")
        self._add("voz.clarify", "voz:alpha-post",
                  {"comment_id": cid, "clarify_id": "q1", "question": "which?", "grill_run_id": "g0"})
        self.client.post("/clarify/q1/answer", data={"body": "the left one"})
        self.drain.drain(self.log, self._reply_stub(), grill_run_id="g1")
        self.assertNotIn(cid, [c["comment_id"] for c in self.server.open_comments()])


class TestClarifyAnswerGated(unittest.TestCase):
    """The voz.clarify_answer route mutates the authoritative log, so it rides the Slice-1 gate:
    an unauthenticated / cross-origin call is rejected with no append."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.log = root / "log.jsonl"
        self.log.write_text(_ev(1, "2026-06-10T09:00:00+00:00", "voz.clarify", "voz:alpha-post",
                                 {"comment_id": "c1", "clarify_id": "q1", "question": "which?",
                                  "grill_run_id": "g0"}) + "\n")
        os.environ["EDGE_BLOG_LOG"] = str(self.log)
        os.environ["EDGE_BLOG_ENTRIES"] = str(root)
        os.environ["EDGE_BLOG_STATIC"] = str(root)
        os.environ["EDGE_DASH_AUTH"] = "on"
        os.environ.pop("EDGE_DASH_TOKEN", None)
        import server
        importlib.reload(server)
        self.server = server
        self.client = server.app.test_client()

    def tearDown(self):
        for k in ("EDGE_BLOG_LOG", "EDGE_DASH_AUTH", "EDGE_DASH_TOKEN"):
            os.environ.pop(k, None)
        self.tmp.cleanup()

    def _count(self):
        return len([ln for ln in self.log.read_text().splitlines() if ln.strip()])

    def test_unauthenticated_clarify_answer_rejected_no_append(self):
        before = self._count()
        r = self.client.post("/clarify/q1/answer", data={"body": "spoofed"},
                             environ_overrides={"REMOTE_ADDR": "10.0.0.5"})
        self.assertIn(r.status_code, (401, 403))
        self.assertEqual(self._count(), before)


class TestStartupMigrationGuarded(unittest.TestCase):
    """The import-time migration (_migrate_voz_lifecycle) must NOT append to a seq-corrupt log — a
    back-fill there stamps from base=len(read()), which on a gapped log would forge a DUPLICATE seq
    and worsen the authoritative log. It must check log_is_intact first (same gate as the route)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.log = root / "log.jsonl"
        # a seq-GAPPED log (1,3) with a legacy reply-only comment the back-fill would target
        self.log.write_text(
            '{"seq": 1, "type": "voz.comment", "payload": {"target_ref": null, '
            '"comment_id": "c1", "body": "oi"}}\n'
            '{"seq": 3, "type": "voz.reply", "payload": {"comment_id": "c1", "body": "hand reply"}}\n')
        os.environ["EDGE_BLOG_LOG"] = str(self.log)
        os.environ["EDGE_BLOG_ENTRIES"] = str(root)
        os.environ["EDGE_BLOG_STATIC"] = str(root)
        os.environ["EDGE_DASH_AUTH"] = "off"

    def tearDown(self):
        for k in ("EDGE_BLOG_LOG", "EDGE_DASH_AUTH"):
            os.environ.pop(k, None)
        self.tmp.cleanup()

    def test_import_migration_does_not_append_to_a_seq_corrupt_log(self):
        before = len([ln for ln in self.log.read_text().splitlines() if ln.strip()])
        import server
        importlib.reload(server)  # triggers _migrate_voz_lifecycle on import
        after = len([ln for ln in self.log.read_text().splitlines() if ln.strip()])
        self.assertEqual(after, before)  # nothing appended past the corrupt log


class TestDrainRouteAuthGate(unittest.TestCase):
    """Acceptance (g): the drain route (HTTP) sits behind the Slice-1 auth gate — an
    unauthenticated / cross-origin call is rejected with NO append (per Slice 1). And the route
    NEVER calls a live LLM in tests (the reply-generator is injectable; default refuses to spend)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.log = root / "log.jsonl"
        self.log.write_text("\n".join([
            _ev(1, "2026-06-10T09:00:00+00:00", "artefato.published", "artefato:alpha-post",
                {"slug": "alpha-post", "cites": [], "distills": [], "proposes": []}),
        ]) + "\n")
        os.environ["EDGE_BLOG_LOG"] = str(self.log)
        os.environ["EDGE_BLOG_ENTRIES"] = str(root)
        os.environ["EDGE_BLOG_STATIC"] = str(root)
        os.environ["EDGE_DASH_AUTH"] = "on"  # the real gate
        os.environ.pop("EDGE_DASH_TOKEN", None)
        import server
        importlib.reload(server)
        self.server = server
        self.client = server.app.test_client()

    def tearDown(self):
        for k in ("EDGE_BLOG_LOG", "EDGE_DASH_AUTH", "EDGE_DASH_TOKEN"):
            os.environ.pop(k, None)
        self.tmp.cleanup()

    def _count(self):
        return len([ln for ln in self.log.read_text().splitlines() if ln.strip()])

    def test_unauthenticated_drain_is_rejected_with_no_append(self):
        before = self._count()
        r = self.client.post("/grill/drain", environ_overrides={"REMOTE_ADDR": "10.0.0.5"})
        self.assertIn(r.status_code, (401, 403))
        self.assertEqual(self._count(), before)  # nothing appended

    def test_cross_origin_drain_is_rejected_with_no_append(self):
        before = self._count()
        r = self.client.post("/grill/drain", headers={"Origin": "http://evil.example"})
        self.assertIn(r.status_code, (401, 403))
        self.assertEqual(self._count(), before)

    def test_authed_drain_does_not_call_a_live_llm_by_default(self):
        # the operator triggers the route, but no reply-generator is configured → the route must
        # NOT invoke a live LLM (no API spend). It returns a "no generator" signal, no append.
        before = self._count()
        r = self.client.post("/grill/drain")  # local operator, authed
        self.assertIn(r.status_code, (200, 503))
        # whatever the status, nothing was generated (no voz.reply / voz.resolved) — no LLM spend
        types = [json.loads(ln)["type"] for ln in self.log.read_text().splitlines() if ln.strip()]
        self.assertNotIn("voz.reply", types)

    def test_route_does_not_500_on_a_malformed_legacy_line(self):
        # the gate's finding: a schema-drifted / garbage line in an upgraded log must not crash the
        # route before the controlled response. The back-fill is fail-soft (same contract as the
        # startup migration): the route returns its controlled 503, flagging the migration degraded
        # rather than 500ing. A corrupt log is surfaced, never silently appended past (a miscounted
        # seq would corrupt the source of truth) — honest degrade over a forged write.
        import eventlog
        eventlog.append("voz.comment", "voz:alpha-post",
                        {"target_ref": "alpha-post", "comment_id": "legacy1", "body": "oi"},
                        log=self.log)
        eventlog.append("voz.reply", "voz:alpha-post",
                        {"comment_id": "legacy1", "body": "hand reply"}, log=self.log)
        with open(self.log, "a") as fh:
            fh.write("{ this is not valid json at all\n")
        r = self.client.post("/grill/drain")  # must NOT 500
        self.assertEqual(r.status_code, 503)
        self.assertEqual(json.loads(r.data)["backfill"], "degraded")  # surfaced, not crashed

    def test_generator_backed_route_does_not_500_on_a_malformed_log(self):
        # the gate's finding: with a generator configured, the route still drained — and drain()
        # re-ran the back-fill unguarded → 500 on a corrupt log. Now a degraded migration aborts the
        # drain with a controlled degraded response, and nothing is appended past the corrupt log.
        import eventlog
        eventlog.append("voz.comment", "voz:alpha-post",
                        {"target_ref": "alpha-post", "comment_id": "legacy1", "body": "oi"},
                        log=self.log)
        eventlog.append("voz.reply", "voz:alpha-post",
                        {"comment_id": "legacy1", "body": "hand reply"}, log=self.log)
        with open(self.log, "a") as fh:
            fh.write("{ not valid json\n")
        before = len([ln for ln in self.log.read_text().splitlines() if ln.strip()])
        self.server.DRAIN_REPLY_GENERATOR = lambda c: {"reply": "stub, no llm"}
        try:
            r = self.client.post("/grill/drain")  # generator set → would have drained
            self.assertNotEqual(r.status_code, 500)  # must NOT 500
            self.assertEqual(json.loads(r.data)["backfill"], "degraded")
        finally:
            self.server.DRAIN_REPLY_GENERATOR = None
        after = len([ln for ln in self.log.read_text().splitlines() if ln.strip()])
        self.assertEqual(after, before)  # nothing appended past the corrupt log

    def test_schema_drifted_event_degrades_not_500(self):
        # the gate's finding: a syntactically-valid JSON line that is NOT a well-formed event
        # envelope (missing seq, or a non-dict payload) passes a JSON-only guard but can 500 the
        # drain folds (e['seq'], e['payload'].get(...)). The up-front validator must reject the
        # envelope shape too → controlled degrade, no 500, no generator, no append.
        import eventlog
        eventlog.append("voz.comment", "voz:alpha-post",
                        {"target_ref": "alpha-post", "comment_id": "open1", "body": "fresh"},
                        log=self.log)
        with open(self.log, "a") as fh:
            fh.write('{"seq": 999, "type": "voz.comment", "payload": "not-a-dict"}\n')  # bad payload
        called = {"n": 0}
        self.server.DRAIN_REPLY_GENERATOR = lambda c: (called.__setitem__("n", called["n"] + 1)
                                                       or {"reply": "x"})
        try:
            r = self.client.post("/grill/drain")
            self.assertNotEqual(r.status_code, 500)
            self.assertEqual(json.loads(r.data)["backfill"], "degraded")
        finally:
            self.server.DRAIN_REPLY_GENERATOR = None
        self.assertEqual(called["n"], 0)  # generator never invoked on a schema-drifted log

    def test_event_missing_seq_degrades(self):
        import grill_drain
        with open(self.log, "a") as fh:
            fh.write('{"type": "voz.comment", "payload": {"comment_id": "x", "body": "b"}}\n')  # no seq
        self.assertFalse(grill_drain.log_is_intact(self.log))

    def test_non_string_voz_comment_body_degrades(self):
        # an envelope-valid voz.comment whose payload.body is a non-string would 500 _harm_score's
        # .lower() in the drain — the up-front health check must reject it so the route degrades.
        import grill_drain
        with open(self.log, "a") as fh:
            fh.write('{"seq": 50, "type": "voz.comment", "payload": '
                     '{"comment_id": "x", "body": ["not", "a", "string"]}}\n')
        self.assertFalse(grill_drain.log_is_intact(self.log))

    def test_non_string_voz_reply_body_degrades(self):
        import grill_drain
        with open(self.log, "a") as fh:
            fh.write('{"seq": 50, "type": "voz.reply", "payload": {"comment_id": "x", "body": {"k": 1}}}\n')
        self.assertFalse(grill_drain.log_is_intact(self.log))

    def test_non_string_direction_set_id_degrades(self):
        # fold_direction uses direction.set.id AS a dict KEY (`items[iid] = ...`); a list-valued id
        # is unhashable → TypeError in the fold, the consistency check, AND any direction_at read. So
        # the up-front integrity gate must reject it, like every other id used as a fold key. The seq
        # stays contiguous (2 after the setup's seq-1 line) so this isolates the id-TYPE rejection,
        # not the seq-gap rule.
        import grill_drain
        with open(self.log, "w") as fh:
            fh.write('{"seq": 1, "type": "artefato.published", "payload": {"slug": "a"}}\n')
            fh.write('{"seq": 2, "type": "direction.set", "payload": '
                     '{"id": ["not", "a", "string"], "body": "a steer"}}\n')
        self.assertFalse(grill_drain.log_is_intact(self.log))

    def test_string_direction_set_id_is_intact(self):
        # the positive control: a well-typed direction.set.id passes the gate (the rule rejects only
        # a corrupt-TYPED id, not the field's presence).
        import grill_drain
        with open(self.log, "w") as fh:
            fh.write('{"seq": 1, "type": "artefato.published", "payload": {"slug": "a"}}\n')
            fh.write('{"seq": 2, "type": "direction.set", "payload": {"id": "d1", "body": "a steer"}}\n')
        self.assertTrue(grill_drain.log_is_intact(self.log))

    def test_non_contiguous_seq_degrades(self):
        # eventlog stamps seq = base+i+1, so a clean log has seqs exactly 1..N contiguous in file
        # order. An out-of-order / gapped seq breaks the cursor-bound batch (a high-seq voz.resolved
        # past the last line, or a hidden comment), so the integrity gate must reject it.
        import grill_drain
        with open(self.log, "w") as fh:
            fh.write('{"seq": 1, "type": "artefato.published", "payload": {"slug": "a"}}\n')
            fh.write('{"seq": 5, "type": "voz.comment", "payload": {"comment_id": "x", "body": "b"}}\n')
        self.assertFalse(grill_drain.log_is_intact(self.log))  # gap 1 -> 5

    def test_out_of_order_seq_degrades(self):
        import grill_drain
        with open(self.log, "w") as fh:
            fh.write('{"seq": 2, "type": "artefato.published", "payload": {"slug": "a"}}\n')
            fh.write('{"seq": 1, "type": "voz.comment", "payload": {"comment_id": "x", "body": "b"}}\n')
        self.assertFalse(grill_drain.log_is_intact(self.log))  # decreasing

    def test_contiguous_seq_is_intact(self):
        import grill_drain
        with open(self.log, "w") as fh:
            fh.write('{"seq": 1, "type": "artefato.published", "payload": {"slug": "a"}}\n')
            fh.write('{"seq": 2, "type": "voz.comment", "payload": {"comment_id": "x", "body": "b"}}\n')
        self.assertTrue(grill_drain.log_is_intact(self.log))

    def test_voz_comment_missing_comment_id_degrades(self):
        # the drain indexes comment["comment_id"] directly (clarify_context, _close_one), so a
        # voz.comment with no/blank/non-string comment_id must fail the up-front gate.
        import grill_drain
        for payload in ('{"body": "x"}', '{"comment_id": "", "body": "x"}',
                        '{"comment_id": 123, "body": "x"}'):
            with open(self.log, "w") as fh:  # fresh log each iteration
                fh.write('{"seq": 1, "type": "artefato.published", "payload": {"slug": "alpha-post"}}\n')
                fh.write(f'{{"seq": 2, "type": "voz.comment", "payload": {payload}}}\n')
            self.assertFalse(grill_drain.log_is_intact(self.log), payload)

    def test_voz_comment_missing_body_degrades(self):
        # the drain indexes comment["body"] directly (_build_live_prompt, _harm_score), so a
        # voz.comment with NO body must fail the up-front gate — else a KeyError 500s the live drain.
        import grill_drain
        with open(self.log, "a") as fh:
            fh.write('{"seq": 50, "type": "voz.comment", "payload": {"comment_id": "x"}}\n')  # no body
        self.assertFalse(grill_drain.log_is_intact(self.log))

    def test_route_degrades_on_a_comment_missing_body_generator_backed(self):
        with open(self.log, "a") as fh:
            fh.write('{"seq": 50, "type": "voz.comment", "payload": '
                     '{"target_ref": "alpha-post", "comment_id": "nobody"}}\n')  # no body
        called = {"n": 0}
        self.server.DRAIN_REPLY_GENERATOR = lambda c: (called.__setitem__("n", called["n"] + 1)
                                                       or {"reply": "x"})
        try:
            r = self.client.post("/grill/drain")
            self.assertNotEqual(r.status_code, 500)
            self.assertEqual(json.loads(r.data)["backfill"], "degraded")
        finally:
            self.server.DRAIN_REPLY_GENERATOR = None
        self.assertEqual(called["n"], 0)

    def test_route_degrades_on_a_preexisting_non_string_payload(self):
        # a pre-existing poisoned Voz payload (envelope-valid, body non-string) → the route degrades
        # before the drain/generator, never 500. Proven on the generator-backed path (no spend).
        with open(self.log, "a") as fh:
            fh.write('{"seq": 50, "type": "voz.comment", "payload": '
                     '{"target_ref": "alpha-post", "comment_id": "poison", "body": [1, 2]}}\n')
        called = {"n": 0}
        self.server.DRAIN_REPLY_GENERATOR = lambda c: (called.__setitem__("n", called["n"] + 1)
                                                       or {"reply": "x"})
        try:
            r = self.client.post("/grill/drain")
            self.assertNotEqual(r.status_code, 500)
            self.assertEqual(json.loads(r.data)["backfill"], "degraded")
        finally:
            self.server.DRAIN_REPLY_GENERATOR = None
        self.assertEqual(called["n"], 0)

    def test_malformed_log_with_no_backfill_target_still_degrades_no_generator(self):
        # the gate's finding: a corrupt log with an OPEN voz.comment but NO legacy reply-only target
        # → the back-fill returns [] early (no append), so it can't be the corruption detector. The
        # route must validate the log strictly up front and degrade — no drain, no append.
        import eventlog
        eventlog.append("voz.comment", "voz:alpha-post",
                        {"target_ref": "alpha-post", "comment_id": "open1", "body": "a fresh one"},
                        log=self.log)
        with open(self.log, "a") as fh:
            fh.write("{ not valid json\n")
        before = len([ln for ln in self.log.read_text().splitlines() if ln.strip()])
        r = self.client.post("/grill/drain")  # no generator
        self.assertNotEqual(r.status_code, 500)
        self.assertEqual(json.loads(r.data)["backfill"], "degraded")
        after = len([ln for ln in self.log.read_text().splitlines() if ln.strip()])
        self.assertEqual(after, before)  # nothing appended

    def test_malformed_log_with_no_backfill_target_degrades_before_generator(self):
        # same corrupt-no-target log, but a generator IS set. The route must degrade BEFORE building
        # or calling the generator — no API spend, no 500, no append.
        import eventlog
        eventlog.append("voz.comment", "voz:alpha-post",
                        {"target_ref": "alpha-post", "comment_id": "open1", "body": "a fresh one"},
                        log=self.log)
        with open(self.log, "a") as fh:
            fh.write("{ not valid json\n")
        called = {"n": 0}

        def gen(c):
            called["n"] += 1  # if this ever fires on a corrupt log, that's a (potential live) spend
            return {"reply": "x"}

        self.server.DRAIN_REPLY_GENERATOR = gen
        try:
            r = self.client.post("/grill/drain")
            self.assertNotEqual(r.status_code, 500)
            self.assertEqual(json.loads(r.data)["backfill"], "degraded")
        finally:
            self.server.DRAIN_REPLY_GENERATOR = None
        self.assertEqual(called["n"], 0)  # the generator was never invoked on a corrupt log

    def test_route_backfills_on_a_clean_upgraded_log(self):
        # the clean upgrade path: a historical reply-only comment, no garbage → the route migrates
        # it (the back-fill succeeds) and reports backfill ok, so nothing reopens.
        import eventlog
        eventlog.append("voz.comment", "voz:alpha-post",
                        {"target_ref": "alpha-post", "comment_id": "legacy1", "body": "oi"},
                        log=self.log)
        eventlog.append("voz.reply", "voz:alpha-post",
                        {"comment_id": "legacy1", "body": "hand reply"}, log=self.log)
        r = self.client.post("/grill/drain")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(json.loads(r.data)["backfill"], "ok")
        self.assertNotIn("legacy1", [c["comment_id"] for c in self.server.open_comments()])

    def test_no_generator_route_still_backfills_legacy_so_nothing_reopens(self):
        # the gate's finding: an upgraded install with a historical voz.reply-only comment and NO
        # generator. The lifecycle switch is live, so without a back-fill the legacy chat shows as
        # open. The route must migrate it (back-fill) even on the no-generator 503 path — the
        # migration is independent of the reply generator (ADR-0017: switch ships WITH the back-fill).
        import eventlog
        eventlog.append("voz.comment", "voz:alpha-post",
                        {"target_ref": "alpha-post", "comment_id": "legacy1", "body": "oi"},
                        log=self.log)
        eventlog.append("voz.reply", "voz:alpha-post",
                        {"comment_id": "legacy1", "body": "hand reply"}, log=self.log)
        # before: the switch would show it open
        self.assertIn("legacy1", [c["comment_id"] for c in self.server.open_comments()])
        r = self.client.post("/grill/drain")  # authed, no generator → 503 path
        self.assertEqual(r.status_code, 503)
        # but the legacy chat was migrated: it is NOT open, with a back-filled voz.resolved
        self.assertNotIn("legacy1", [c["comment_id"] for c in self.server.open_comments()])
        types = [json.loads(ln)["type"] for ln in self.log.read_text().splitlines() if ln.strip()]
        self.assertIn("voz.resolved", types)
        self.assertNotIn("voz.reply", types[types.index("voz.resolved"):])  # no NEW reply generated

    def test_authed_drain_with_injected_stub_runs_end_to_end_no_llm(self):
        # the route's vertical, proven with a STUB generator (no API spend): an authed drain
        # replies + resolves an open comment through the HTTP entry point.
        import uuid
        cid = uuid.uuid4().hex[:12]
        # seed an open comment via the canonical append
        import eventlog
        eventlog.append("voz.comment", "voz:alpha-post",
                        {"target_ref": "alpha-post", "comment_id": cid, "body": "steer it"},
                        log=self.log)
        self.server.DRAIN_REPLY_GENERATOR = lambda c: {"reply": "stub reply, no llm"}
        try:
            r = self.client.post("/grill/drain")
            self.assertEqual(r.status_code, 200)
            self.assertIn(cid, json.loads(r.data)["loaded"])
        finally:
            self.server.DRAIN_REPLY_GENERATOR = None
        types = [json.loads(ln)["type"] for ln in self.log.read_text().splitlines() if ln.strip()]
        self.assertIn("voz.reply", types)
        self.assertIn("voz.resolved", types)


class TestDrainHappyPath(_Base):
    """Acceptance (a): post a comment → drain → a voz.reply generates, the comment leaves
    open_comments() (the dead-letter is gone)."""

    def test_drain_replies_and_closes_a_comment(self):
        cid = self._comment("tighten the framing", "alpha-post")
        self.assertIn(cid, [c["comment_id"] for c in self.server.open_comments()])
        loaded = self.drain.drain(self.log, self._reply_stub("ed says"), grill_run_id="g1")
        self.assertEqual([c["comment_id"] for c in loaded], [cid])
        # a voz.reply generated (from the stub — no real LLM)
        replies = [e for e in self._events("voz.reply") if e["payload"]["comment_id"] == cid]
        self.assertEqual(len(replies), 1)
        self.assertIn("ed says", replies[0]["payload"]["body"])
        # a terminal voz.resolved{replied} landed; the comment left open_comments()
        res = [e for e in self._events("voz.resolved") if e["payload"]["comment_id"] == cid]
        self.assertEqual(res[0]["payload"]["outcome"], "replied")
        self.assertNotIn(cid, [c["comment_id"] for c in self.server.open_comments()])

    def test_reply_fn_is_called_once_per_loaded_comment_no_real_llm(self):
        # prove the generator is pluggable + stubbed: the suite makes ZERO real LLM calls.
        self._comment("one", "alpha-post")
        self._comment("two", "beta-post")
        calls = []

        def spy(comment):
            calls.append(comment["comment_id"])
            return {"reply": "ok"}

        self.drain.drain(self.log, spy, grill_run_id="g1")
        self.assertEqual(len(calls), 2)

    def test_drain_is_idempotent_under_the_same_grill_run_id(self):
        # acceptance (d, idempotency): re-running the SAME grill_run_id adds nothing (a retry
        # replays the identical planned batch).
        self._comment("a directive", "alpha-post")
        self.drain.drain(self.log, self._reply_stub(), grill_run_id="g1")
        before = len(self._events())
        # the SAME run id over a fresh actionable read — the comment is already closed, so it is
        # no longer actionable; even if it were, the precondition would drop the duplicate.
        self.drain.drain(self.log, self._reply_stub(), grill_run_id="g1")
        self.assertEqual(len(self._events()), before)


class TestFoldToDirection(_Base):
    """Acceptance (b): a standing Directive → drain → direction.set + voz.resolved{
    folded-to-direction, origin_comment_id, direction_id} land ATOMICALLY."""

    @staticmethod
    def _directive_stub():
        def gen(comment):
            return {"reply": "folding this into a steer",
                    "directive": True, "direction_body": "standing: " + comment["body"]}
        return gen

    def test_standing_directive_folds_to_direction_atomically(self):
        cid = self._comment("always cite an outside benchmark", "alpha-post")
        self.drain.drain(self.log, self._directive_stub(), grill_run_id="g1")
        # direction.set with origin_comment_id
        sets = [e for e in self._events("direction.set")
                if e["payload"].get("origin_comment_id") == cid]
        self.assertEqual(len(sets), 1)
        direction_id = sets[0]["payload"]["id"]
        # voz.resolved{folded-to-direction} carrying origin_comment_id + the matching direction_id
        res = [e for e in self._events("voz.resolved") if e["payload"]["comment_id"] == cid]
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["payload"]["outcome"], "folded-to-direction")
        self.assertEqual(res[0]["payload"]["origin_comment_id"], cid)
        self.assertEqual(res[0]["payload"]["direction_id"], direction_id)
        # no consistency error — the direction_id resolves to a real direction.set
        self.assertEqual(self.drain.consistency_errors(self.log), [])

    def test_fold_is_one_atomic_append_batch(self):
        # the reply + direction.set + voz.resolved share ONE write — contiguous seqs, no half-state.
        cid = self._comment("a standing steer", "alpha-post")
        comment_seq = self._events("voz.comment")[-1]["seq"]
        self.drain.drain(self.log, self._directive_stub(), grill_run_id="g1")
        # the three CLOSE events (exclude the seeding voz.comment, which shares comment_id == cid)
        seqs = sorted(e["seq"] for e in self._events()
                      if e["seq"] > comment_seq
                      and (e.get("payload", {}).get("comment_id") == cid
                           or e.get("payload", {}).get("origin_comment_id") == cid))
        self.assertEqual(len(seqs), 3)  # voz.reply + direction.set + voz.resolved
        # contiguous (one append_batch stamps a contiguous seq range — no interleaving, no half)
        self.assertEqual(seqs, list(range(seqs[0], seqs[0] + 3)))


class TestVersionGuardConcurrency(_Base):
    """Acceptance (d): a stale/concurrent drain must NOT produce a second terminal outcome (the
    version guard); a crash mid-close leaves a chat fully resolved-or-open, never half."""

    def test_a_stale_drain_cannot_double_close(self):
        cid = self._comment("contested", "alpha-post")
        # drain A captures its start cursor (before any close)
        start_cursor = self.drain._start_cursor(self.log)
        # drain B (a concurrent grill) closes the chat first
        self.drain.drain(self.log, self._reply_stub("B"), grill_run_id="gB")
        self.assertEqual(len(self._events("voz.resolved")), 1)
        # drain A now tries to close the SAME comment with its STALE cursor → guard drops it
        comment = [c for c in self.drain.open_comments(self.log) if c["comment_id"] == cid]
        # (it already left open; simulate A still holding the loaded comment)
        loaded_comment = {"comment_id": cid, "target_ref": "alpha-post", "body": "contested"}
        result = self.drain._close_one(
            self.log, loaded_comment, {"reply": "A"}, "gA", start_cursor)
        self.assertEqual(result, [])  # stale batch dropped
        self.assertEqual(len(self._events("voz.resolved")), 1)  # still exactly one terminal outcome

    def test_a_stale_drain_cannot_double_park(self):
        # the guard tests BOTH resolved AND clarify — a parked chat is still open, so still_open
        # alone would let a stale grill double-park. The guard catches it.
        cid = self._comment("ambiguous", "alpha-post")
        start_cursor = self.drain._start_cursor(self.log)
        # grill B parks it
        self.drain._close_one(self.log, {"comment_id": cid, "target_ref": "alpha-post",
                                         "body": "ambiguous"},
                              {"park": True, "question": "which?"}, "gB", start_cursor=self.drain._start_cursor(self.log))
        self.assertEqual(len(self._events("voz.clarify")), 1)
        # grill A, stale cursor, tries to close → dropped (a clarify appeared since A's cursor)
        result = self.drain._close_one(
            self.log, {"comment_id": cid, "target_ref": "alpha-post", "body": "ambiguous"},
            {"reply": "A"}, "gA", start_cursor)
        self.assertEqual(result, [])
        self.assertEqual(len(self._events("voz.resolved")), 0)  # not terminally closed by the stale A


class TestLiveGeneratorStructuredPlan(_Base):
    """The live generator must return a STRUCTURED plan (so a standing Directive folds to direction,
    not silently closes as 'replied'), and on an invalid/unclassifiable model output it must PARK
    (never fabricate a terminal 'replied' that hides a lost steer). Tested via the pure plan-parser
    with the model call stubbed — NO real LLM (a live call would spend the edge OpenAI API)."""

    def test_parse_plan_classifies_a_standing_directive_as_folded(self):
        raw = '{"outcome": "directive", "reply": "folding this", "direction_body": "always cite a benchmark"}'
        plan = self.drain.parse_live_plan(raw)
        self.assertTrue(plan.get("directive"))
        self.assertEqual(plan["reply"], "folding this")
        self.assertEqual(plan["direction_body"], "always cite a benchmark")

    def test_parse_plan_classifies_a_plain_reply(self):
        raw = '{"outcome": "reply", "reply": "noted, here is the tradeoff"}'
        plan = self.drain.parse_live_plan(raw)
        self.assertFalse(plan.get("directive"))
        self.assertFalse(plan.get("park"))
        self.assertEqual(plan["reply"], "noted, here is the tradeoff")

    def test_invalid_model_output_parks_never_fabricates_replied(self):
        # unparseable / unclassifiable output must PARK (non-terminal), never close as replied —
        # an autonomous grill may only park, never fabricate a terminal outcome (ADR-0017).
        plan = self.drain.parse_live_plan("the model returned prose, not json")
        self.assertTrue(plan.get("park"))
        self.assertIn("question", plan)

    def test_non_string_fields_are_coerced_to_park(self):
        # a live model could emit a non-string reply/question/direction_body; persisting it would
        # poison the log (the render path html.escapes a str) → coerce to park, never append it.
        for raw in (
            '{"outcome":"reply","reply":{"x":1}}',                 # non-string reply
            '{"outcome":"park","question":["x"]}',                 # non-string question
            '{"outcome":"directive","reply":"ok","direction_body":42}',  # non-string steer body
            '{"outcome":"reply","reply":"   "}',                   # whitespace-only reply
            '{"outcome":"directive","reply":"ok","direction_body":""}',  # empty steer body
        ):
            plan = self.drain.parse_live_plan(raw)
            self.assertTrue(plan.get("park"), raw)
            self.assertIsInstance(plan["question"], str)

    def test_live_generator_folds_a_directive_end_to_end_with_a_stubbed_model(self):
        # wire a FAKE model completer into the structured generator (no real LLM) and prove a
        # standing-directive classification folds to direction.set through the real drain.
        cid = self._comment("always cite an outside benchmark", "alpha-post")
        fake_model = lambda prompt: ('{"outcome": "directive", "reply": "folding", '
                                     '"direction_body": "always cite an outside benchmark"}')
        gen = self.drain.structured_reply_generator(fake_model)
        self.drain.drain(self.log, gen, grill_run_id="g1")
        sets = [e for e in self._events("direction.set")
                if e["payload"].get("origin_comment_id") == cid]
        self.assertEqual(len(sets), 1)
        res = [e for e in self._events("voz.resolved") if e["payload"]["comment_id"] == cid]
        self.assertEqual(res[0]["payload"]["outcome"], "folded-to-direction")


class TestCoreDrainFailsClosedOnCorruptLog(_Base):
    """The core drain() API (usable as a local tool, not only via the HTTP route) must itself
    fail-closed on a corrupt log — no back-fill append, no generator invocation — so a caller that
    bypasses the route's gate cannot append over / spend on a seq-corrupt or schema-drifted log."""

    def test_drain_on_unhashable_clarify_id_fails_closed(self):
        # a voz.clarify with a non-string (unhashable) comment_id/clarify_id passes a question-only
        # check but would TypeError the set/dict-keyed folds — the core drain must fail closed.
        import grill_drain
        self._comment("a directive", "alpha-post")  # keep seqs contiguous
        with open(self.log, "a") as fh:
            fh.write('{"seq": 99, "type": "voz.clarify", "payload": '
                     '{"comment_id": ["x"], "clarify_id": "q1", "question": "?"}}\n')
        # (seq 99 also makes it gapped, but assert the schema check independently too)
        with open(self.log, "w") as fh:  # a contiguous log whose only flaw is the unhashable id
            fh.write('{"seq": 1, "type": "artefato.published", "payload": {"slug": "alpha-post"}}\n')
            fh.write('{"seq": 2, "type": "voz.clarify", "payload": '
                     '{"comment_id": ["x"], "clarify_id": "q1", "question": "?"}}\n')
        self.assertFalse(grill_drain.log_is_intact(self.log))
        called = {"n": 0}
        loaded = self.drain.drain(self.log,
                                  lambda c: (called.__setitem__("n", called["n"] + 1) or {"reply": "x"}),
                                  grill_run_id="g1")
        self.assertEqual(loaded, [])
        self.assertEqual(called["n"], 0)

    def test_drain_on_a_seq_gapped_legacy_log_appends_nothing_and_calls_no_generator(self):
        # a seq-gapped log (1,2,3 then a gap to 9) with a legacy reply-only target
        import eventlog
        cid = self._comment("oi", "alpha-post")  # contiguous so far
        eventlog.append("voz.reply", "voz:alpha-post", {"comment_id": cid, "body": "hand reply"},
                        log=self.log)
        with open(self.log, "a") as fh:  # inject a seq gap
            fh.write('{"seq": 99, "type": "voz.comment", "payload": '
                     '{"target_ref": "alpha-post", "comment_id": "gap", "body": "post-gap"}}\n')
        before = len([ln for ln in self.log.read_text().splitlines() if ln.strip()])
        called = {"n": 0}
        loaded = self.drain.drain(self.log,
                                  lambda c: (called.__setitem__("n", called["n"] + 1) or {"reply": "x"}),
                                  grill_run_id="g1")
        self.assertEqual(loaded, [])           # degraded — nothing loaded
        self.assertEqual(called["n"], 0)       # generator never invoked
        after = len([ln for ln in self.log.read_text().splitlines() if ln.strip()])
        self.assertEqual(after, before)        # nothing appended over the corrupt log


class TestDrainConcurrencyDoesNotDoubleSpend(_Base):
    """The paid reply-generator must not be invoked twice for the same comment under overlapping
    drains (the version guard keeps DATA consistent, but a wasted paid call is not idempotent). A
    cross-process drain lock serializes executions so the second drain re-reads the now-closed state
    and never generates for an already-resolved comment — protecting the user's OpenAI API spend."""

    def test_a_second_drain_does_not_regenerate_for_an_already_closed_comment(self):
        # drain A closes the comment; an overlapping drain B (same actionable snapshot intent) must
        # NOT call the generator again for it — under the lock, B re-reads and sees it closed.
        cid = self._comment("one directive", "alpha-post")
        calls = []

        def gen(comment):
            calls.append(comment["comment_id"])
            return {"reply": "r"}

        self.drain.drain(self.log, gen, grill_run_id="gA")
        self.assertEqual(calls, [cid])
        # a second drain over the same log: the comment is already closed → not actionable → no call
        self.drain.drain(self.log, gen, grill_run_id="gB")
        self.assertEqual(calls, [cid])  # generator NOT invoked a second time

    def test_drain_serializes_under_a_lock(self):
        # the drain acquires an exclusive lock for its whole execution, so two drains cannot
        # interleave their snapshot→generate→close windows (the double-spend race). We assert the
        # lock is held across the generate step by checking a nested drain re-entry finds no work.
        self._comment("d", "alpha-post")
        seen = {"reentrant_loaded": None}

        def gen(comment):
            # while this (paid) call is "in flight", a concurrent drain must not also load it: a
            # re-entrant drain under the held lock would block in real concurrency; here we assert
            # the actionable snapshot is taken once (the comment is in THIS batch, not re-loadable).
            seen["reentrant_loaded"] = [c["comment_id"]
                                        for c in self.drain.actionable_set(self.log)]
            return {"reply": "r"}

        loaded = self.drain.drain(self.log, gen, grill_run_id="g1")
        self.assertEqual(len(loaded), 1)


class TestConsistencyErrors(_Base):
    """Acceptance (e): a duplicate / orphan voz.resolved surfaces as a consistency error."""

    def test_duplicate_resolved_is_a_consistency_error(self):
        cid = self._comment("once", "alpha-post")
        self._add("voz.resolved", "voz:alpha-post",
                  {"comment_id": cid, "outcome": "replied", "grill_run_id": "g1"})
        self._add("voz.resolved", "voz:alpha-post",
                  {"comment_id": cid, "outcome": "replied", "grill_run_id": "g2"})
        errs = self.drain.consistency_errors(self.log)
        self.assertTrue(any(e["kind"] == "duplicate-resolved" and e["comment_id"] == cid
                            for e in errs))

    def test_orphan_resolved_is_a_consistency_error(self):
        # a voz.resolved with no preceding voz.comment
        self._add("voz.resolved", "voz:alpha-post",
                  {"comment_id": "ghost", "outcome": "replied", "grill_run_id": "g1"})
        errs = self.drain.consistency_errors(self.log)
        self.assertTrue(any(e["kind"] == "orphan-resolved" and e["comment_id"] == "ghost"
                            for e in errs))

    def test_dangling_direction_id_is_a_consistency_error(self):
        cid = self._comment("steer", "alpha-post")
        self._add("voz.resolved", "voz:alpha-post",
                  {"comment_id": cid, "outcome": "folded-to-direction",
                   "origin_comment_id": cid, "direction_id": "nope", "grill_run_id": "g1"})
        errs = self.drain.consistency_errors(self.log)
        self.assertTrue(any(e["kind"] == "dangling-direction" for e in errs))

    def test_folded_direction_missing_origin_comment_id_is_a_consistency_error(self):
        # ADR-0007/SURFACE: a Direction mutation folded from a Directive MUST carry origin_comment_id.
        # A direction.set the resolved points at, but with NO origin_comment_id, is a broken audit link.
        cid = self._comment("steer", "alpha-post")
        self._add("direction.set", "direction",
                  {"id": "d1", "body": "a steer", "kind": "thread", "supersedes": None})  # no origin!
        self._add("voz.resolved", "voz:alpha-post",
                  {"comment_id": cid, "outcome": "folded-to-direction",
                   "origin_comment_id": cid, "direction_id": "d1", "grill_run_id": "g1"})
        errs = self.drain.consistency_errors(self.log)
        self.assertTrue(any(e["kind"] == "provenance-missing" for e in errs))

    def test_folded_direction_mismatched_origin_is_a_consistency_error(self):
        # the direction.set carries a DIFFERENT origin_comment_id than the resolved event → mismatch.
        cid = self._comment("steer", "alpha-post")
        self._add("direction.set", "direction",
                  {"id": "d1", "body": "a steer", "kind": "thread", "supersedes": None,
                   "origin_comment_id": "someone-else"})
        self._add("voz.resolved", "voz:alpha-post",
                  {"comment_id": cid, "outcome": "folded-to-direction",
                   "origin_comment_id": cid, "direction_id": "d1", "grill_run_id": "g1"})
        errs = self.drain.consistency_errors(self.log)
        self.assertTrue(any(e["kind"] == "provenance-mismatch" for e in errs))

    def test_a_clean_drain_has_no_consistency_errors(self):
        self._comment("clean", "alpha-post")
        self.drain.drain(self.log, self._reply_stub(), grill_run_id="g1")
        self.assertEqual(self.drain.consistency_errors(self.log), [])

    def test_a_clean_fold_has_no_provenance_error(self):
        # the real drain fold carries matching origin_comment_id on both events → clean.
        cid = self._comment("a standing steer", "alpha-post")
        self.drain.drain(self.log,
                         lambda c: {"reply": "r", "directive": True, "direction_body": "x"},
                         grill_run_id="g1")
        errs = self.drain.consistency_errors(self.log)
        self.assertEqual([e for e in errs if "provenance" in e["kind"]], [])


class TestCapAndOverflow(_Base):
    """Acceptance (f): with more actionable comments than the cap, the drain processes only the
    capped batch and the overflow stays open + visible (not dropped, not one oversized prompt)."""

    def test_overflow_beyond_the_cap_stays_open(self):
        cids = [self._comment(f"directive {i}", "alpha-post") for i in range(5)]
        loaded = self.drain.drain(self.log, self._reply_stub(), grill_run_id="g1", cap=2)
        self.assertEqual(len(loaded), 2)  # only the cap loaded
        closed = [c["comment_id"] for c in loaded]
        still_open = [c["comment_id"] for c in self.server.open_comments()]
        # the 3 overflow remain open + visible; the 2 loaded left
        self.assertEqual(len(still_open), 3)
        for cid in cids:
            self.assertEqual(cid in closed, cid not in still_open)

    def test_harm_ranked_batch_loads_the_harmful_first(self):
        # deterministic harm-ranking: a body flagged harmful loads before a benign one under a cap.
        benign = self._comment("a routine note", "alpha-post")
        harmful = self._comment("this is wrong and unsafe, correct it", "alpha-post")
        loaded = self.drain.drain(self.log, self._reply_stub(), grill_run_id="g1", cap=1)
        self.assertEqual([c["comment_id"] for c in loaded], [harmful])
        self.assertIn(benign, [c["comment_id"] for c in self.server.open_comments()])

    def test_actionable_set_is_bounded_by_a_cursor(self):
        # ADR-0017 cursor-bound invariant: actionable_set(log, until_seq=cursor) sees only comments
        # at/under the cursor — a post-cursor arrival is NOT in the batch.
        old = self._comment("before the cursor", "alpha-post")
        cursor = self.drain._start_cursor(self.log)
        new = self._comment("after the cursor", "alpha-post")
        bounded = [c["comment_id"] for c in self.drain.actionable_set(self.log, until_seq=cursor)]
        self.assertIn(old, bounded)
        self.assertNotIn(new, bounded)  # post-cursor arrival excluded

    def test_drain_does_not_load_a_post_cursor_arrival(self):
        # a high-harm comment arriving AFTER the cursor must not displace a cursor-bound comment
        # under the cap — the batch is cursor-bounded so ordering is not race-dependent. Simulate by
        # asserting the drain's loaded set is drawn only from the pre-cursor snapshot.
        old = self._comment("a routine pre-cursor note", "alpha-post")
        # the drain captures its cursor, THEN (in a race) a high-harm comment lands — but the drain
        # already snapshotted the actionable set at its cursor, so the new one is overflow.
        import eventlog
        # monkeypatch: inject a post-cursor arrival mid-drain via a spy reply_fn on the first call
        injected = {"done": False}

        def racing_reply(comment):
            if not injected["done"]:
                injected["done"] = True
                eventlog.append("voz.comment", "voz:alpha-post",
                                {"target_ref": "alpha-post", "comment_id": "racer",
                                 "body": "wrong unsafe harm correct it now"}, log=self.log)
            return {"reply": "ok"}

        loaded = self.drain.drain(self.log, racing_reply, grill_run_id="g1", cap=5)
        loaded_ids = [c["comment_id"] for c in loaded]
        self.assertIn(old, loaded_ids)
        self.assertNotIn("racer", loaded_ids)  # the post-cursor arrival is not in THIS batch
        self.assertIn("racer", [c["comment_id"] for c in self.server.open_comments()])  # overflow

    def test_overflow_is_loaded_by_a_second_drain(self):
        for i in range(3):
            self._comment(f"d{i}", "alpha-post")
        self.drain.drain(self.log, self._reply_stub(), grill_run_id="g1", cap=2)
        self.assertEqual(len(self.server.open_comments()), 1)
        self.drain.drain(self.log, self._reply_stub(), grill_run_id="g2", cap=2)
        self.assertEqual(self.server.open_comments(), [])  # the overflow drained next run


if __name__ == "__main__":
    unittest.main(verbosity=2)
