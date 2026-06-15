"""Slice 3 — the Briefing surface (`GET /briefing`) + the read-model health strip + shared nav.

The Briefing is the self-state landing: it renders `tools/briefing.py::compose_briefing` — the EXACT
text the edge wakes to (curated Direction, open bets, corpus head, clusters, source orientation) — as
a PURE projection of the log + genotype, with **zero LLM/API spend** on render (compose_briefing is a
fold, not a generator; the route pins clusters=None / recap=None so it never even probes neo4j).

Above it sits a compact **read-model health strip** — last dispatch, log cursor, sweep/extraction
signal, graph reachability, open-Directive count, Voz backlog/awaiting-clarification, and resolution-
consistency errors — folded from the log. It fails **dark** (a visible degraded band), never blank,
when a fold degrades.

These tests pin that on a throwaway temp log + a throwaway genotype (CONTRACT C1 — never real state/),
and assert the render makes no API call by injecting a tripwire compose function.
"""
import importlib
import json
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _ev(seq, ts, type_, payload, subject="x"):
    return json.dumps({"seq": seq, "ts": ts, "type": type_, "subject": subject, "payload": payload})


class _BriefingBase(unittest.TestCase):
    """A hermetic blog server over a throwaway log + a throwaway genotype (agent.yaml + memory/),
    so compose_briefing's fail-closed genotype inputs are satisfied without touching real state/."""

    LOG_LINES = []

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        entries = root / "entries"
        entries.mkdir()

        # A throwaway genotype the briefing's fail-closed head accepts: identity + a declared source
        # + the immutable doctrine docs + a state/idiom.md (memory.parent / "state").
        memory = root / "memory"
        memory.mkdir()
        (memory / "personality.md").write_text("# Personality\n\nAnalytical and skeptical.")
        (memory / "method.md").write_text("# Method\n\nDerive before researching.")
        (root / "state").mkdir()
        (root / "state" / "idiom.md").write_text("# Idiom\n\n**beat** — the work cycle.")
        agent_yaml = root / "agent.yaml"
        agent_yaml.write_text(textwrap.dedent("""\
            name: ed
            mission: "Mentor to the edge-of-chaos PM."
            voice: "Direct, technical, skeptical."
            sources:
              - name: exa
                kind: api
                description: "Neural/semantic web search."
            """))

        self.log = root / "log.jsonl"
        self.log.write_text("\n".join(self.LOG_LINES) + ("\n" if self.LOG_LINES else ""))

        os.environ["EDGE_BLOG_ENTRIES"] = str(entries)
        os.environ["EDGE_BLOG_STATIC"] = str(root)
        os.environ["EDGE_BLOG_LOG"] = str(self.log)
        # Briefing genotype seam — point compose_briefing at the throwaway genotype (CONTRACT C1).
        os.environ["EDGE_BRIEFING_AGENT_YAML"] = str(agent_yaml)
        os.environ["EDGE_BRIEFING_MEMORY"] = str(memory)
        sys.path.insert(0, str(REPO / "blog"))
        import server
        importlib.reload(server)
        self.server = server
        self.client = server.app.test_client()

    def tearDown(self):
        for k in ("EDGE_BRIEFING_AGENT_YAML", "EDGE_BRIEFING_MEMORY"):
            os.environ.pop(k, None)
        self.tmp.cleanup()


class TestBriefingRendersSelfState(_BriefingBase):
    """The composed wake-state renders on /briefing — the same text the edge wakes to."""

    LOG_LINES = [
        _ev(1, "2026-06-10T09:00:00+00:00", "objective.set",
            {"body": "ship the dashboard", "rationale": "the say-A-do-B gap"}),
        _ev(2, "2026-06-10T09:00:01+00:00", "direction.set",
            {"id": "d1", "body": "surface the self-state", "kind": "priority"}),
        _ev(3, "2026-06-10T09:00:02+00:00", "artefato.published",
            {"slug": "alpha-post", "cites": [], "distills": [], "proposes": []}),
        _ev(4, "2026-06-10T09:00:03+00:00", "intent.kernel",
            {"slug": "alpha-post", "intent": "open: alpha — the next bet is briefing."}),
    ]

    def test_briefing_renders_the_composed_wake_text(self):
        body = self.client.get("/briefing").data.decode()
        # the load-bearing inscribed lines — Objective, curated Direction, corpus head
        self.assertIn("ship the dashboard", body)
        self.assertIn("surface the self-state", body)
        self.assertIn("alpha-post", body)
        # the briefing's section scaffold (it is the wake artifact, not a recomposition)
        self.assertIn("Direction", body)

    def test_briefing_is_full_html_page(self):
        body = self.client.get("/briefing").data.decode()
        self.assertIn("<!DOCTYPE html", body)
        self.assertIn("/static/style.css", body)

    def test_briefing_reuses_compose_briefing_unrecomposed(self):
        """SURFACE.md: 'Reuses the wake artifact — exactly what the edge wakes to, no drift.' The
        route must call tools/briefing.compose_briefing, not a parallel recomposition."""
        self.assertTrue(hasattr(self.server, "_compose_briefing_text"))


class TestBriefingMakesNoApiCall(_BriefingBase):
    """CRITICAL (operator just got burned on API spend): rendering /briefing costs ZERO API. The
    route pins clusters=None / recap=None and compose_briefing is a pure fold — no LLM path. We prove
    it by replacing compose_briefing with a tripwire that fails if asked to do anything LLM-shaped and
    asserting clusters/recap are pinned to the non-generating values."""

    LOG_LINES = [
        _ev(1, "2026-06-10T09:00:00+00:00", "objective.set", {"body": "ship it"}),
    ]

    def test_render_pins_clusters_and_recap_to_non_generating_values(self):
        import briefing
        captured = {}
        real = briefing.compose_briefing

        def tripwire(*args, **kwargs):
            captured.update(kwargs)
            # clusters MUST be an explicit None (the Tier-0 / no-graph value) — never _AUTO, which
            # would navigate neo4j; recap MUST be None (a slot marker), never an LLM-synthesized one.
            assert kwargs.get("clusters", briefing._AUTO) is None, "clusters not pinned to None"
            assert kwargs.get("recap") is None, "recap not pinned to None"
            return real(*args, **kwargs)

        briefing.compose_briefing = tripwire
        try:
            r = self.client.get("/briefing")
        finally:
            briefing.compose_briefing = real
        self.assertEqual(r.status_code, 200)
        self.assertIs(captured.get("clusters"), None)
        self.assertIsNone(captured.get("recap"))

    def test_compose_briefing_has_no_llm_dependency(self):
        """A static guard: neither briefing.py nor the route imports an LLM client to render."""
        src = (REPO / "tools" / "briefing.py").read_text()
        for forbidden in ("import _llm", "import openai", "from openai", "chat_router", "anthropic"):
            self.assertNotIn(forbidden, src)


class TestHealthStrip(_BriefingBase):
    """The read-model health strip — a compact band folded from the log, above the briefing."""

    LOG_LINES = [
        _ev(1, "2026-06-10T09:00:00+00:00", "dispatch.open", {"swept_sessions": 3}, subject="dispatch"),
        _ev(2, "2026-06-10T09:00:01+00:00", "artefato.published",
            {"slug": "alpha-post", "cites": [], "distills": [], "proposes": []}),
        _ev(3, "2026-06-10T09:00:02+00:00", "intent.kernel",
            {"slug": "alpha-post", "intent": "open: alpha."}),
        _ev(4, "2026-06-10T09:00:03+00:00", "voz.comment",
            {"target_ref": None, "comment_id": "c-open-1", "body": "an open directive"}),
    ]

    def test_strip_renders_the_health_band(self):
        body = self.client.get("/briefing").data.decode()
        self.assertIn("health", body.lower())
        self.assertIn('class="health-strip"', body)

    def test_strip_shows_last_dispatch_and_cursor(self):
        body = self.client.get("/briefing").data.decode()
        self.assertIn("2026-06-10", body)         # last dispatch ts
        self.assertIn("4", body)                  # the log cursor (max seq)

    def test_strip_shows_open_directive_count(self):
        body = self.client.get("/briefing").data.decode()
        # one open voz.comment with no terminal voz.resolved
        self.assertIn("open Directive", body)
        self.assertIn('data-metric="open-directives">1', body)

    def test_strip_shows_swept_sessions(self):
        body = self.client.get("/briefing").data.decode()
        self.assertIn('data-metric="swept-sessions">3', body)


class TestHealthStripFailsDark(_BriefingBase):
    """The strip is the degraded-mode signal — a composed briefing can read plausible while the folds
    beneath it are stale (SURFACE.md: swept_sessions:0 yet the briefing composes clean). So a degraded
    fold renders a VISIBLE degraded band, never a blank."""

    LOG_LINES = [
        # the documented degrade: the sweep degraded to swept_sessions:0 (context-window overflow)
        _ev(1, "2026-06-10T09:00:00+00:00", "dispatch.open", {"swept_sessions": 0}, subject="dispatch"),
        # a duplicate voz.resolved — a resolution-consistency error
        _ev(2, "2026-06-10T09:00:01+00:00", "voz.comment",
            {"target_ref": None, "comment_id": "c1", "body": "directive"}),
        _ev(3, "2026-06-10T09:00:02+00:00", "voz.resolved",
            {"comment_id": "c1", "outcome": "replied"}),
        _ev(4, "2026-06-10T09:00:03+00:00", "voz.resolved",
            {"comment_id": "c1", "outcome": "replied"}),
    ]

    def test_degraded_sweep_renders_a_visible_degraded_state(self):
        body = self.client.get("/briefing").data.decode()
        # swept_sessions:0 is the documented degrade — it must be visibly flagged, not silently 0
        self.assertIn("degraded", body.lower())
        self.assertIn('class="health-strip degraded"', body)

    def test_consistency_error_surfaces_in_the_strip(self):
        body = self.client.get("/briefing").data.decode()
        # the duplicate voz.resolved must surface (SURFACE.md: a duplicate voz.resolved is an error)
        self.assertIn("consistency", body.lower())
        self.assertIn('data-metric="consistency-errors">1', body)


class TestBriefingComposeFailsDark(_BriefingBase):
    """If compose_briefing itself raises (a thin genotype / fail-closed identity error), the surface
    fails DARK — a visible degraded briefing band — never a 500 or a blank page (CONTRACT C1: the
    dark leg darkens only this view)."""

    LOG_LINES = [_ev(1, "2026-06-10T09:00:00+00:00", "objective.set", {"body": "ship it"})]

    def test_compose_error_renders_dark_not_500(self):
        import briefing
        real = briefing.compose_briefing

        def boom(*a, **k):
            raise briefing.BriefingIdentityError("thin genotype")

        briefing.compose_briefing = boom
        try:
            r = self.client.get("/briefing")
        finally:
            briefing.compose_briefing = real
        self.assertEqual(r.status_code, 200)  # dark, not 500
        body = r.data.decode()
        self.assertIn("dark", body.lower())
        # the health strip still renders (it folds the log independently of the composer)
        self.assertIn('class="health-strip', body)


class TestHealthStripFailsDarkOnSchemaDrift(_BriefingBase):
    """Codex [high]: a JSON-VALID but schema-drifted log line (`[]`, `42`, a bare string) must NOT
    500 the landing — `_last_dispatch()` / `_log_cursor()` call `.get()`/`["seq"]` on each event, so a
    non-dict event would crash outside the guarded Voz-fold. The health strip's contract is fail-dark
    on corrupt read-model input: a visible degraded band, never a blanked page. This is a realistic
    upgrade/corruption path (the drain treats schema-drifted lines as a fail-closed condition)."""

    LOG_LINES = [
        _ev(1, "2026-06-10T09:00:00+00:00", "dispatch.open", {"swept_sessions": 2}, subject="dispatch"),
        "[]",          # a JSON-valid non-dict line (schema drift)
        "42",          # a bare scalar
        '"a string"',  # a bare string
    ]

    def test_schema_drift_does_not_500_the_briefing(self):
        r = self.client.get("/briefing")
        self.assertEqual(r.status_code, 200)  # fail dark, not 500
        body = r.data.decode()
        self.assertIn('class="health-strip', body)  # the strip still renders


class TestHealthStripFailsDarkOnDriftedSeq(_BriefingBase):
    """Codex round-2 [high]: a JSON-valid DICT event with a schema-drifted `seq` (a string/list)
    passes `_dict_events()` yet makes `max()` raise in `_log_cursor()`. The degraded fallback must be
    type-stable so the renderer's int comparisons (`backlog > 0`) don't then TypeError → 500. One
    normal event + one dict event with a non-int seq → /briefing returns 200 with the degraded strip."""

    LOG_LINES = [
        _ev(1, "2026-06-10T09:00:00+00:00", "dispatch.open", {"swept_sessions": 2}, subject="dispatch"),
        # a JSON-valid dict whose seq is a string — drifts past _dict_events, breaks max()
        json.dumps({"seq": "not-an-int", "ts": "2026-06-10T09:00:01+00:00",
                    "type": "voz.comment", "subject": "x", "payload": {"comment_id": "c1"}}),
    ]

    def test_drifted_seq_fails_dark_not_500(self):
        r = self.client.get("/briefing")
        self.assertEqual(r.status_code, 200)  # fail dark, not 500
        body = r.data.decode()
        self.assertIn('class="health-strip degraded"', body)


class TestHealthStripFailsDarkOnMalformedLine(_BriefingBase):
    """Codex round-3 [high]: `_read_events()` SILENTLY DROPS a JSONDecodeError line, so a truly
    malformed (non-JSON) line was invisible to the strip — /briefing could read healthy while
    grill_drain.log_is_intact() treats the SAME line as corrupt and the drain refuses to run (the Voz
    write/drain path is dead). The strip must reuse the ONE strict integrity predicate
    (log_is_intact) so its corruption model matches the drain's: a malformed line → 200 + degraded."""

    LOG_LINES = [
        _ev(1, "2026-06-10T09:00:00+00:00", "dispatch.open", {"swept_sessions": 3}, subject="dispatch"),
        "{not valid json at all",  # a malformed (non-JSON) line — _read_events drops it silently
    ]

    def test_malformed_line_renders_200_and_visibly_degraded(self):
        r = self.client.get("/briefing")
        self.assertEqual(r.status_code, 200)
        body = r.data.decode()
        self.assertIn('class="health-strip degraded"', body)


class TestHealthStripFailsDarkOnSeqGap(_BriefingBase):
    """Codex round-3 [high]: a seq GAP / non-contiguous seq is corruption the drain's log_is_intact()
    rejects (append_batch stamps base=len(read())+i+1, so a gap would forge a duplicate seq). The
    strip must flag it degraded too — the same predicate, one corruption model."""

    LOG_LINES = [
        _ev(1, "2026-06-10T09:00:00+00:00", "dispatch.open", {"swept_sessions": 1}, subject="dispatch"),
        _ev(5, "2026-06-10T09:00:01+00:00", "objective.set", {"body": "ship it"}),  # seq jumps 1->5
    ]

    def test_seq_gap_renders_200_and_visibly_degraded(self):
        r = self.client.get("/briefing")
        self.assertEqual(r.status_code, 200)
        body = r.data.decode()
        self.assertIn('class="health-strip degraded"', body)


class TestBriefingDarkOnThinOverrideGenotype(_BriefingBase):
    """Codex [medium]: with EDGE_BRIEFING_AGENT_YAML set to a THIN/malformed agent.yaml,
    source_roster() must not escape the dark fallback — the override path must fail dark exactly like
    the default path (which catches roster failures inside compose_briefing)."""

    LOG_LINES = [_ev(1, "2026-06-10T09:00:00+00:00", "objective.set", {"body": "ship it"})]

    def setUp(self):
        super().setUp()
        # overwrite the genotype agent.yaml with a thin one (no sources) → source_roster raises
        thin = Path(os.environ["EDGE_BRIEFING_AGENT_YAML"])
        thin.write_text("name: ed\n")  # no sources: → BriefingIdentityError from source_roster

    def test_thin_override_renders_dark_not_500(self):
        r = self.client.get("/briefing")
        self.assertEqual(r.status_code, 200)  # dark, not a 500
        body = r.data.decode()
        self.assertIn("dark", body.lower())
        self.assertIn('class="health-strip', body)  # the strip still folds independently


class TestSharedReadSurfacesSurviveNonDictLine(_BriefingBase):
    """Codex round-4 [medium]: the shared nav now routes users across surfaces, so a single corrupt
    log must not 500 one surface while another handles it. A JSON-valid NON-dict line (`[]`, `42`) is
    a corruption case; the blog index + chat parse the log directly and called `e.get(...)` on each
    JSON value → AttributeError. Every read surface (`/`, `/chat`, `/briefing`) must render 200 over
    it (the non-dict line is skipped — it was never a valid event), not crash."""

    LOG_LINES = [
        _ev(1, "2026-06-10T09:00:00+00:00", "artefato.published",
            {"slug": "alpha-post", "cites": [], "distills": [], "proposes": []}),
        _ev(2, "2026-06-10T09:00:01+00:00", "intent.kernel",
            {"slug": "alpha-post", "intent": "open: alpha."}),
        "[]",   # a JSON-valid non-dict line — must be skipped by every read fold, not crash .get()
        "42",
    ]

    def test_index_survives_a_non_dict_line(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("alpha-post", r.data.decode())  # the valid post still renders

    def test_chat_survives_a_non_dict_line(self):
        self.assertEqual(self.client.get("/chat").status_code, 200)

    def test_briefing_survives_a_non_dict_line(self):
        self.assertEqual(self.client.get("/briefing").status_code, 200)


class TestSharedNav(_BriefingBase):
    """Task B — the shared header/nav (cross-cutting, starts at Slice 3): ONE nav linking all four
    surfaces, on every surface, built from the shared design vocabulary (no one-off styling)."""

    LOG_LINES = [
        _ev(1, "2026-06-10T09:00:00+00:00", "artefato.published",
            {"slug": "alpha-post", "cites": [], "distills": [], "proposes": []}),
        _ev(2, "2026-06-10T09:00:01+00:00", "intent.kernel",
            {"slug": "alpha-post", "intent": "open: alpha."}),
        _ev(3, "2026-06-10T09:00:02+00:00", "objective.set", {"body": "ship it"}),
    ]

    NAV_TARGETS = ('href="/"', 'href="/cortex"', 'href="/chat"', 'href="/briefing"')

    def _assert_nav(self, body):
        self.assertIn('class="site-nav"', body)
        for target in self.NAV_TARGETS:
            self.assertIn(target, body)

    def test_blog_index_carries_the_shared_nav(self):
        self._assert_nav(self.client.get("/").data.decode())

    def test_chat_carries_the_shared_nav(self):
        self._assert_nav(self.client.get("/chat").data.decode())

    def test_briefing_carries_the_shared_nav(self):
        self._assert_nav(self.client.get("/briefing").data.decode())

    def test_cortex_carries_a_corner_nav_link(self):
        # full-canvas /cortex gets a corner nav (not the full bar — it's a full-screen island)
        body = self.client.get("/cortex").data.decode()
        self.assertIn('href="/briefing"', body)
        self.assertIn('href="/"', body)

    def test_nav_marks_the_current_surface(self):
        # the active surface is marked (aria-current) so the nav reads as one app, not a pile of pages
        body = self.client.get("/briefing").data.decode()
        self.assertIn('aria-current="page"', body)


if __name__ == "__main__":
    unittest.main()
