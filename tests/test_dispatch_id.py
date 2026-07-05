"""S2 (grounding iteration) — dispatch_id: identidade real + cadeia proof-bound (E1/E1b/E1c).

E1: the dispatch_id is IDENTITY, never reconstructed — minted at predispatch, EXPOSED
machine-readable (`DISPATCH_ID=<id>` on main()'s stdout: the live path is CLI → skill-snippet
across processes, an in-process return does not cross), stamped into `dispatch.open` with the
SESSION ANCHOR (session_id + the event's own seq as the monotonic anchor), and carried
explicitly to close/publish. Two concurrent dispatches each publish under their OWN id —
"the last dispatch.open before the publish" is forbidden as a join key.

E1b: dispatch_id is PROOF-BOUND, same class as slug — persisted field = digested field. It
enters proof_digest/_mint_proof/verify_proof and publisher.publish, so a publish_fn cannot
publish with ANOTHER dispatch_id without a digest mismatch.

E1c: REQUIRED on the canonical log (loud ValueError, nothing written); tests/custom logs
inject a synthetic id via the test-only helper `eventlog.test_dispatch_id()`; the legacy
`eventlog.publish_artefato` is declared migration/test-only.
"""
import ast
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import close        # noqa: E402
import eventlog     # noqa: E402
import predispatch  # noqa: E402
import publisher    # noqa: E402


def _no_session_env():
    """An env WITHOUT the session anchor var — so the null-session case is deterministic."""
    return {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_SESSION_ID"}


class PredispatchMintsTheDispatchId(unittest.TestCase):
    """E1 — the id is minted at the entry-driver: unique, sortable (ULID-equivalent:
    ms-timestamp prefix + random suffix; no ULID helper exists in the repo and no new deps)."""

    def test_mint_is_a_unique_nonempty_string(self):
        ids = {predispatch.mint_dispatch_id() for _ in range(200)}
        self.assertEqual(len(ids), 200, "concurrent mints must never collide")
        for did in ids:
            self.assertIsInstance(did, str)
            self.assertTrue(did.strip())


class DispatchOpenCarriesIdentityAndSessionAnchor(unittest.TestCase):
    """E1 + S2 contract — dispatch.open carries dispatch_id, the session anchor (session_id
    from CLAUDE_CODE_SESSION_ID, else null; the event's OWN seq is the monotonic anchor) and
    the optional declared fields (theme/intent/geometry, tier `declared`)."""

    def _run(self, log, **kw):
        return predispatch.run(sweep_fn=lambda: 1, briefing_fn=lambda: "B",
                               recall_fn=lambda: "R", harvest_fn=lambda: 0, log=log, **kw)

    def test_stamp_carries_dispatch_id_session_and_declared_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "sess-abc"}):
                self._run(log, dispatch_id="d-explicit", theme="grounding",
                          intent="close the join")
            ev = eventlog.read(types=["dispatch.open"], log=log)[0]
            p = ev["payload"]
            self.assertEqual(p["dispatch_id"], "d-explicit")
            self.assertEqual(p["session_id"], "sess-abc")
            self.assertEqual(p["theme"], "grounding")
            self.assertEqual(p["intent"], "close the join")
            # the monotonic anchor is the event's OWN seq (stamped by append) — S4's harvest
            # maps rows by (session anchor, dispatch interval), so it must be there and ordered
            self.assertIsInstance(ev["seq"], int)
            self.assertEqual(p["swept_sessions"], 1, "the sweep yield still rides the stamp")

    def test_session_id_is_null_when_the_env_var_is_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with mock.patch.dict(os.environ, _no_session_env(), clear=True):
                self._run(log, dispatch_id="d-1")
            p = eventlog.read(types=["dispatch.open"], log=log)[0]["payload"]
            self.assertIsNone(p["session_id"], "no env anchor → null, never fabricated")

    def test_geometry_defaults_ambient_and_flips_themed_on_a_declared_theme(self):
        # predispatch cannot see its caller (the live path is a separate CLI process), so
        # geometry is DECLARED: default ambient (the heartbeat entry), themed when a theme is
        # declared, and an explicit geometry always wins.
        cases = [
            ({}, "ambient"),
            ({"theme": "x"}, "themed"),
            ({"theme": "x", "geometry": "ambient"}, "ambient"),
            ({"geometry": "themed"}, "themed"),
        ]
        for kw, want in cases:
            with tempfile.TemporaryDirectory() as tmp:
                log = Path(tmp) / "log.jsonl"
                self._run(log, dispatch_id="d-g", **kw)
                p = eventlog.read(types=["dispatch.open"], log=log)[0]["payload"]
                self.assertEqual(p["geometry"], want, f"{kw} → geometry {want!r}")

    def test_run_auto_mints_when_no_id_is_handed_in(self):
        # a direct run() (tests, in-process callers) still stamps a real identity — the id is
        # never optional on the stamp itself
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            self._run(log)
            p = eventlog.read(types=["dispatch.open"], log=log)[0]["payload"]
            self.assertIsInstance(p["dispatch_id"], str)
            self.assertTrue(p["dispatch_id"].strip())


class MainPrintsTheMachineReadableLine(unittest.TestCase):
    """S2 — the live path is CLI → skill-snippet in separate processes: an in-process return
    does not cross, so main() prints `DISPATCH_ID=<id>` machine-readable on stdout and the
    printed id is EXACTLY the one run() stamps (one mint, one identity)."""

    def test_main_prints_dispatch_id_line_matching_the_stamped_id(self):
        seen = {}

        def fake_run(**kw):
            seen.update(kw)
            # #62: the id is written by run() to the id_sink main() hands it, not by main()
            if kw.get("id_sink") is not None:
                kw["id_sink"].write(f"DISPATCH_ID={kw['dispatch_id']}\n")
                kw["id_sink"].flush()
            return "BRIEFING", "RECALL"

        buf = io.StringIO()
        with mock.patch.object(predispatch, "run", fake_run), redirect_stdout(buf):
            predispatch.main([])
        lines = buf.getvalue().splitlines()
        did_lines = [l for l in lines if l.startswith("DISPATCH_ID=")]
        self.assertEqual(len(did_lines), 1, "exactly ONE machine-readable DISPATCH_ID line")
        printed = did_lines[0].split("=", 1)[1]
        self.assertTrue(printed.strip())
        self.assertEqual(printed, seen.get("dispatch_id"),
                         "the printed id must be the SAME identity run() stamps — "
                         "one mint per dispatch (E1)")

    def test_main_passes_the_declared_flags_through(self):
        seen = {}

        def fake_run(**kw):
            seen.update(kw)
            return "B", "R"

        with mock.patch.object(predispatch, "run", fake_run), redirect_stdout(io.StringIO()):
            predispatch.main(["--theme", "grounding", "--intent", "why", "--geometry", "themed"])
        self.assertEqual(seen.get("theme"), "grounding")
        self.assertEqual(seen.get("intent"), "why")
        self.assertEqual(seen.get("geometry"), "themed")

    def test_dispatch_id_line_is_first_even_when_the_floor_is_noisy(self):
        # codex S2 gate D2: the real sweep prints degraded warnings — a snippet grepping
        # "first line" must still find DISPATCH_ID= first; the noise is preserved AFTER it.
        def noisy_run(**kw):
            # #62: run() writes the id to the id_sink FIRST, then the floor legs print their noise
            if kw.get("id_sink") is not None:
                kw["id_sink"].write(f"DISPATCH_ID={kw['dispatch_id']}\n")
                kw["id_sink"].flush()
            print("sweep: transcript store degraded — continuing dark")
            print("recall: graph unreachable")
            return "BRIEFING", "RECALL"

        buf = io.StringIO()
        with mock.patch.object(predispatch, "run", noisy_run), redirect_stdout(buf):
            predispatch.main([])
        lines = [l for l in buf.getvalue().splitlines() if l.strip()]
        self.assertTrue(lines[0].startswith("DISPATCH_ID="),
                        f"the machine-readable line must be FIRST, got {lines[0]!r}")
        self.assertIn("sweep: transcript store degraded — continuing dark", lines,
                      "the floor's warnings must be preserved, never swallowed")

    def test_no_dispatch_id_line_when_the_floor_fails_before_the_stamp(self):
        # a dispatch that could not wake must not LOOK woken (ADR-0016): a raising run() means
        # no stamp — so no DISPATCH_ID line either; the captured noise still surfaces.
        def failing_run(**kw):
            print("sweep: about to fail loud")
            raise RuntimeError("transcript store not found")

        buf = io.StringIO()
        with mock.patch.object(predispatch, "run", failing_run), redirect_stdout(buf):
            with self.assertRaises(RuntimeError):
                predispatch.main([])
        out = buf.getvalue()
        self.assertNotIn("DISPATCH_ID=", out,
                         "no stamp → no machine-readable id (a failed wake must not look woken)")
        self.assertIn("sweep: about to fail loud", out,
                      "the failing floor's output must still surface for diagnosis")


def _conformant_artefato(slug="bound-artefato", dispatch_id=None):
    """A genus-conformant artefato (mirrors tests/test_close_loop.py) — optionally carrying
    the proof-bound dispatch_id (E1b)."""
    art = {
        "slug": slug,
        "content": {"sections": [{"title": "Body", "blocks": [
            {"type": "paragraph", "text": "the proof is bound to this exact payload."},
        ]}]},
        "cites": [{"ref": "github:abc", "kind": "atividade", "relevant": True,
                   "snippet": "the cursor became a watermark"}],
        "proposes": [{"body": "name the budget", "kind": "constraint"}],
        "intent": "open: x; bet: y",
    }
    if dispatch_id is not None:
        art["dispatch_id"] = dispatch_id
    return art


def _mint(art):
    """Mint through the REAL close (canonical reviewers, offline completer) — the proof
    binds whatever the artefato dict carries, dispatch_id included."""
    return close.run_close(
        art, produce_fn=lambda: art,
        reviewers=(close.feynman_review, close.regular_review),
        complete_fn=lambda *a, **k: '{"pass": true, "scores": {}, "strikes": []}',
    )


class ProofChainBindsDispatchId(unittest.TestCase):
    """E1b — dispatch_id is PROOF-BOUND, same class as slug: persisted field = digested field.
    Outside the digest, a publish_fn could publish under ANOTHER dispatch_id with no mismatch,
    corrupting the yield join without violating the proof."""

    def test_digest_changes_when_dispatch_id_changes(self):
        base = dict(slug="s", spec={"x": 1}, intent="i", cites=[], proposes=[])
        a = close.proof_digest(dispatch_id="d-A", **base)
        b = close.proof_digest(dispatch_id="d-B", **base)
        same = close.proof_digest(dispatch_id="d-A", **base)
        self.assertNotEqual(a, b, "a different dispatch_id must yield a different digest")
        self.assertEqual(a, same, "the digest is deterministic for the same payload")

    def test_verify_rejects_a_proof_minted_under_a_different_dispatch_id(self):
        art = _conformant_artefato(dispatch_id="d-A")
        proof = _mint(art)
        self.assertTrue(proof["pass"])
        # binds to the id it was minted over…
        close.verify_proof(
            proof, slug=art["slug"], spec=art["content"], intent=art["intent"],
            cites=art["cites"], proposes=art["proposes"],
            dispatch_id="d-A", reviewer_count=2)
        # …and a publish attempted under ANOTHER dispatch_id is a digest mismatch.
        with self.assertRaises(ValueError):
            close.verify_proof(
                proof, slug=art["slug"], spec=art["content"], intent=art["intent"],
                cites=art["cites"], proposes=art["proposes"],
                dispatch_id="d-B", reviewer_count=2)

    def test_legacy_no_dispatch_id_payloads_still_verify(self):
        # byte-compat: an artefato with no dispatch_id digests as None on both sides — the
        # existing close suite stays green; the REQUIREMENT lives at the canonical log (E1c).
        art = _conformant_artefato()
        proof = _mint(art)
        close.verify_proof(
            proof, slug=art["slug"], spec=art["content"], intent=art["intent"],
            cites=art["cites"], proposes=art["proposes"], reviewer_count=2)


class CanonicalLogRequiresDispatchId(unittest.TestCase):
    """E1c — the compatibility contract: dispatch_id is OBRIGATÓRIO on the canonical log
    (opcional-em-produção reabriria o join sem identidade); tests/custom logs inject a
    synthetic id via the test-only helper."""

    def test_canonical_publish_without_dispatch_id_fails_loud_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with mock.patch.object(eventlog, "LOG", log):
                for absent in (None, "", "   "):
                    with self.assertRaises(ValueError) as ctx:
                        eventlog.publish_artefato_atomic(
                            "a-slug", "open: x; bet: y", log=log, dispatch_id=absent)
                    self.assertIn("dispatch_id", str(ctx.exception))
                self.assertEqual(eventlog.read(log=log), [],
                                 "a refused canonical publish must write NOTHING")

    def test_canonical_publish_with_a_dispatch_id_lands_it_on_the_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            did = eventlog.test_dispatch_id()
            with mock.patch.object(eventlog, "LOG", log):
                eventlog.publish_artefato_atomic(
                    "a-slug", "open: x; bet: y", log=log, dispatch_id=did)
            p = eventlog.read(types=["artefato.published"], log=log)[0]["payload"]
            self.assertEqual(p["dispatch_id"], did)

    def test_custom_log_tolerates_an_absent_id_and_records_null(self):
        # tests/dry-runs over a NON-canonical log stay callable without an id — the payload
        # records null honestly (the S7 join will count it, never fabricate an identity)
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.publish_artefato_atomic("a-slug", "open: x; bet: y", log=log)
            p = eventlog.read(types=["artefato.published"], log=log)[0]["payload"]
            self.assertIsNone(p["dispatch_id"])

    def test_test_only_helper_mints_a_marked_synthetic_id(self):
        a, b = eventlog.test_dispatch_id(), eventlog.test_dispatch_id()
        self.assertNotEqual(a, b)
        for did in (a, b):
            self.assertTrue(did.startswith("test-"),
                            "a synthetic id must be VISIBLY synthetic — never mistakable "
                            "for a predispatch-minted identity in a real join")


class ConcurrentDispatchesKeepTheirOwnIds(unittest.TestCase):
    """E1 concurrency — two dispatches open on the same log; each publish consumes ITS OWN
    id (carried explicitly), never "the last dispatch.open before the publish". Gated
    (require_wake=True, codex S2 gate D1): under the OLD global wake_fresh the second
    publish would lose regardless of stamp order — the identity-held gate admits both."""

    def test_each_publish_carries_its_own_dispatch_id_no_cross_talk(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            # dispatch A opens, then dispatch B opens (B is the LAST open on the log)
            eventlog.dispatch_open({"dispatch_id": "d-A"}, log=log)
            eventlog.dispatch_open({"dispatch_id": "d-B"}, log=log)
            # A publishes FIRST — under a "last open" reconstruction it would steal d-B,
            # and under the global gate B's publish would then fail as no-wake
            eventlog.publish_artefato_atomic(
                "artefato-of-a", "open: a; bet: a", log=log, dispatch_id="d-A",
                require_wake=True)
            eventlog.publish_artefato_atomic(
                "artefato-of-b", "open: b; bet: b", log=log, dispatch_id="d-B",
                require_wake=True)
            by_slug = {e["payload"]["slug"]: e["payload"]["dispatch_id"]
                       for e in eventlog.read(types=["artefato.published"], log=log)}
            self.assertEqual(by_slug, {"artefato-of-a": "d-A", "artefato-of-b": "d-B"},
                             "each publish must carry the id it was handed — the join key "
                             "is identity, never inference (E1)")


class IdentityHeldWakeGate(unittest.TestCase):
    """codex S2 gate D1 — the wake gate is IDENTITY-HELD, not global (E1: "consumed under the
    same lock"): `wake_fresh_for(dispatch_id)` requires a dispatch.open that MINTED this id and
    no artefato.published that consumed it. Global max-seq comparison would let concurrent
    dispatches spend each other's stamps AND let a publish ride an id no wake ever minted
    (proof-bound ≠ provenance)."""

    def test_two_opens_publish_in_either_order_both_pass(self):
        for order in (("d-A", "d-B"), ("d-B", "d-A")):
            with tempfile.TemporaryDirectory() as tmp:
                log = Path(tmp) / "log.jsonl"
                eventlog.dispatch_open({"dispatch_id": "d-A"}, log=log)
                eventlog.dispatch_open({"dispatch_id": "d-B"}, log=log)
                for i, did in enumerate(order):
                    eventlog.publish_artefato_atomic(
                        f"artefato-{i}-{did}", "open: x; bet: y", log=log,
                        dispatch_id=did, require_wake=True)
                slugs = [e["payload"]["slug"] for e in
                         eventlog.read(types=["artefato.published"], log=log)]
                self.assertEqual(len(slugs), 2,
                                 f"order {order}: both dispatches must publish — neither "
                                 "steals the other's stamp (E1)")

    def test_publish_under_an_id_no_wake_ever_minted_fails_no_wake(self):
        # proof-bound ≠ provenance: an id that never appeared in a dispatch.open is not a
        # wake — the gate must refuse it even though another dispatch is open
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.dispatch_open({"dispatch_id": "d-A"}, log=log)
            with self.assertRaises(RuntimeError) as ctx:
                eventlog.publish_artefato_atomic(
                    "phantom", "open: x; bet: y", log=log,
                    dispatch_id="d-C", require_wake=True)
            self.assertIn("no-wake", str(ctx.exception))
            self.assertIn("d-C", str(ctx.exception), "the refusal names the phantom id")
            self.assertEqual(eventlog.read(types=["artefato.published"], log=log), [],
                             "a refused publish must write NOTHING")

    def test_duplicate_publish_of_the_same_id_fails(self):
        # one wake, one publish — an id is CONSUMED by the publish that carries it
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.dispatch_open({"dispatch_id": "d-A"}, log=log)
            eventlog.publish_artefato_atomic(
                "first", "open: x; bet: y", log=log, dispatch_id="d-A", require_wake=True)
            with self.assertRaises(RuntimeError) as ctx:
                eventlog.publish_artefato_atomic(
                    "second", "open: x; bet: y", log=log, dispatch_id="d-A",
                    require_wake=True)
            self.assertIn("no-wake", str(ctx.exception))
            slugs = [e["payload"]["slug"] for e in
                     eventlog.read(types=["artefato.published"], log=log)]
            self.assertEqual(slugs, ["first"])

    def test_wake_fresh_for_fold(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            self.assertFalse(eventlog.wake_fresh_for("d-A", log=log), "no open → not fresh")
            eventlog.dispatch_open({"dispatch_id": "d-A"}, log=log)
            self.assertTrue(eventlog.wake_fresh_for("d-A", log=log))
            self.assertFalse(eventlog.wake_fresh_for("d-B", log=log),
                             "another dispatch's open is not THIS id's wake")
            eventlog.publish_artefato_atomic(
                "consumer", "open: x; bet: y", log=log, dispatch_id="d-A")
            self.assertFalse(eventlog.wake_fresh_for("d-A", log=log),
                             "a publish under the id consumes it")
            for hollow in (None, "", "   ", 7):
                self.assertFalse(eventlog.wake_fresh_for(hollow, log=log),
                                 f"a hollow id ({hollow!r}) can never be fresh")


class PublisherCarriesTheProofBoundDispatchId(unittest.TestCase):
    """E1b at the publish seam — publisher.publish gains dispatch_id: verified against the
    proof digest (the proof-bound artefato's value) and passed through to the event payload."""

    def _publish(self, tmp, dispatch_id, proof_dispatch_id):
        log = Path(tmp) / "log.jsonl"
        slug = "dispatch-bound"
        spec = {"sections": [{"title": "Body", "blocks": [
            {"type": "paragraph", "text": "the id rides the proof and the event."}]}]}
        intent = "open: x; bet: y"
        cites = [{"ref": "github:abc", "kind": "atividade", "relevant": True,
                  "snippet": "the cursor became a watermark"}]
        verdicts = [
            {"pass": True, "scores": {}, "strikes": [], "overall": 4.0,
             "reviewer": close.FEYNMAN_REVIEWER_ID},
            {"pass": True, "scores": {}, "strikes": [], "overall": 4.0,
             "reviewer": close.REGULAR_REVIEWER_ID},
        ]
        proof = close._mint_proof(verdicts, slug=slug, spec=spec, intent=intent,
                                  cites=cites, proposes=[], skill="report",
                                  dispatch_id=proof_dispatch_id)
        eventlog.dispatch_open({"dispatch_id": dispatch_id}, log=log)
        publisher.publish(slug, spec, intent, skill="report", verdict=proof,
                          cites=cites, date="2026-07-01", log=log,
                          blog_dir=Path(tmp) / "blog", dispatch_id=dispatch_id)
        return log

    def test_publish_lands_the_dispatch_id_on_the_published_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = self._publish(tmp, dispatch_id="d-77", proof_dispatch_id="d-77")
            p = eventlog.read(types=["artefato.published"], log=log)[0]["payload"]
            self.assertEqual(p["dispatch_id"], "d-77")

    def test_publish_under_an_id_the_proof_was_not_minted_over_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                self._publish(tmp, dispatch_id="d-88", proof_dispatch_id="d-77")
            self.assertEqual(
                eventlog.read(types=["artefato.published"], log=Path(tmp) / "log.jsonl"), [],
                "a digest-mismatched publish must write nothing (E1b)")

    def test_publish_under_an_unminted_id_fails_no_wake_at_the_seam(self):
        # codex S2 gate D1 at the publisher fast-fail: an id-carrying publish gates on the
        # IDENTITY-HELD check — an open that minted a DIFFERENT id (or none) is not this
        # dispatch's wake, even with a perfectly bound proof.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            slug, spec, intent = "phantom-id", {"sections": [{"title": "B", "blocks": [
                {"type": "paragraph", "text": "x"}]}]}, "open: x; bet: y"
            verdicts = [
                {"pass": True, "scores": {}, "strikes": [], "overall": 4.0,
                 "reviewer": close.FEYNMAN_REVIEWER_ID},
                {"pass": True, "scores": {}, "strikes": [], "overall": 4.0,
                 "reviewer": close.REGULAR_REVIEWER_ID},
            ]
            proof = close._mint_proof(verdicts, slug=slug, spec=spec, intent=intent,
                                      cites=[], proposes=[], skill="report",
                                      dispatch_id="d-X")
            eventlog.dispatch_open(log=log)  # an id-LESS open — not d-X's wake
            with self.assertRaises(RuntimeError) as ctx:
                publisher.publish(slug, spec, intent, skill="report", verdict=proof,
                                  date="2026-07-01", log=log, blog_dir=Path(tmp) / "blog",
                                  dispatch_id="d-X")
            self.assertIn("no-wake", str(ctx.exception))


class LegacyPublishArtefatoIsDeclaredMigrationOnly(unittest.TestCase):
    """E1c — the legacy wrapper is declared migration/test-only in its docstring (its only
    call-sites are tests; the production path is publisher → publish_artefato_atomic)."""

    def test_docstring_declares_migration_test_only(self):
        doc = (eventlog.publish_artefato.__doc__ or "").lower()
        self.assertTrue("migration" in doc and "test" in doc,
                        "publish_artefato must declare itself migration/test-only (E1c)")


class ProducerSnippetsCarryTheDispatchId(unittest.TestCase):
    """E1b — the publish snippets producers actually run: the artefato dict carries
    'dispatch_id' (read from the wake's DISPATCH_ID line) and the publish_fn passes
    dispatch_id=art['dispatch_id']. Covers the whole roster that publishes via a snippet."""

    SNIPPET_PRODUCERS = ("report", "research", "map", "plan", "discovery", "grill")

    def test_every_snippet_binds_and_passes_the_dispatch_id(self):
        for p in self.SNIPPET_PRODUCERS:
            text = (REPO / "skills" / p / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("'dispatch_id'", text,
                          f"{p}'s artefato dict does not carry the proof-bound dispatch_id")
            self.assertIn("art['dispatch_id']", text,
                          f"{p}'s publish_fn does not pass dispatch_id from the minted art")
            self.assertIn("DISPATCH_ID", text,
                          f"{p} never tells the producer where the id comes from "
                          "(the wake's machine-readable DISPATCH_ID line)")

    def test_snippet_dispatch_id_literal_is_valid_python(self):
        # codex S2 gate D3: an apostrophe inside the placeholder ("the wake's …") CLOSES the
        # single-quoted literal and SyntaxErrors the whole edge-python -c command. Compile the
        # dispatch_id assignment with ast.parse so the snippet the producer copy-runs can never
        # ship a broken literal. (Grill inlines no `dispatch_id='…'` assignment — its snippet
        # reads the field off `art` only.)
        for p in self.SNIPPET_PRODUCERS:
            text = (REPO / "skills" / p / "SKILL.md").read_text(encoding="utf-8")
            for line in text.splitlines():
                if "dispatch_id='" not in line:
                    continue
                stmt = line.strip().rstrip("\\").strip().rstrip(";")
                try:
                    ast.parse(stmt)
                except SyntaxError as e:
                    self.fail(f"{p}'s snippet dispatch_id line is not valid python "
                              f"({e.msg}): {stmt!r} — an apostrophe in the placeholder "
                              "breaks the -c command (gate D3)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
