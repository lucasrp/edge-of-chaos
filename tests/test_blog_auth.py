"""Slice 1 — the Voz write trust boundary.

Every `voz.*` write route is a mutation of the authoritative log (ADR-0006), so it sits behind a
single-tenant auth gate + CSRF/origin check + `target_ref` validation + a body-size limit, and
appends through the canonical `tools/eventlog` append (locked, idempotency key) — never the
hand-rolled `_append`. The gate rejects spoofing (cross-origin / unauthenticated), not the legitimate
local mentee: a same-origin localhost request is auto-granted a session, and a configured
`EDGE_DASH_TOKEN` authorizes a reverse-proxied principal.

Test seam: `EDGE_DASH_AUTH` sets/skips the auth principal:
  - unset / "on"  → the real gate (localhost auto-grant + token + CSRF/origin).
  - "off"         → gate disabled (the pre-Slice-1 behavior the existing suites rely on).
  - "test:<who>"  → a fixed authorized principal, no cookie dance.
"""
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


def _ev(seq, ts, type_, slug, payload_extra=None):
    payload = {"slug": slug}
    payload.update(payload_extra or {})
    return json.dumps({"seq": seq, "ts": ts, "type": type_, "subject": f"artefato:{slug}",
                       "payload": payload})


class _Base(unittest.TestCase):
    """A blog server over a temp log with two published slugs (alpha-post, beta-post)."""

    AUTH = "on"  # the real gate by default; subclasses may override

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        entries = root / "entries"
        entries.mkdir()
        for slug in ("alpha-post", "beta-post"):
            (entries / f"{slug}.html").write_text(f"<html><body><h1>{slug}</h1></body></html>")

        self.log = root / "log.jsonl"
        self.log.write_text("\n".join([
            _ev(1, "2026-06-10T09:00:00+00:00", "artefato.published", "alpha-post",
                {"cites": [], "distills": [], "proposes": []}),
            _ev(2, "2026-06-10T09:00:01+00:00", "intent.kernel", "alpha-post",
                {"intent": "open: alpha."}),
            _ev(3, "2026-06-12T15:30:00+00:00", "artefato.published", "beta-post",
                {"cites": [], "distills": [], "proposes": []}),
            _ev(4, "2026-06-12T15:30:01+00:00", "intent.kernel", "beta-post",
                {"intent": "open: beta."}),
        ]) + "\n")

        os.environ["EDGE_BLOG_ENTRIES"] = str(entries)
        os.environ["EDGE_BLOG_STATIC"] = str(root)
        os.environ["EDGE_BLOG_LOG"] = str(self.log)
        os.environ["EDGE_DASH_AUTH"] = self.AUTH
        os.environ.pop("EDGE_DASH_TOKEN", None)
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "blog"))
        import server
        importlib.reload(server)
        self.server = server
        self.client = server.app.test_client()

    def tearDown(self):
        os.environ.pop("EDGE_DASH_AUTH", None)
        os.environ.pop("EDGE_DASH_TOKEN", None)
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

    # Request shapes. The dashboard binds 127.0.0.1, so a loopback peer IS the operator; a
    # non-loopback peer (arrived over the network / a reverse proxy) is the untrusted surface.
    _REMOTE = {"REMOTE_ADDR": "10.0.0.5"}  # a non-local peer

    def _post(self, path, data=None, *, local=True, origin=None, token=None):
        kw = {}
        if not local:
            kw["environ_overrides"] = dict(self._REMOTE)
        headers = {}
        if origin is not None:
            headers["Origin"] = origin
        if token is not None:
            headers["X-Edge-Token"] = token
        if headers:
            kw["headers"] = headers
        return self.client.post(path, data=data or {}, **kw)


class TestUnauthenticatedRejected(_Base):
    """An unauthenticated write to a mutating route is log poisoning, not a comment — rejected
    with no append. The gate is ON (no token configured, no local session granted)."""

    AUTH = "on"

    def test_unauthenticated_comment_is_rejected_with_no_append(self):
        before = self._count()
        # a non-local peer, no token, no matching origin → unauthenticated
        r = self._post("/e/alpha-post/comment", {"body": "spoofed directive"}, local=False)
        self.assertIn(r.status_code, (401, 403))
        self.assertEqual(self._count(), before)  # nothing appended
        self.assertEqual(self._events("voz.comment"), [])

    def test_cross_origin_comment_is_rejected_even_from_local_peer(self):
        """CSRF: a browser ON the operator's box (loopback peer) is tricked by an attacker page
        into POSTing here. The cross-origin Origin header gives it away → rejected, no append."""
        before = self._count()
        r = self._post("/e/alpha-post/comment", {"body": "csrf directive"},
                       local=True, origin="http://evil.example")
        self.assertIn(r.status_code, (401, 403))
        self.assertEqual(self._count(), before)
        self.assertEqual(self._events("voz.comment"), [])


class TestEveryMutatingRouteGated(_Base):
    """The gate covers EVERY log-mutating route, not just /comment: the chat composer and the
    vote control. An unauthenticated call to any of them → rejected, no append (test each)."""

    AUTH = "on"

    def test_unauthenticated_chat_comment_rejected_no_append(self):
        before = self._count()
        r = self._post("/chat/comment", {"body": "spoofed chat"}, local=False)
        self.assertIn(r.status_code, (401, 403))
        self.assertEqual(self._count(), before)
        self.assertEqual(self._events("voz.comment"), [])

    def test_unauthenticated_vote_rejected_no_append(self):
        before = self._count()
        r = self._post("/e/alpha-post/vote", {"value": "1"}, local=False)
        self.assertIn(r.status_code, (401, 403))
        self.assertEqual(self._count(), before)
        self.assertEqual(self._events("voz.vote"), [])

    def test_local_operator_chat_and_vote_still_write(self):
        before = self._count()
        self.assertEqual(self._post("/chat/comment", {"body": "real chat"}, local=True).status_code, 200)
        self.assertEqual(self._post("/e/alpha-post/vote", {"value": "1"}, local=True).status_code, 200)
        self.assertEqual(self._count(), before + 2)


class TestTargetRefValidation(_Base):
    """A vote/comment may only target a slug that exists in the published fold. An unknown slug is
    log poisoning (a forged target_ref) → rejected, no append. Authorized (local) so we isolate the
    validation from the auth gate."""

    AUTH = "on"

    def test_comment_on_unknown_slug_is_rejected_no_append(self):
        before = self._count()
        r = self._post("/e/ghost-post/comment", {"body": "for a slug that does not exist"},
                       local=True)
        self.assertIn(r.status_code, (400, 404))
        self.assertEqual(self._count(), before)
        self.assertEqual(self._events("voz.comment"), [])

    def test_vote_on_unknown_slug_is_rejected_no_append(self):
        before = self._count()
        r = self._post("/e/ghost-post/vote", {"value": "1"}, local=True)
        self.assertIn(r.status_code, (400, 404))
        self.assertEqual(self._count(), before)
        self.assertEqual(self._events("voz.vote"), [])

    def test_comment_on_a_published_slug_still_appends(self):
        before = self._count()
        r = self._post("/e/beta-post/comment", {"body": "for a real slug"}, local=True)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._count(), before + 1)


class TestBodySizeLimit(_Base):
    """A comment is prose, not a payload. An oversized body → rejected, no append (defends the
    authoritative log against a flooded write). Authorized + valid slug so only size is at issue."""

    AUTH = "on"

    def test_oversized_comment_body_is_rejected_no_append(self):
        before = self._count()
        huge = "x" * (self.server.MAX_BODY_BYTES + 1)
        r = self._post("/e/alpha-post/comment", {"body": huge}, local=True)
        self.assertIn(r.status_code, (400, 413))
        self.assertEqual(self._count(), before)
        self.assertEqual(self._events("voz.comment"), [])

    def test_body_at_the_limit_still_appends(self):
        before = self._count()
        ok = "x" * self.server.MAX_BODY_BYTES
        r = self._post("/e/alpha-post/comment", {"body": ok}, local=True)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._count(), before + 1)


class TestCanonicalAppend(_Base):
    """Writes go through the canonical, locked tools/eventlog append (monotonic seq, idempotency
    key), never the hand-rolled scan-for-max-seq path. The idempotency key dedupes a double-click /
    retry: the SAME key twice appends ONCE."""

    AUTH = "test:mentee"  # authorized; isolate the append path from the gate

    def test_comment_appends_through_eventlog_with_monotonic_seq(self):
        before = self._count()
        r = self._post("/e/alpha-post/comment", {"body": "via canonical append"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._count(), before + 1)
        comments = self._events("voz.comment")
        self.assertEqual(len(comments), 1)
        # the canonical append continues the log's count (max seq was 4 → 5)
        self.assertEqual(comments[0]["seq"], 5)

    def test_duplicate_idempotency_key_appends_once(self):
        before = self._count()
        # same key twice (a double-click / retry) → exactly one append
        r1 = self._post("/e/alpha-post/comment",
                        {"body": "double click", "idem_key": "dup-key-123"})
        r2 = self._post("/e/alpha-post/comment",
                        {"body": "double click", "idem_key": "dup-key-123"})
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(self._count(), before + 1)  # ONE event, not two
        self.assertEqual(len(self._events("voz.comment")), 1)

    def test_distinct_idempotency_keys_both_append(self):
        before = self._count()
        self._post("/e/alpha-post/comment", {"body": "one", "idem_key": "k1"})
        self._post("/e/alpha-post/comment", {"body": "two", "idem_key": "k2"})
        self.assertEqual(self._count(), before + 2)

    def test_rendered_vote_form_carries_an_idempotency_key(self):
        """The live vote UI must take the idempotent path: the rendered form ships an idem_key, so
        a rapid double-submit of the SAME rendered button dedupes (no double-toggle back to 0)."""
        html = self.server._render_votes("alpha-post")
        self.assertIn('name="idem_key"', html)

    def test_double_submitting_the_same_vote_form_appends_once(self):
        before = self._count()
        # extract the key the form rendered, then submit it twice (a double-click on one button)
        import re
        html = self.server._render_votes("alpha-post")
        key = re.search(r'name="idem_key" value="([^"]+)"', html).group(1)
        self._post("/e/alpha-post/vote", {"value": "1", "idem_key": key})
        self._post("/e/alpha-post/vote", {"value": "1", "idem_key": key})
        self.assertEqual(self._count(), before + 1)  # one vote event, not a toggle-back-to-0
        self.assertEqual(self.server._vote_state("alpha-post"), 1)


class TestDnsRebindingDefense(_Base):
    """A DNS-rebinding page resolves an attacker hostname to 127.0.0.1, so the browser sends a
    matching Host AND Origin and the peer is loopback — every request.host-relative check passes.
    The origin must be validated against an ALLOWLISTED dashboard host, not the request's own Host
    (which the attacker controls). A loopback peer carrying an attacker Host/Origin → rejected."""

    AUTH = "on"

    def setUp(self):
        super().setUp()
        os.environ["EDGE_DASH_ORIGIN"] = "127.0.0.1:8780"  # the install's real dashboard host

    def tearDown(self):
        os.environ.pop("EDGE_DASH_ORIGIN", None)
        super().tearDown()

    def test_rebinding_host_and_origin_rejected_even_from_loopback(self):
        before = self._count()
        # the attacker's rebound name: loopback peer, but Host/Origin = attacker.example
        r = self.client.post(
            "/e/alpha-post/comment", data={"body": "rebinding poison"},
            base_url="http://attacker.example:8780",
            headers={"Origin": "http://attacker.example:8780"})
        self.assertIn(r.status_code, (401, 403))
        self.assertEqual(self._count(), before)
        self.assertEqual(self._events("voz.comment"), [])

    def test_allowlisted_origin_from_loopback_still_writes(self):
        before = self._count()
        r = self.client.post(
            "/e/alpha-post/comment", data={"body": "real operator"},
            base_url="http://127.0.0.1:8780",
            headers={"Origin": "http://127.0.0.1:8780"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._count(), before + 1)


class TestDefaultPortAllowlist(_Base):
    """The default allowlist (no EDGE_DASH_ORIGIN, no BLOG_PORT) must include the server's OWN
    default port — the one app.run binds — so the operator on the default URL is not rejected."""

    AUTH = "on"

    def setUp(self):
        super().setUp()
        os.environ.pop("EDGE_DASH_ORIGIN", None)
        os.environ.pop("BLOG_PORT", None)

    def test_operator_on_the_servers_default_port_can_write(self):
        # the port app.run() binds by default (the source of truth for "the default URL")
        port = self.server.DEFAULT_PORT
        before = self._count()
        r = self.client.post(
            "/e/alpha-post/comment", data={"body": "on the default port"},
            base_url=f"http://127.0.0.1:{port}",
            headers={"Origin": f"http://127.0.0.1:{port}"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._count(), before + 1)


class TestProxiedLoopbackNotAutoGranted(_Base):
    """Behind a reverse proxy (Caddy reverse_proxy localhost:<port>), Flask sees EVERY external
    client as a loopback peer. The loopback auto-grant must therefore NOT fire on a forwarded
    *public* host — only on a genuine loopback Host/Origin (the operator's own browser). A public
    host + loopback peer + no token → rejected (else any public visitor could write)."""

    AUTH = "on"

    def setUp(self):
        super().setUp()
        # the public host IS allowlisted (so a *tokened* proxied write can work), but that must not
        # by itself grant a tokenless request just because the proxy peer is loopback.
        os.environ["EDGE_DASH_ORIGIN"] = "edge.edgeofchaos.net,127.0.0.1:8766,localhost:8766"
        os.environ.pop("EDGE_DASH_TOKEN", None)

    def tearDown(self):
        os.environ.pop("EDGE_DASH_ORIGIN", None)
        super().tearDown()

    def test_public_host_via_proxy_without_token_is_rejected(self):
        before = self._count()
        # loopback peer (the proxy), but the forwarded Host/Origin is the public name, no token
        r = self.client.post(
            "/e/alpha-post/comment", data={"body": "public poison"},
            base_url="http://edge.edgeofchaos.net",
            headers={"Origin": "http://edge.edgeofchaos.net"})
        self.assertIn(r.status_code, (401, 403))
        self.assertEqual(self._count(), before)
        self.assertEqual(self._events("voz.comment"), [])

    def test_loopback_host_still_auto_granted_for_the_operator(self):
        before = self._count()
        # the operator's own browser: loopback Host AND Origin → still writes (UX preserved)
        r = self.client.post(
            "/e/alpha-post/comment", data={"body": "operator local"},
            base_url="http://127.0.0.1:8766",
            headers={"Origin": "http://127.0.0.1:8766"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._count(), before + 1)


class TestLegitimateMentee(_Base):
    """The gate must NOT break the operator: the local single-tenant mentee on 127.0.0.1, and a
    same-origin browser POST, both write normally. The gate is against spoofing, not the operator."""

    AUTH = "on"

    def test_local_operator_comment_appends_one_event(self):
        before = self._count()
        r = self._post("/e/alpha-post/comment", {"body": "operator directive"}, local=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("operator directive", r.data.decode())
        self.assertEqual(self._count(), before + 1)
        comments = self._events("voz.comment")
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["payload"]["body"], "operator directive")

    def test_same_origin_browser_post_is_authorized(self):
        before = self._count()
        # the operator's browser on the dashboard's own host → Origin matches → authorized
        r = self._post("/e/alpha-post/comment", {"body": "from the browser"},
                       local=True, origin="http://localhost")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._count(), before + 1)


class TestConfiguredToken(_Base):
    """A reverse-proxied principal authorizes with the configured EDGE_DASH_TOKEN (SURFACE.md:
    "session cookie OR reverse-proxy header"). Non-local peer + right token + same origin → write."""

    AUTH = "on"

    def setUp(self):
        super().setUp()
        os.environ["EDGE_DASH_TOKEN"] = "s3cr3t-proxy-token"

    def test_correct_token_from_remote_peer_is_authorized(self):
        before = self._count()
        r = self._post("/e/alpha-post/comment", {"body": "proxied directive"},
                       local=False, origin="http://localhost", token="s3cr3t-proxy-token")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._count(), before + 1)

    def test_wrong_token_is_rejected_with_no_append(self):
        before = self._count()
        r = self._post("/e/alpha-post/comment", {"body": "forged"},
                       local=False, origin="http://localhost", token="WRONG")
        self.assertIn(r.status_code, (401, 403))
        self.assertEqual(self._count(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
