"""Slice 6b — the Earmarked corrective write-path (node-targeted Voz).

Close the safety feedback loop: an Earmarked Cortex node gets a CORRECTION affordance — a small Voz
composer in its inspect panel that posts a `voz.comment` whose `target_ref` is the Cortex NODE ref
(beyond the slug namespace). The Slice-1 write validation is extended to allowlist a valid Cortex
node `target_ref` (a node present in the group_id-scoped cortex payload); an invalid/unknown node ref
is rejected with NO append. The correction rides the SAME `authorize_write` gate + canonical
`eventlog` append, and the Slice-2 drain resolves it like any Directive — with `origin_comment_id`
and the node `target_ref` provenance preserved.

A node `target_ref` carries the `node:<node_id>` namespace — unambiguous against a bare slug (a slug
never contains `:` — publisher's SLUG_RE), so the existing slug validation is untouched.

TDD seam: EDGE_CORTEX_FIXTURE (the {nodes, edges} payload) + EDGE_DASH_AUTH (the auth principal) +
DRAIN_REPLY_GENERATOR (the stubbed reply-generator — ZERO API spend in every test).
"""
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

BLOG = Path(__file__).resolve().parent.parent / "blog"

# A small whole-Cortex fixture with an Earmarked node (e1, the harm-bearing one to correct).
FIXTURE = {
    "nodes": [
        {"id": "g0", "label": "Genesis", "title": "ed", "trust": "space0", "earmarked": False},
        {"id": "a1", "label": "Artefato", "title": "alpha-post", "trust": "asserted", "earmarked": False},
        {"id": "e1", "label": "Entity", "title": "a harmful claim", "trust": "extracted", "earmarked": True},
        {"id": "ep1", "label": "Episodic", "title": "session-x", "trust": "episodic", "earmarked": False},
    ],
    "edges": [
        {"id": "r0", "source": "g0", "target": "a1", "type": "GROUNDS"},
        {"id": "r1", "source": "a1", "target": "e1", "type": "DISTILLS"},
    ],
}


def _ev(seq, ts, type_, slug, payload_extra=None):
    payload = {"slug": slug}
    payload.update(payload_extra or {})
    return json.dumps({"seq": seq, "ts": ts, "type": type_, "subject": f"artefato:{slug}",
                       "payload": payload})


class _Base(unittest.TestCase):
    """A blog server over a temp log + the cortex fixture (an Earmarked node e1). One published
    slug (alpha-post) so the slug-target_ref path stays exercisable alongside the node path."""

    AUTH = "on"  # the real gate by default; subclasses override for an isolated principal

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        entries = root / "entries"
        entries.mkdir()
        (entries / "alpha-post.html").write_text("<html><body><h1>alpha</h1></body></html>")
        self.fix = root / "cortex.json"
        self.fix.write_text(json.dumps(FIXTURE))
        self.log = root / "log.jsonl"
        self.log.write_text("\n".join([
            _ev(1, "2026-06-10T09:00:00+00:00", "artefato.published", "alpha-post",
                {"cites": [], "distills": [], "proposes": []}),
            _ev(2, "2026-06-10T09:00:01+00:00", "intent.kernel", "alpha-post",
                {"intent": "open: alpha."}),
        ]) + "\n")
        os.environ["EDGE_BLOG_ENTRIES"] = str(entries)
        os.environ["EDGE_BLOG_STATIC"] = str(root)
        os.environ["EDGE_BLOG_LOG"] = str(self.log)
        os.environ["EDGE_CORTEX_FIXTURE"] = str(self.fix)
        os.environ["EDGE_GROUP"] = "edge-next"
        os.environ["EDGE_DASH_AUTH"] = self.AUTH
        os.environ.pop("EDGE_DASH_TOKEN", None)
        sys.path.insert(0, str(BLOG))
        import server
        importlib.reload(server)
        self.server = server
        self.client = server.app.test_client()

    def tearDown(self):
        for k in ("EDGE_BLOG_ENTRIES", "EDGE_BLOG_STATIC", "EDGE_BLOG_LOG", "EDGE_CORTEX_FIXTURE",
                  "EDGE_GROUP", "EDGE_DASH_AUTH", "EDGE_DASH_TOKEN"):
            os.environ.pop(k, None)
        self.tmp.cleanup()

    def _events(self, type_):
        out = []
        for line in self.log.read_text().splitlines():
            if line.strip():
                e = json.loads(line)
                if e.get("type") == type_:
                    out.append(e)
        return out

    def _count(self):
        return len([ln for ln in self.log.read_text().splitlines() if ln.strip()])

    _REMOTE = {"REMOTE_ADDR": "10.0.0.5"}

    def _post(self, path, data=None, *, local=True, origin=None):
        kw = {}
        if not local:
            kw["environ_overrides"] = dict(self._REMOTE)
        if origin is not None:
            kw["headers"] = {"Origin": origin}
        return self.client.post(path, data=data or {}, **kw)


class TestNodeTargetRefValidation(_Base):
    """The Slice-1 `target_ref` validation, extended to a Cortex node ref. A node ref `node:<id>` is
    valid iff <id> is a node in the group-scoped cortex payload (cortex_fold). Slug refs are untouched."""

    AUTH = "test:mentee"  # authorized — isolate the validation from the auth gate

    def test_valid_node_ref_is_accepted(self):
        # e1 is a real node in the fixture payload → its node ref validates
        self.assertTrue(self.server._valid_node_target_ref("node:e1"))

    def test_unknown_node_ref_is_rejected(self):
        # a node id absent from the payload → not a valid target (forged node ref)
        self.assertFalse(self.server._valid_node_target_ref("node:ghost"))

    def test_non_earmarked_node_ref_is_rejected(self):
        # codex round-1 [high]: the corrective write-path is for the HARM-settled Earmarked subset
        # (SURFACE.md: Earmarked = harm-surfacing; the correction surface backs the harm frontier).
        # A real-but-INERT node (a1, not earmarked) is navigable, not correctable — the server must
        # enforce earmarked, not just node existence, or a crafted POST expands Voz corrective
        # authority beyond the eligible subset and pollutes the Directive backlog / curated Direction.
        self.assertFalse(self.server._valid_node_target_ref("node:a1"))    # exists, NOT earmarked
        self.assertTrue(self.server._valid_node_target_ref("node:e1"))     # exists AND earmarked

    def test_truthy_but_non_boolean_earmarked_is_rejected(self):
        # codex round-2 [high]: fail closed ON TYPE. Schema drift in the payload — a string "false" /
        # "0" or an int 1 — is TRUTHY, so a `bool(...)` / truthy check would promote an inert node
        # into the eligible harm subset. Only a LITERAL boolean True crosses the corrective boundary.
        import json as _json
        from pathlib import Path as _P
        # rewrite the fixture with poisoned earmarked values on otherwise-valid nodes
        poisoned = {
            "nodes": [
                {"id": "p_str", "label": "Entity", "title": "x", "trust": "extracted", "earmarked": "false"},
                {"id": "p_zero", "label": "Entity", "title": "y", "trust": "extracted", "earmarked": "0"},
                {"id": "p_int", "label": "Entity", "title": "z", "trust": "extracted", "earmarked": 1},
                {"id": "p_true", "label": "Entity", "title": "real", "trust": "extracted", "earmarked": True},
            ],
            "edges": [],
        }
        _P(self.fix).write_text(_json.dumps(poisoned))
        # a truthy-but-non-boolean earmarked must NOT validate (only literal True does)
        self.assertFalse(self.server._valid_node_target_ref("node:p_str"))
        self.assertFalse(self.server._valid_node_target_ref("node:p_zero"))
        self.assertFalse(self.server._valid_node_target_ref("node:p_int"))
        self.assertTrue(self.server._valid_node_target_ref("node:p_true"))

    def test_map_node_preserves_only_literal_boolean_earmarked(self):
        # codex round-2 [high]: the LIVE fold (_map_node) must not coerce a truthy non-bool into True.
        # A poisoned prop ("false" / "0" / 1) → earmarked False; only a literal True stays True.
        self.assertIs(self.server._map_node("4:x:1", "Entity", {"earmarked": "false"})["earmarked"], False)
        self.assertIs(self.server._map_node("4:x:2", "Entity", {"earmarked": "0"})["earmarked"], False)
        self.assertIs(self.server._map_node("4:x:3", "Entity", {"earmarked": 1})["earmarked"], False)
        self.assertIs(self.server._map_node("4:x:4", "Entity", {"earmarked": True})["earmarked"], True)
        self.assertIs(self.server._map_node("4:x:5", "Entity", {})["earmarked"], False)


class TestCorrectionAppend(_Base):
    """An authenticated correction from an Earmarked node posts a `voz.comment` whose `target_ref`
    is the node ref — through the SAME canonical append. The drain then resolves it like any Directive."""

    AUTH = "test:mentee"  # authorized — isolate the append path from the gate

    def test_correction_appends_one_voz_comment_with_the_node_target_ref(self):
        before = self._count()
        r = self._post("/cortex/e1/comment", {"body": "this claim is wrong — correct it"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._count(), before + 1)
        comments = self._events("voz.comment")
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["payload"]["target_ref"], "node:e1")
        self.assertEqual(comments[0]["payload"]["body"], "this claim is wrong — correct it")
        self.assertIn("comment_id", comments[0]["payload"])

    def test_duplicate_correction_nonce_appends_once(self):
        # codex round-1 [medium]: the correction route honors the SAME idempotency model as every
        # other Voz composer — a double-fire (same comment_nonce + same body, a double-click / retry)
        # appends exactly ONCE, so a flaky network / double-submit can't create duplicate open
        # Directives (which, if standing, would fold into duplicate direction.set).
        before = self._count()
        r1 = self._post("/cortex/e1/comment",
                        {"body": "double correction", "comment_nonce": "corr:e1:0"})
        r2 = self._post("/cortex/e1/comment",
                        {"body": "double correction", "comment_nonce": "corr:e1:0"})
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(self._count(), before + 1)  # ONE event, not two
        self.assertEqual(len(self._events("voz.comment")), 1)

    def test_distinct_correction_nonces_both_append(self):
        # a deliberate second correction (advanced nonce, e.g. after a successful first) still lands —
        # the nonce dedupes a transport retry, never a legitimate follow-up correction.
        before = self._count()
        self._post("/cortex/e1/comment", {"body": "one", "comment_nonce": "corr:e1:0"})
        self._post("/cortex/e1/comment", {"body": "two", "comment_nonce": "corr:e1:1"})
        self.assertEqual(self._count(), before + 2)


class TestCorrectionRejected(_Base):
    """The reject cases (acceptance): an invalid/unknown node ref → rejected, no append; an
    unauthenticated / cross-origin correction → rejected, no append (the Slice-1 gate)."""

    AUTH = "on"  # the real gate, so the auth rejections are exercised end-to-end

    def test_invalid_node_ref_is_rejected_with_no_append(self):
        before = self._count()
        r = self._post("/cortex/ghost/comment", {"body": "correcting a node that does not exist"},
                       local=True)
        self.assertIn(r.status_code, (400, 404))
        self.assertEqual(self._count(), before)  # nothing appended
        self.assertEqual(self._events("voz.comment"), [])

    def test_correction_on_a_non_earmarked_node_is_rejected_with_no_append(self):
        # codex round-1 [high]: a1 is a real node but NOT earmarked → not correctable. A crafted POST
        # to a non-earmarked node must reject with no append (the harm boundary is server-enforced,
        # not UI-only) — else Voz corrective authority leaks beyond the Earmarked harm subset.
        before = self._count()
        r = self._post("/cortex/a1/comment", {"body": "correcting an inert node"}, local=True)
        self.assertIn(r.status_code, (400, 404))
        self.assertEqual(self._count(), before)
        self.assertEqual(self._events("voz.comment"), [])

    def test_unauthenticated_correction_is_rejected_with_no_append(self):
        before = self._count()
        r = self._post("/cortex/e1/comment", {"body": "spoofed correction"}, local=False)
        self.assertIn(r.status_code, (401, 403))
        self.assertEqual(self._count(), before)
        self.assertEqual(self._events("voz.comment"), [])

    def test_cross_origin_correction_is_rejected_with_no_append(self):
        before = self._count()
        r = self._post("/cortex/e1/comment", {"body": "csrf correction"},
                       local=True, origin="http://evil.example")
        self.assertIn(r.status_code, (401, 403))
        self.assertEqual(self._count(), before)
        self.assertEqual(self._events("voz.comment"), [])

    def test_auth_is_checked_before_node_validation(self):
        """An unauthenticated correction to an INVALID node ref still rejects as auth (403), and the
        node validation (which folds the graph) is never reached — the gate is the outer boundary."""
        before = self._count()
        r = self._post("/cortex/ghost/comment", {"body": "spoofed + forged"}, local=False)
        self.assertIn(r.status_code, (401, 403))
        self.assertEqual(self._count(), before)


class TestCorrectionEntryPoint(unittest.TestCase):
    """The correction AFFORDANCE: the /cortex island builds a Voz composer in the inspect panel of an
    EARMARKED node, posting the correction to the node-targeted route. Asserted over the island
    source (the DOM island is not jsdom-driven here) + the rendered /cortex body, mirroring how the
    href drill-down is tested. The node id reaches the route URL via a DOM-safe construction (no
    attribute-string interpolation — the same breakout defense as the source-href link)."""

    JS = (BLOG / "static" / "cortex.js").read_text()

    def test_island_builds_a_correction_composer_for_earmarked_nodes(self):
        # the inspect panel offers a correction composer ONLY for an Earmarked node (the harm subset
        # the mentee corrects); a plain node gets only the read-only inspect + source link.
        self.assertIn("earmarked", self.JS)
        self.assertIn("/cortex/", self.JS)             # the node-targeted correction route
        self.assertIn("/comment", self.JS)
        # the composer posts a body (the correction prose) — a textarea/field named "body"
        self.assertIn('"body"', self.JS)

    def test_composer_sends_a_comment_nonce_for_idempotency(self):
        # codex round-1 [medium]: the composer must carry a stable per-render comment_nonce so the
        # route takes the idempotent append path — a double-submit can't create duplicate Directives
        # (which, if standing, fold into duplicate direction.set). It advances after a successful
        # submit (the same stable-then-advance pattern as the other Voz composers), so a deliberate
        # repeat still lands.
        self.assertIn("comment_nonce", self.JS)

    def test_composer_nonce_is_render_unique_not_a_fixed_zero(self):
        # codex round-2 [medium]: the nonce must SURVIVE a panel rebuild. A hardcoded `corr:<id>:0`
        # seed resets to the same value every time appendCorrection rebuilds the composer, so the
        # same body after reopening the panel collides on the server idempotency key and is silently
        # dropped (the same same-body-follow-up loss the server-rendered composers avoid). The nonce
        # base must be RENDER-UNIQUE (a fresh token per build), stable only for retries within a render.
        # We pin the unique seed (a Date.now()/random token) so the base differs across rebuilds.
        self.assertTrue("Date.now()" in self.JS or "Math.random()" in self.JS,
                        "the correction nonce must seed from a render-unique token (Date.now/random)")

    def test_correction_url_is_built_dom_safe_not_attribute_string_interp(self):
        # SECURITY: the node id is graph-derived; building the POST URL by interpolating it into an
        # action="..."/href="..." attribute STRING would repeat the round-1 breakout surface. The id
        # is url-encoded and the action assigned via a DOM property — never a quoted attribute string.
        self.assertIn("encodeURIComponent", self.JS)

    def test_cortex_page_ships_the_island_that_carries_the_correction(self):
        # the live page loads the island script that wires the correction composer (not latent).
        with tempfile.TemporaryDirectory() as td:
            fix = Path(td) / "cortex.json"
            fix.write_text(json.dumps(FIXTURE))
            server = _load_server({"EDGE_CORTEX_FIXTURE": str(fix), "EDGE_GROUP": "edge-next"})
            body = server.app.test_client().get("/cortex").data.decode()
            os.environ.pop("EDGE_CORTEX_FIXTURE", None)
        self.assertIn("/static/cortex.js", body)
        # the Earmarked node is shipped so the island can offer the correction on it
        self.assertIn("earmarked", body.lower())


def _load_server(env):
    for k, v in env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    sys.path.insert(0, str(BLOG))
    import server
    importlib.reload(server)
    return server


class TestCorrectionRoundTrip(_Base):
    """The full round-trip (acceptance), ZERO API spend: from an Earmarked node an authenticated
    correction posts a `voz.comment` with the node `target_ref` → it appears as an OPEN Directive →
    run the drain with a STUBBED reply-generator → it reaches a terminal outcome with the
    `origin_comment_id` + node `target_ref` provenance preserved and LEAVES the open backlog. The
    drain is run as a local tool with the stub injected (never the live, API-spending generator)."""

    AUTH = "test:mentee"  # authorized — the round-trip is about the lifecycle, not the gate

    def _import_drain(self):
        sys.path.insert(0, str(BLOG))
        import grill_drain
        return grill_drain

    def test_node_targeted_correction_opens_a_directive_then_drains_to_terminal(self):
        drain = self._import_drain()
        # 1. post the correction from the Earmarked node e1
        r = self._post("/cortex/e1/comment", {"body": "this is a harmful claim — correct it"})
        self.assertEqual(r.status_code, 200)
        cid = self._events("voz.comment")[0]["payload"]["comment_id"]
        # 2. it appears as an OPEN Directive (any target — the node-target_ref comment is a Directive)
        open_now = [c["comment_id"] for c in drain.open_comments(self.log)]
        self.assertIn(cid, open_now)
        # the node-target_ref comment is in the actionable set the drain may load
        actionable = [c["comment_id"] for c in drain.actionable_set(self.log)]
        self.assertIn(cid, actionable)
        # 3. run the drain with a STUBBED reply-generator — NO live LLM, zero API spend
        stub = lambda comment: {"reply": "you're right — I'll retract that claim."}
        loaded = drain.drain(self.log, stub, grill_run_id="g1")
        self.assertIn(cid, [c["comment_id"] for c in loaded])
        # 4. it reached a TERMINAL outcome and LEFT the open backlog
        self.assertIn(cid, drain.terminally_resolved(self.log))
        self.assertNotIn(cid, [c["comment_id"] for c in drain.open_comments(self.log)])
        # a voz.reply was generated (rendered inline by the dashboard); the node target_ref is
        # preserved on the originating comment (provenance back to the corrected node)
        replies = self._events("voz.reply")
        self.assertEqual([x["payload"]["comment_id"] for x in replies], [cid])
        comment = self._events("voz.comment")[0]["payload"]
        self.assertEqual(comment["target_ref"], "node:e1")  # node provenance preserved

    def test_standing_node_correction_folds_to_direction_with_provenance(self):
        """A standing node-correction Directive → drain (stub marks it a directive) → `direction.set`
        + `voz.resolved{folded-to-direction, origin_comment_id, direction_id}`. The `origin_comment_id`
        provenance is preserved, and the corrective link is visible from the Direction surface (the
        steer carries origin_comment_id back to the correction comment). ZERO API spend."""
        drain = self._import_drain()
        r = self._post("/cortex/e1/comment",
                       {"body": "stop trusting this source — it is unsafe"})
        self.assertEqual(r.status_code, 200)
        cid = self._events("voz.comment")[0]["payload"]["comment_id"]
        # the stub classifies it a STANDING Directive → the drain folds it to a curated steer
        stub = lambda comment: {"reply": "agreed — retiring that trust.",
                                "directive": True,
                                "direction_body": "Distrust the unsafe source flagged on the node."}
        drain.drain(self.log, stub, grill_run_id="g2")
        # the terminal outcome carries the fold provenance: origin_comment_id == the correction comment
        resolved = self._events("voz.resolved")
        self.assertEqual(len(resolved), 1)
        rp = resolved[0]["payload"]
        self.assertEqual(rp["outcome"], "folded-to-direction")
        self.assertEqual(rp["origin_comment_id"], cid)
        # the curated steer carries the same origin_comment_id (the corrective link, visible on /direction)
        sets = self._events("direction.set")
        self.assertEqual(len(sets), 1)
        self.assertEqual(sets[0]["payload"]["origin_comment_id"], cid)
        self.assertEqual(sets[0]["payload"]["id"], rp["direction_id"])
        # and the originating comment still carries its node target_ref (provenance to the node)
        self.assertEqual(self._events("voz.comment")[0]["payload"]["target_ref"], "node:e1")

    def test_drain_run_was_zero_api_spend(self):
        """Belt-and-suspenders: the round-trip drain used the injected stub, never the live
        generator factory (which would spend the user's OpenAI API). The stub is the only callable
        passed to drain(); live_reply_generator is never built."""
        drain = self._import_drain()
        self._post("/cortex/e1/comment", {"body": "correct this"})
        calls = {"n": 0}

        def stub(comment):
            calls["n"] += 1
            return {"reply": "noted."}

        drain.drain(self.log, stub, grill_run_id="g3")
        self.assertEqual(calls["n"], 1)  # exactly the loaded correction; no live LLM


if __name__ == "__main__":
    unittest.main(verbosity=2)
