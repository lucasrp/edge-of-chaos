"""Slice 4 — the Direction surface (`GET /direction`) + the Voz→Direction provenance link.

Direction is a projeção (SURFACE.md §"Direction"): a fold of `direction.*` via
`eventlog.direction_at` into TWO tiers — `set` (curated, Voz-only — the active steers, prominent)
and `proposed` (candidates awaiting the grill, dimmer; the same trust-language as the Cortex graph).

A `set` steer folded from a Directive carries `origin_comment_id` (the write-side the Slice-2 drain
appends). The surface renders that provenance BIDIRECTIONALLY (steer ⇄ originating comment), linking
to the comment's chat/post context. `proposed` carries `from_artefato`/`relates_to`, never
`origin_comment_id` — tier-disjoint provenance (ADR-0007 / SURFACE.md).

The LIVE acceptance (TestDirectionLiveRoundTrip) proves the end-to-end path DETERMINISTICALLY via a
stubbed reply-generator — ZERO API spend (the drain is pluggable; the fold-to-direction.set logic is
deterministic and needs no LLM). It does NOT run a live drain (that would spend the edge's OpenAI API).

Pinned on a throwaway temp log (CONTRACT C1 — never real state/).
"""
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _ev(seq, ts, type_, payload, subject="x"):
    return json.dumps({"seq": seq, "ts": ts, "type": type_, "subject": subject, "payload": payload})


class _DirectionBase(unittest.TestCase):
    """A hermetic blog server over a throwaway log. Auth is off (these are read-side tests; the
    live round-trip flips it per its own seam)."""

    LOG_LINES = []

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        entries = root / "entries"
        entries.mkdir()
        self.log = root / "log.jsonl"
        self.log.write_text("\n".join(self.LOG_LINES) + ("\n" if self.LOG_LINES else ""))
        os.environ["EDGE_BLOG_ENTRIES"] = str(entries)
        os.environ["EDGE_BLOG_STATIC"] = str(root)
        os.environ["EDGE_BLOG_LOG"] = str(self.log)
        os.environ["EDGE_DASH_AUTH"] = "off"
        sys.path.insert(0, str(REPO / "blog"))
        import server
        importlib.reload(server)
        self.server = server
        self.client = server.app.test_client()

    def tearDown(self):
        os.environ.pop("EDGE_DASH_AUTH", None)
        self.tmp.cleanup()


class TestDirectionRendersBothTiers(_DirectionBase):
    """The two tiers render: `set` (curated, prominent) and `proposed` (candidate, dimmer) — same
    trust-language as the Cortex graph (SURFACE.md §"Direction")."""

    LOG_LINES = [
        _ev(1, "2026-06-10T09:00:00+00:00", "direction.set",
            {"id": "d-set", "body": "always cite an outside benchmark", "kind": "constraint"}),
        _ev(2, "2026-06-10T09:00:01+00:00", "direction.proposed",
            {"id": "d-prop", "body": "explore the source-feedback tier", "kind": "thread",
             "from_artefato": "alpha-post"}),
    ]

    def test_is_full_html_page(self):
        body = self.client.get("/direction").data.decode()
        self.assertEqual(self.client.get("/direction").status_code, 200)
        self.assertIn("<!DOCTYPE html", body)
        self.assertIn("/static/style.css", body)

    def test_set_steer_renders_in_the_curated_tier(self):
        body = self.client.get("/direction").data.decode()
        self.assertIn("always cite an outside benchmark", body)
        # the curated tier is marked as such (a stable hook for the trust-language)
        self.assertIn('class="direction-tier set"', body)

    def test_proposed_steer_renders_in_the_candidate_tier(self):
        body = self.client.get("/direction").data.decode()
        self.assertIn("explore the source-feedback tier", body)
        self.assertIn('class="direction-tier proposed"', body)

    def test_set_is_prominent_proposed_is_dimmer(self):
        # the curated tier renders BEFORE the proposed tier (prominence by order) — the active steers
        # come first, the candidates awaiting the grill below.
        body = self.client.get("/direction").data.decode()
        self.assertLess(body.index('direction-tier set'), body.index('direction-tier proposed'))

    def test_proposed_shows_its_artefato_provenance(self):
        body = self.client.get("/direction").data.decode()
        self.assertIn("alpha-post", body)  # from_artefato provenance on the proposed tier


class TestDirectionProvenanceLink(_DirectionBase):
    """A `set` steer folded from a Directive carries `origin_comment_id` → the surface renders the
    bidirectional link (steer ⇄ originating comment), linking to the comment's chat/post context
    (SURFACE.md: 'renders the link bidirectionally')."""

    LOG_LINES = [
        # the originating Directive — a per-publication comment (target_ref = a slug)
        _ev(1, "2026-06-10T09:00:00+00:00", "artefato.published",
            {"slug": "alpha-post", "cites": [], "distills": [], "proposes": []}),
        _ev(2, "2026-06-10T09:00:01+00:00", "voz.comment",
            {"target_ref": "alpha-post", "comment_id": "c-origin", "body": "steer the framing"}),
        # the folded steer carrying the provenance back-reference
        _ev(3, "2026-06-10T09:00:02+00:00", "direction.set",
            {"id": "d-folded", "body": "frame every artefato as a steer test",
             "origin_comment_id": "c-origin"}),
        _ev(4, "2026-06-10T09:00:03+00:00", "voz.resolved",
            {"comment_id": "c-origin", "outcome": "folded-to-direction",
             "origin_comment_id": "c-origin", "direction_id": "d-folded"}),
    ]

    def test_set_steer_shows_its_originating_comment_link(self):
        body = self.client.get("/direction").data.decode()
        # the provenance is surfaced (the steer carries an origin) — a visible from-a-Directive marker
        self.assertIn("c-origin", body)
        self.assertIn('class="provenance', body)

    def test_provenance_links_to_a_surface_that_renders_the_comment(self):
        # FIX 3: even a targeted Directive drills into /chat#comment-{id} — the chat renders EVERY
        # comment, so the link lands on a surface that ACTUALLY shows the originating comment (the old
        # /e/{slug}.html pointed at the static post file, which renders no comment / no Voz rail). The
        # link targets a /chat#comment-... fragment that matches a rendered comment element.
        import re
        body = self.client.get("/direction").data.decode()
        m = re.search(r'href="/chat#(comment-[^"]+)"', body)
        self.assertIsNotNone(m, "steer→comment href must drill into /chat#comment-<id>")
        self.assertNotIn('href="/e/alpha-post.html" data-origin-comment', body)
        chat = self.client.get("/chat").data.decode()
        self.assertIn(f'id="{m.group(1)}"', chat)  # the chat renders the comment at that anchor

    def test_a_general_chat_directive_links_to_chat(self):
        # a steer folded from a general-chat Directive (target_ref None) links to /chat at the anchor
        # of the comment the chat renders.
        self.log.write_text("\n".join([
            _ev(1, "2026-06-10T09:00:00+00:00", "voz.comment",
                {"target_ref": None, "comment_id": "c-chat", "body": "a general steer"}),
            _ev(2, "2026-06-10T09:00:01+00:00", "direction.set",
                {"id": "d-chat", "body": "a folded general steer", "origin_comment_id": "c-chat"}),
        ]) + "\n")
        import re
        body = self.client.get("/direction").data.decode()
        m = re.search(r'href="/chat#(comment-[^"]+)"', body)
        self.assertIsNotNone(m)
        chat = self.client.get("/chat").data.decode()
        self.assertIn(f'id="{m.group(1)}"', chat)

    def test_a_non_voz_set_has_no_provenance_marker(self):
        # a direction.set with NO origin_comment_id (a grill-direct set) renders without the link
        self.log.write_text("\n".join([
            _ev(1, "2026-06-10T09:00:00+00:00", "direction.set",
                {"id": "d-plain", "body": "a plain grill steer"}),
        ]) + "\n")
        body = self.client.get("/direction").data.decode()
        self.assertIn("a plain grill steer", body)
        self.assertNotIn('class="provenance', body)


class TestSteerLinksToARenderedComment(_DirectionBase):
    """FIX 3: the steer→comment provenance link used to point at `/e/{target_ref}.html` — the STATIC
    artifact file, which renders the post body, NOT the Voz rail / the originating comment. The link
    must land on a surface that ACTUALLY renders that comment, at a stable per-comment anchor. `/chat`
    renders every comment (targeted or general), so the steer→comment href is `/chat#comment-{id}`,
    and the chat (and post threads) carry `id="comment-{comment_id}"` so the anchor centers it."""

    LOG_LINES = [
        _ev(1, "2026-06-10T09:00:00+00:00", "artefato.published",
            {"slug": "alpha-post", "cites": [], "distills": [], "proposes": []}),
        _ev(2, "2026-06-10T09:00:01+00:00", "voz.comment",
            {"target_ref": "alpha-post", "comment_id": "c-origin", "body": "steer the framing"}),
        _ev(3, "2026-06-10T09:00:02+00:00", "direction.set",
            {"id": "d-folded", "body": "frame every artefato as a steer test",
             "origin_comment_id": "c-origin"}),
        _ev(4, "2026-06-10T09:00:03+00:00", "voz.resolved",
            {"comment_id": "c-origin", "outcome": "folded-to-direction",
             "origin_comment_id": "c-origin", "direction_id": "d-folded"}),
    ]

    def test_steer_origin_href_targets_a_rendered_comment_anchor(self):
        import re
        direction = self.client.get("/direction").data.decode()
        # the provenance link drills into a comment anchor on a surface that renders the comment
        m = re.search(r'href="(/chat#comment-[^"]+)"', direction)
        self.assertIsNotNone(m, "steer→comment href must target /chat#comment-<id>")
        anchor = m.group(1).split("#", 1)[1]
        # the chat actually renders the comment carrying that exact element id
        chat = self.client.get("/chat").data.decode()
        self.assertIn(f'id="{anchor}"', chat)

    def test_steer_origin_href_is_not_the_static_artifact_file(self):
        # the dead link was /e/{target_ref}.html (the static file, no Voz rail) — it must be gone from
        # the provenance link (the steer's origin must reach a surface that renders the comment).
        direction = self.client.get("/direction").data.decode()
        self.assertNotIn('href="/e/alpha-post.html" data-origin-comment', direction)

    def test_post_thread_comment_carries_its_anchor(self):
        # the per-publication thread renders the comment too — it must carry a comment-<...> anchor id
        # so a reader landing from the steer can also find it in its post context. The id matches the
        # steer's provenance fragment (same _anchor_id helper both ends).
        import re
        direction = self.client.get("/direction").data.decode()
        anchor = re.search(r'href="/chat#(comment-[^"]+)"', direction).group(1)
        body = self.client.get("/").data.decode()
        self.assertIn(f'id="{anchor}"', body)

    def test_general_chat_directive_steer_links_to_chat_anchor(self):
        # a steer folded from a general-chat Directive (target_ref None) still links into /chat at the
        # comment anchor the chat renders — every comment is in the chat regardless of target.
        self.log.write_text("\n".join([
            _ev(1, "2026-06-10T09:00:00+00:00", "voz.comment",
                {"target_ref": None, "comment_id": "c-chat", "body": "a general steer"}),
            _ev(2, "2026-06-10T09:00:01+00:00", "direction.set",
                {"id": "d-chat", "body": "a folded general steer", "origin_comment_id": "c-chat"}),
        ]) + "\n")
        import re
        direction = self.client.get("/direction").data.decode()
        m = re.search(r'href="/chat#(comment-[^"]+)"', direction)
        self.assertIsNotNone(m)
        chat = self.client.get("/chat").data.decode()
        self.assertIn(f'id="{m.group(1)}"', chat)


class TestVozCommentLinksBackToItsSteer(_DirectionBase):
    """The OTHER half of the bidirectional link (SURFACE.md: 'renders the link bidirectionally,
    steer ⇄ originating comment'). The Direction surface links steer→comment; the Voz rail must link
    the originating comment→steer — so a Directive that landed shows, inline in the thread/chat, that
    it folded into a steer, drilling into /direction. 'Did my steer land?' is answerable from BOTH
    ends."""

    LOG_LINES = [
        _ev(1, "2026-06-10T09:00:00+00:00", "artefato.published",
            {"slug": "alpha-post", "cites": [], "distills": [], "proposes": []}),
        _ev(2, "2026-06-10T09:00:01+00:00", "voz.comment",
            {"target_ref": "alpha-post", "comment_id": "c-folded", "body": "steer the framing"}),
        _ev(3, "2026-06-10T09:00:02+00:00", "voz.reply",
            {"comment_id": "c-folded", "body": "folding this into a steer"}),
        _ev(4, "2026-06-10T09:00:03+00:00", "direction.set",
            {"id": "d-folded", "body": "always test the framing", "origin_comment_id": "c-folded"}),
        _ev(5, "2026-06-10T09:00:04+00:00", "voz.resolved",
            {"comment_id": "c-folded", "outcome": "folded-to-direction",
             "origin_comment_id": "c-folded", "direction_id": "d-folded"}),
    ]

    def test_chat_shows_a_folded_comment_links_to_direction(self):
        body = self.client.get("/chat").data.decode()
        # the comment that folded into a steer carries an inline marker linking to /direction
        self.assertIn('class="folded-marker', body)
        self.assertIn('href="/direction"', body)

    def test_post_thread_shows_a_folded_comment_links_to_direction(self):
        body = self.client.get("/").data.decode()
        self.assertIn('class="folded-marker', body)

    def test_a_plainly_replied_comment_has_no_folded_marker(self):
        # a comment resolved as a plain reply (not folded) shows NO steer link
        self.log.write_text("\n".join([
            _ev(1, "2026-06-10T09:00:00+00:00", "voz.comment",
                {"target_ref": None, "comment_id": "c-plain", "body": "a question"}),
            _ev(2, "2026-06-10T09:00:01+00:00", "voz.reply",
                {"comment_id": "c-plain", "body": "an answer"}),
            _ev(3, "2026-06-10T09:00:02+00:00", "voz.resolved",
                {"comment_id": "c-plain", "outcome": "replied"}),
        ]) + "\n")
        body = self.client.get("/chat").data.decode()
        self.assertNotIn('class="folded-marker', body)


class TestFoldedMarkerDrillsIntoTheSteer(_DirectionBase):
    """FIX 2: the comment→steer marker builds `/direction#steer-{direction_id}` (_folded_marker), but
    the set steer must carry a MATCHING element `id="steer-{id}"` or the anchor lands nowhere. The
    marker's href fragment and the steer element's id must agree (sanitized identically), so the
    drill-down centers the actual steer (SURFACE.md: 'renders the link bidirectionally')."""

    LOG_LINES = [
        _ev(1, "2026-06-10T09:00:00+00:00", "voz.comment",
            {"target_ref": None, "comment_id": "c-folded", "body": "steer the framing"}),
        _ev(2, "2026-06-10T09:00:01+00:00", "direction.set",
            {"id": "d-folded", "body": "always test the framing", "origin_comment_id": "c-folded"}),
        _ev(3, "2026-06-10T09:00:02+00:00", "voz.resolved",
            {"comment_id": "c-folded", "outcome": "folded-to-direction",
             "origin_comment_id": "c-folded", "direction_id": "d-folded"}),
    ]

    def test_set_steer_carries_a_stable_anchor_id(self):
        # the set steer renders a stable steer-<...> element id (the drill-down target). The exact
        # format is an implementation detail (sanitized + hashed for injectivity); what matters is a
        # `steer-` id is present and the marker (test below) drills into it.
        import re
        body = self.client.get("/direction").data.decode()
        self.assertRegex(body, r'<li class="steer" id="steer-[^"]+"')

    def test_marker_href_anchor_matches_a_rendered_steer_id(self):
        # the marker (rendered on the Voz rail) points at #steer-<sanitized id>; that exact id must
        # exist on /direction — extract the fragment from /chat's marker and assert the element exists.
        import re
        chat = self.client.get("/chat").data.decode()
        m = re.search(r'href="/direction#(steer-[^"]+)"', chat)
        self.assertIsNotNone(m, "the folded marker must carry a #steer-<id> anchor")
        anchor = m.group(1)
        direction = self.client.get("/direction").data.decode()
        self.assertIn(f'id="{anchor}"', direction)

    def test_anchor_id_is_sanitized_for_an_unsafe_direction_id(self):
        # a direction_id with whitespace / unsafe chars must sanitize IDENTICALLY on both ends so the
        # marker fragment and the element id still agree (no broken anchor, no malformed HTML id).
        self.log.write_text("\n".join([
            _ev(1, "2026-06-10T09:00:00+00:00", "voz.comment",
                {"target_ref": None, "comment_id": "c-x", "body": "a directive"}),
            _ev(2, "2026-06-10T09:00:01+00:00", "direction.set",
                {"id": "weird id/with spaces", "body": "a steer", "origin_comment_id": "c-x"}),
            _ev(3, "2026-06-10T09:00:02+00:00", "voz.resolved",
                {"comment_id": "c-x", "outcome": "folded-to-direction",
                 "origin_comment_id": "c-x", "direction_id": "weird id/with spaces"}),
        ]) + "\n")
        import re
        chat = self.client.get("/chat").data.decode()
        m = re.search(r'href="/direction#(steer-[^"]+)"', chat)
        self.assertIsNotNone(m)
        anchor = m.group(1)
        # the anchor carries no raw space (sanitized) and the steer element matches it exactly
        self.assertNotIn(" ", anchor)
        direction = self.client.get("/direction").data.decode()
        self.assertIn(f'id="{anchor}"', direction)


class TestSteerAnchorsAreInjective(_DirectionBase):
    """FIX 2 / codex round-5 [med]: a lossy sanitizer that collapses every non-[a-zA-Z0-9_-] run to a
    single `-` makes distinct ids (`a:b`, `a/b`, `a b`, `a-b`) share ONE fragment — so two folded
    steers collide and a comment marker drills into the wrong (or ambiguous) steer. The anchor must
    be INJECTIVE: distinct direction ids → distinct element ids, on BOTH the link and the target."""

    LOG_LINES = [
        _ev(1, "2026-06-10T09:00:00+00:00", "voz.comment",
            {"target_ref": None, "comment_id": "c-a", "body": "directive a"}),
        _ev(2, "2026-06-10T09:00:01+00:00", "voz.comment",
            {"target_ref": None, "comment_id": "c-b", "body": "directive b"}),
        # two distinct ids that a lossy collapse would map to the SAME fragment ("steer-a-b")
        _ev(3, "2026-06-10T09:00:02+00:00", "direction.set",
            {"id": "a:b", "body": "steer colon", "origin_comment_id": "c-a"}),
        _ev(4, "2026-06-10T09:00:03+00:00", "direction.set",
            {"id": "a/b", "body": "steer slash", "origin_comment_id": "c-b"}),
        _ev(5, "2026-06-10T09:00:04+00:00", "voz.resolved",
            {"comment_id": "c-a", "outcome": "folded-to-direction",
             "origin_comment_id": "c-a", "direction_id": "a:b"}),
        _ev(6, "2026-06-10T09:00:05+00:00", "voz.resolved",
            {"comment_id": "c-b", "outcome": "folded-to-direction",
             "origin_comment_id": "c-b", "direction_id": "a/b"}),
    ]

    def test_distinct_ids_get_distinct_steer_element_ids(self):
        import re
        body = self.client.get("/direction").data.decode()
        ids = re.findall(r'<li class="steer" id="(steer-[^"]+)"', body)
        self.assertEqual(len(ids), 2)
        self.assertEqual(len(set(ids)), 2, f"steer ids must be distinct (injective): {ids}")

    def test_each_marker_drills_into_the_right_steer(self):
        # the marker for comment c-a (folded into a:b) must anchor a DIFFERENT steer than c-b (a/b);
        # each marker's fragment must match exactly one rendered steer element id.
        import re
        chat = self.client.get("/chat").data.decode()
        markers = re.findall(r'href="/direction#(steer-[^"]+)"', chat)
        self.assertEqual(len(markers), 2)
        self.assertEqual(len(set(markers)), 2, f"markers must target distinct steers: {markers}")
        direction = self.client.get("/direction").data.decode()
        for anchor in markers:
            self.assertEqual(direction.count(f'id="{anchor}"'), 1,
                             f"{anchor} must match exactly one steer element")


class TestDirectionEmptyAndDark(_DirectionBase):
    """The empty case renders cleanly (no direction events at all) — a 200 with an honest empty
    marker, never a 500 or a blank."""

    LOG_LINES = []

    def test_empty_direction_renders_an_honest_marker(self):
        r = self.client.get("/direction")
        self.assertEqual(r.status_code, 200)
        self.assertIn("sem", r.data.decode().lower())  # "sem direção ainda" — empty marker


class TestDirectionSurvivesCorruptLog(_DirectionBase):
    """The shared nav routes the mentee across surfaces, so ONE corrupt log must not 500 /direction
    while the others degrade cleanly (Codex round-4 contract). `direction_at` folds via
    `eventlog.read`, which is NOT tolerant of a JSON-valid NON-dict line (`[]`, `42`) — it does
    `e["type"]` and TypeErrors. The route must fold tolerantly so /direction renders 200, the valid
    steer still shows, and the corrupt line is skipped (the health strip on /briefing flags it)."""

    LOG_LINES = [
        _ev(1, "2026-06-10T09:00:00+00:00", "direction.set", {"id": "d1", "body": "a real steer"}),
        "[]",   # a JSON-valid non-dict line — must be skipped, not crash the fold
        "42",
    ]

    def test_direction_renders_200_over_a_non_dict_line(self):
        r = self.client.get("/direction")
        self.assertEqual(r.status_code, 200)
        self.assertIn("a real steer", r.data.decode())  # the valid steer still renders

    def test_direction_renders_200_over_a_non_dict_payload(self):
        # a dict envelope with a corrupt (list) payload — fold_direction does .get on payload
        self.log.write_text("\n".join([
            _ev(1, "2026-06-10T09:00:00+00:00", "direction.set", {"id": "d1", "body": "a real steer"}),
            json.dumps({"seq": 2, "ts": "2026-06-10T09:00:01+00:00", "type": "direction.proposed",
                        "subject": "direction", "payload": []}),
        ]) + "\n")
        r = self.client.get("/direction")
        self.assertEqual(r.status_code, 200)
        self.assertIn("a real steer", r.data.decode())

    def test_direction_renders_200_over_a_list_valued_id(self):
        # a JSON-valid direction.set whose `id` is a LIST — fold_direction uses `id` as a dict KEY
        # (`items[iid] = ...`), and a list is unhashable → TypeError → 500. The corrupt steer is
        # SKIPPED (NOT coerced into an active steer — codex round-2 [high]: coercing it would promote
        # POISONED data onto the trusted curated tier); the valid one still shows.
        self.log.write_text("\n".join([
            _ev(1, "2026-06-10T09:00:00+00:00", "direction.set", {"id": "d1", "body": "a real steer"}),
            _ev(2, "2026-06-10T09:00:01+00:00", "direction.set",
                {"id": ["not", "a", "string"], "body": "a corrupt steer"}),
        ]) + "\n")
        r = self.client.get("/direction")
        self.assertEqual(r.status_code, 200)
        self.assertIn("a real steer", r.data.decode())
        # the corrupt-id steer must be ABSENT — never promoted to the curated tier (fail-dark, not
        # fail-poison). Its body never reaches the trusted surface.
        self.assertNotIn("a corrupt steer", r.data.decode())

    def test_direction_renders_200_over_a_list_valued_supersedes(self):
        # a direction.set whose `supersedes` is a LIST — fold_direction does `items.pop(sup, ...)`,
        # and pop with an unhashable key TypeErrors. A corrupt supersedes is IGNORED (never an
        # items.pop key), so it can't retire a real steer: d1 STAYS active alongside d2.
        self.log.write_text("\n".join([
            _ev(1, "2026-06-10T09:00:00+00:00", "direction.set", {"id": "d1", "body": "a real steer"}),
            _ev(2, "2026-06-10T09:00:01+00:00", "direction.set",
                {"id": "d2", "body": "another steer", "supersedes": ["d1"]}),
        ]) + "\n")
        r = self.client.get("/direction")
        self.assertEqual(r.status_code, 200)
        self.assertIn("another steer", r.data.decode())
        # a corrupt supersedes must NOT retire the real steer it (malformedly) names
        self.assertIn("a real steer", r.data.decode())

    def test_direction_renders_200_over_a_list_valued_origin_comment_id(self):
        # a direction.set whose `origin_comment_id` is a LIST — the provenance link builds an anchor
        # from it; the read boundary must coerce it so the surface renders inert (a 200), not 500.
        self.log.write_text("\n".join([
            _ev(1, "2026-06-10T09:00:00+00:00", "voz.comment",
                {"target_ref": None, "comment_id": "c1", "body": "a directive"}),
            _ev(2, "2026-06-10T09:00:01+00:00", "direction.set",
                {"id": "d1", "body": "a real steer", "origin_comment_id": ["c1"]}),
        ]) + "\n")
        r = self.client.get("/direction")
        self.assertEqual(r.status_code, 200)
        self.assertIn("a real steer", r.data.decode())

    def test_direction_renders_200_over_a_list_valued_direction_id_on_resolved(self):
        # a voz.resolved{folded-to-direction} whose `direction_id` is a LIST — the Voz rail's
        # _folded_directions maps comment_id → direction_id and the marker uses it as an anchor; the
        # comment→steer fold must not crash a surface that renders it.
        self.log.write_text("\n".join([
            _ev(1, "2026-06-10T09:00:00+00:00", "voz.comment",
                {"target_ref": None, "comment_id": "c1", "body": "a directive"}),
            _ev(2, "2026-06-10T09:00:01+00:00", "direction.set",
                {"id": "d1", "body": "a real steer", "origin_comment_id": "c1"}),
            _ev(3, "2026-06-10T09:00:02+00:00", "voz.resolved",
                {"comment_id": "c1", "outcome": "folded-to-direction",
                 "origin_comment_id": "c1", "direction_id": ["d1"]}),
        ]) + "\n")
        self.assertEqual(self.client.get("/direction").status_code, 200)
        self.assertEqual(self.client.get("/chat").status_code, 200)


class TestDirectionNav(_DirectionBase):
    """The shared nav (cross-cutting): Direction is added to the one bar, and /direction carries it.
    The drill-down off the Briefing links into /direction."""

    LOG_LINES = [
        _ev(1, "2026-06-10T09:00:00+00:00", "direction.set",
            {"id": "d1", "body": "a steer"}),
    ]

    def test_direction_carries_the_shared_nav(self):
        body = self.client.get("/direction").data.decode()
        self.assertIn('class="site-nav"', body)
        self.assertIn('href="/direction"', body)

    def test_nav_marks_direction_current(self):
        body = self.client.get("/direction").data.decode()
        self.assertIn('aria-current="page"', body)

    def test_direction_is_in_every_surfaces_nav(self):
        # the shared bar links Direction from the other read surfaces too (one app, not a pile)
        for path in ("/", "/chat"):
            self.assertIn('href="/direction"', self.client.get(path).data.decode())


class TestBriefingDrillsDownToDirection(_DirectionBase):
    """SURFACE.md / PLAN.md: Direction is a drill-down OFF the Briefing — a link from /briefing into
    /direction (status-scanning the steers, distinct from the Cortex constellation)."""

    LOG_LINES = [
        _ev(1, "2026-06-10T09:00:00+00:00", "objective.set", {"body": "ship the dashboard"}),
        _ev(2, "2026-06-10T09:00:01+00:00", "direction.set", {"id": "d1", "body": "a steer"}),
    ]

    def setUp(self):
        super().setUp()
        # the Briefing needs a throwaway genotype to compose; point it at one.
        import textwrap
        root = Path(self.tmp.name)
        memory = root / "memory"
        memory.mkdir(exist_ok=True)
        (memory / "personality.md").write_text("# Personality\n\nSkeptical.")
        (memory / "method.md").write_text("# Method\n\nDerive first.")
        (root / "state").mkdir(exist_ok=True)
        (root / "state" / "idiom.md").write_text("# Idiom\n\n**beat** — the cycle.")
        agent_yaml = root / "agent.yaml"
        agent_yaml.write_text(textwrap.dedent("""\
            name: ed
            mission: "Mentor."
            voice: "Direct."
            sources:
              - name: exa
                kind: api
                description: "search."
            """))
        os.environ["EDGE_BRIEFING_AGENT_YAML"] = str(agent_yaml)
        os.environ["EDGE_BRIEFING_MEMORY"] = str(memory)

    def tearDown(self):
        for k in ("EDGE_BRIEFING_AGENT_YAML", "EDGE_BRIEFING_MEMORY"):
            os.environ.pop(k, None)
        super().tearDown()

    def test_briefing_has_a_drill_down_into_direction(self):
        body = self.client.get("/briefing").data.decode()
        self.assertIn('href="/direction"', body)


class TestDirectionLiveRoundTrip(_DirectionBase):
    """The LIVE acceptance (NOT seeded) with ZERO API spend: post a REAL standing Directive in /chat,
    run the S2 drain with a STUBBED reply-generator (the fold-to-direction.set logic is deterministic,
    no LLM), then assert /direction shows the NEW `set` steer linked back to its originating comment
    (origin_comment_id), with voz.resolved{folded-to-direction} on the log, both tiers rendering.

    'Did my steer land?' is answerable END-TO-END for a NEW directive — proven via the stub, NOT from
    seeded data, NOT a live drain (which would spend the edge's OpenAI API)."""

    # one seed publication (so a per-publication round-trip is also possible) + one proposed steer so
    # BOTH tiers are non-empty after the fold.
    LOG_LINES = [
        _ev(1, "2026-06-10T09:00:00+00:00", "artefato.published",
            {"slug": "alpha-post", "cites": [], "distills": [], "proposes": []}),
        _ev(2, "2026-06-10T09:00:01+00:00", "intent.kernel",
            {"slug": "alpha-post", "intent": "open: alpha."}),
        _ev(3, "2026-06-10T09:00:02+00:00", "direction.proposed",
            {"id": "p1", "body": "a candidate awaiting the grill", "kind": "thread",
             "from_artefato": "alpha-post"}),
    ]

    @staticmethod
    def _directive_stub():
        """The pluggable reply-generator, STUBBED — classifies the Directive as standing so the drain
        folds it to direction.set. NO LLM call (a live one would spend the edge's OpenAI API)."""
        def gen(comment):
            return {"reply": "folding this into a curated steer",
                    "directive": True, "direction_body": "standing: " + comment["body"]}
        return gen

    def test_a_new_directive_lands_as_a_set_steer_linked_to_its_comment(self):
        import grill_drain

        # 1. /direction does NOT yet show the steer (it does not exist — this is NOT seeded).
        before = self.client.get("/direction").data.decode()
        self.assertNotIn("ratify the benchmark rule", before)

        # 2. post a REAL standing Directive through the /chat write route (the live write path).
        r = self.client.post("/chat/comment", data={"body": "ratify the benchmark rule"})
        self.assertEqual(r.status_code, 200)
        comments = [json.loads(l) for l in self.log.read_text().splitlines()
                    if l.strip() and json.loads(l).get("type") == "voz.comment"]
        self.assertEqual(len(comments), 1)
        cid = comments[0]["payload"]["comment_id"]

        # 3. run the S2 drain with the STUBBED reply-generator — zero API spend.
        self.drain_loaded = grill_drain.drain(self.log, self._directive_stub(), grill_run_id="g1")
        self.assertIn(cid, [c["comment_id"] for c in self.drain_loaded])

        # 4. the write-side landed atomically: direction.set{origin_comment_id} +
        #    voz.resolved{folded-to-direction} on the log (the loop the surface reads).
        events = [json.loads(l) for l in self.log.read_text().splitlines() if l.strip()]
        sets = [e for e in events if e["type"] == "direction.set"
                and e["payload"].get("origin_comment_id") == cid]
        self.assertEqual(len(sets), 1)
        direction_id = sets[0]["payload"]["id"]
        resolved = [e for e in events if e["type"] == "voz.resolved"
                    and e["payload"]["comment_id"] == cid]
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["payload"]["outcome"], "folded-to-direction")
        self.assertEqual(resolved[0]["payload"]["direction_id"], direction_id)
        # the loop is internally consistent (no dangling/missing-provenance error).
        self.assertEqual(grill_drain.consistency_errors(self.log), [])

        # 5. /direction now shows the NEW set steer, LINKED back to its originating comment.
        after = self.client.get("/direction").data.decode()
        self.assertIn("ratify the benchmark rule", after)        # the steer body
        self.assertIn('class="direction-tier set"', after)        # in the curated tier
        self.assertIn('class="provenance', after)                # carrying the provenance link
        self.assertIn(cid, after)                                  # to its origin comment_id
        self.assertIn('href="/chat"', after)                       # the general-chat context

        # 6. BOTH tiers render — the proposed candidate is still there, dimmer.
        self.assertIn('class="direction-tier proposed"', after)
        self.assertIn("a candidate awaiting the grill", after)


if __name__ == "__main__":
    unittest.main()
