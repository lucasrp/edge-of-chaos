"""The bounce loop + the loop-2 brake (Close architecture, S8, ADR-0012/0013).

The close's gate is BOUNDED IN THE PROTOCOL, not in the producer's discretion — that
bound is what separates a gate from the retry-envelope ADR-0003 killed. Two module
constants pin it: `BOUNCE_MAX` (reviewer→producer re-produces) and `LOOP2_MAX_REOPENS`
(serendipity's advisory loop-1 reopens).

`run_close` runs BOTH blind reviewers on the artefato; on any strike/fail it BOUNCES
(re-produces via `produce_fn`) up to `BOUNCE_MAX` times, then HARD-FAILS — never an
unbounded loop. `run_loop2` is the producer-loop brake: the critic converges (emits a
`ship` boolean), serendipity is ADVISORY (may request a reopen, bounded by
`LOOP2_MAX_REOPENS`) and can NEVER hold the loop hostage.

`produce_fn`, `reviewers`, the reviewers' `complete_fn`, and the loop-2 roles are all
injectable so these tests run offline.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import close  # noqa: E402


def _reviewer_strikes_n_then_passes(n):
    """A reviewer stub that strikes its first `n` calls then passes. The `complete_fn`
    is accepted-and-ignored (kept in the signature so it stays injectable like the real
    reviewers)."""
    calls = {"count": 0}

    def reviewer(artefato, complete_fn=None):
        calls["count"] += 1
        if calls["count"] <= n:
            return {"pass": False, "scores": {}, "strikes": ["a strike"], "overall": 2.0}
        return {"pass": True, "scores": {}, "strikes": [], "overall": 4.0}

    reviewer.calls = calls
    return reviewer


def _reviewer_always_passes():
    def reviewer(artefato, complete_fn=None):
        return {"pass": True, "scores": {}, "strikes": [], "overall": 4.0}
    return reviewer


def _reviewer_always_strikes():
    def reviewer(artefato, complete_fn=None):
        return {"pass": False, "scores": {}, "strikes": ["a strike"], "overall": 2.0}
    return reviewer


def _counting_producer():
    """A produce_fn that counts its calls and returns a fresh GENUS-CONFORMANT artefato each
    time (so the genus gate — which now runs first — passes and the reviewer bounce is what
    these tests exercise)."""
    calls = {"count": 0}

    def produce_fn():
        calls["count"] += 1
        return _conformant_artefato(f"re-produced-{calls['count']}")

    produce_fn.calls = calls
    return produce_fn


def _conformant_artefato(slug="bound-artefato"):
    """A genus-conformant artefato (snippeted cite, bodied proposes, intent) so the genus
    gate passes and the close reaches the reviewers + the proof mint."""
    return {
        "slug": slug,
        "content": {"sections": [{"title": "Body", "blocks": [
            {"type": "paragraph", "text": "the proof is bound to this exact payload."},
        ]}]},
        "cites": [{"ref": "github:abc", "kind": "atividade", "relevant": True,
                   "snippet": "the cursor became a watermark"}],
        "proposes": [{"body": "name the budget", "kind": "constraint"}],
        "intent": "open: x; bet: y",
    }


def _genus_invalid_artefato(slug="genus-bad"):
    """A genus-INVALID artefato: a cite with no snippet. check_genus must flag it, so the
    close bounces BEFORE any reviewer proof is minted."""
    art = _conformant_artefato(slug)
    art["cites"] = [{"ref": "github:abc", "kind": "atividade", "relevant": True}]  # no snippet
    return art


class BounceIsBoundedByProtocol(unittest.TestCase):
    """The bound lives in the protocol constants (BOUNCE_MAX / LOOP2_MAX_REOPENS), never
    in the producer's discretion. A single strike triggers exactly one re-produce then
    passes; an always-striking reviewer bounces exactly BOUNCE_MAX times then HARD-FAILS
    (no infinite loop). Loop-2: serendipity is advisory + bounded, and the critic's
    `ship` stops the loop immediately — serendipity can never hold it hostage."""

    def test_one_strike_triggers_exactly_one_reproduce_then_passes(self):
        produce_fn = _counting_producer()
        # one reviewer strikes once then passes; the other always passes.
        striker = _reviewer_strikes_n_then_passes(1)
        passer = _reviewer_always_passes()
        result = close.run_close(
            _conformant_artefato("first-cut"), produce_fn,
            reviewers=(striker, passer), complete_fn=lambda *a, **k: "",
        )
        self.assertTrue(result["pass"])
        self.assertEqual(produce_fn.calls["count"], 1)  # exactly one re-produce

    def test_always_strikes_bounces_bounce_max_then_hard_fails(self):
        produce_fn = _counting_producer()
        always = _reviewer_always_strikes()
        result = close.run_close(
            _conformant_artefato("first-cut"), produce_fn,
            reviewers=(always, _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "",
        )
        self.assertFalse(result["pass"])  # hard fail, no infinite loop
        self.assertEqual(produce_fn.calls["count"], close.BOUNCE_MAX)
        self.assertIn("verdicts", result)

    def test_serendipity_is_advisory_and_bounded_critic_converges(self):
        reopen_calls = {"count": 0}

        def reopen_fn():
            reopen_calls["count"] += 1
            return {"slug": "re-gathered"}

        # critic never wants to ship → only the reopen bound stops the loop.
        def critic_never_ships(artefato):
            return {"ship": False}

        # serendipity ALWAYS wants to diverge/reopen — it must NOT loop forever.
        def serendipity_always_reopens(artefato):
            return {"reopen": True}

        result = close.run_loop2(
            {"slug": "draft"}, critic_never_ships,
            serendipity_always_reopens, reopen_fn,
        )
        # serendipity is bounded by the protocol, never unbounded.
        self.assertEqual(reopen_calls["count"], close.LOOP2_MAX_REOPENS)
        self.assertFalse(result["ship"])

    def test_critic_ship_stops_loop_even_if_serendipity_wants_to_diverge(self):
        reopen_calls = {"count": 0}

        def reopen_fn():
            reopen_calls["count"] += 1
            return {"slug": "re-gathered"}

        def critic_ships(artefato):
            return {"ship": True}

        def serendipity_always_reopens(artefato):
            return {"reopen": True}  # still diverging, but cannot hold the loop hostage

        result = close.run_loop2(
            {"slug": "draft"}, critic_ships,
            serendipity_always_reopens, reopen_fn,
        )
        self.assertTrue(result["ship"])
        self.assertEqual(reopen_calls["count"], 0)  # ship wins; serendipity never gates


class ProofIsBoundAndUnforgeable(unittest.TestCase):
    """The minted proof is UNFORGEABLE and BOUND (Codex re-review #2). run_close stamps a
    run_close-only secret token and a sha256 digest of the EXACT publish payload
    (slug + spec + intent + cites + proposes) carrying BOTH reviewer verdicts.
    `close.verify_proof` accepts it only against that same payload; a hand-built dict, a
    proof minted for a different artefato (digest mismatch), or a single-reviewer proof is
    rejected BEFORE any publish."""

    def _passing_reviewer(self):
        def reviewer(artefato, complete_fn=None):
            return {"pass": True, "scores": {}, "strikes": [], "overall": 4.0}
        return reviewer

    def _mint(self, art):
        """Run the close with no publish_fn so it returns the minted proof. Uses the REAL
        canonical reviewers so the proof carries both canonical identities verify_proof
        requires (a proof minted from fakes is now rejected on identity grounds, #3)."""
        return close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(close.feynman_review, close.regular_review),
            complete_fn=lambda *a, **k: '{"pass": true, "scores": {}, "strikes": []}',
        )

    def test_minted_proof_carries_token_digest_and_both_verdicts(self):
        art = _conformant_artefato()
        proof = self._mint(art)
        self.assertTrue(proof["pass"])
        self.assertIn("token", proof)
        self.assertIn("digest", proof)
        self.assertEqual(len(proof["verdicts"]), 2)
        # verify_proof accepts the proof against the SAME payload it was minted over.
        close.verify_proof(
            proof, slug=art["slug"], spec=art["content"], intent=art["intent"],
            cites=art["cites"], proposes=art["proposes"], reviewer_count=2,
        )

    def test_hand_built_proof_is_rejected_no_valid_token(self):
        art = _conformant_artefato()
        forged = {"pass": True, "verdicts": [
            {"pass": True}, {"pass": True}], "digest": "whatever", "token": "guessed"}
        with self.assertRaises(ValueError):
            close.verify_proof(
                forged, slug=art["slug"], spec=art["content"], intent=art["intent"],
                cites=art["cites"], proposes=art["proposes"], reviewer_count=2,
            )

    def test_proof_for_artefato_A_cannot_verify_artefato_B_digest_mismatch(self):
        art_a = _conformant_artefato("artefato-a")
        art_b = _conformant_artefato("artefato-b")
        proof = self._mint(art_a)
        # the proof is bound to A's payload — verifying it against B's payload must raise.
        with self.assertRaises(ValueError):
            close.verify_proof(
                proof, slug=art_b["slug"], spec=art_b["content"], intent=art_b["intent"],
                cites=art_b["cites"], proposes=art_b["proposes"], reviewer_count=2,
            )

    def test_single_reviewer_proof_is_rejected(self):
        art = _conformant_artefato()
        proof = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(self._passing_reviewer(),),  # only ONE reviewer
            complete_fn=lambda *a, **k: "",
        )
        with self.assertRaises(ValueError):
            close.verify_proof(
                proof, slug=art["slug"], spec=art["content"], intent=art["intent"],
                cites=art["cites"], proposes=art["proposes"], reviewer_count=2,
            )


class ProofBindsIdentityAndAllPublishState(unittest.TestCase):
    """Codex re-review #3. The proof must (1) be un-mintable from producer code —
    `mint_proof` is no longer public; only run_close's PRIVATE `_mint_proof` exists, and
    run_close stamps the CANONICAL reviewer IDENTITIES (the real feynman + regular
    reviewers), so a proof built from fake/injected reviewers fails identity verification;
    and (2) bind EVERY page/state-affecting publish argument — `distills` and `skill` —
    into the digest, so altering them after the mint fails verify."""

    def test_mint_proof_is_not_a_public_attribute(self):
        # the public mint is gone; the producer cannot stamp a valid token onto a verdict
        # list of its own choosing.
        self.assertFalse(hasattr(close, "mint_proof"))
        self.assertTrue(hasattr(close, "_mint_proof"))

    def test_proof_from_real_reviewers_carries_both_canonical_identities(self):
        # the close run with the REAL canonical reviewers stamps both identities; verify
        # against the same payload passes (identity satisfied).
        art = _conformant_artefato()
        proof = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(close.feynman_review, close.regular_review),
            complete_fn=lambda *a, **k: '{"pass": true, "scores": {}, "strikes": []}',
        )
        self.assertTrue(proof["pass"])
        close.verify_proof(
            proof, slug=art["slug"], spec=art["content"], intent=art["intent"],
            cites=art["cites"], proposes=art["proposes"], reviewer_count=2,
        )

    def test_proof_from_fake_reviewers_fails_identity_verification(self):
        # a producer who injects fake reviewers (the test-only seam) gets a proof WITHOUT
        # the canonical identities — verify_proof rejects it on identity grounds.
        art = _conformant_artefato()

        def fake_reviewer(artefato, complete_fn=None):
            return {"pass": True, "scores": {}, "strikes": [], "overall": 4.0}

        proof = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(fake_reviewer, fake_reviewer),
            complete_fn=lambda *a, **k: "",
        )
        with self.assertRaises(ValueError):
            close.verify_proof(
                proof, slug=art["slug"], spec=art["content"], intent=art["intent"],
                cites=art["cites"], proposes=art["proposes"], reviewer_count=2,
            )

    def test_altering_distills_after_mint_fails_verify(self):
        art = _conformant_artefato()
        proof = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(close.feynman_review, close.regular_review),
            complete_fn=lambda *a, **k: '{"pass": true, "scores": {}, "strikes": []}',
        )
        # the proof verifies against the distills/skill it was minted over...
        close.verify_proof(
            proof, slug=art["slug"], spec=art["content"], intent=art["intent"],
            cites=art["cites"], proposes=art["proposes"],
            distills=art.get("distills"), skill=art.get("skill"), reviewer_count=2,
        )
        # ...but a DIFFERENT distills (poisoned provenance) is rejected.
        with self.assertRaises(ValueError):
            close.verify_proof(
                proof, slug=art["slug"], spec=art["content"], intent=art["intent"],
                cites=art["cites"], proposes=art["proposes"],
                distills=[{"page": "poisoned", "body": "altered at publish time"}],
                skill=art.get("skill"), reviewer_count=2,
            )

    def test_altering_skill_after_mint_fails_verify(self):
        art = _conformant_artefato()
        proof = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(close.feynman_review, close.regular_review),
            complete_fn=lambda *a, **k: '{"pass": true, "scores": {}, "strikes": []}',
        )
        with self.assertRaises(ValueError):
            close.verify_proof(
                proof, slug=art["slug"], spec=art["content"], intent=art["intent"],
                cites=art["cites"], proposes=art["proposes"],
                distills=art.get("distills"), skill="a-different-skill",
                reviewer_count=2,
            )


class GenusRunsBeforeAnyProofIsMinted(unittest.TestCase):
    """Codex re-review #2 (medium): run_close calls check_genus at the START of each close
    iteration. A genus violation is a BLOCKING strike that bounces through produce_fn under
    BOUNCE_MAX — BEFORE any reviewer runs or any proof is minted. A genus-invalid artefato
    can NEVER yield a pass proof, even with a custom/omitted publish_fn."""

    def test_genus_invalid_never_mints_a_pass_proof_and_bounces_then_hard_fails(self):
        produce_calls = {"count": 0}
        reviewer_calls = {"count": 0}

        def produce_fn():
            produce_calls["count"] += 1
            return _genus_invalid_artefato()  # still invalid on re-produce

        def reviewer(artefato, complete_fn=None):
            reviewer_calls["count"] += 1
            return {"pass": True, "scores": {}, "strikes": [], "overall": 4.0}

        result = close.run_close(
            _genus_invalid_artefato(), produce_fn=produce_fn,
            reviewers=(reviewer, reviewer), complete_fn=lambda *a, **k: "",
        )
        self.assertFalse(result["pass"])               # never a pass proof
        self.assertNotIn("token", result)              # no proof minted
        self.assertEqual(produce_calls["count"], close.BOUNCE_MAX)  # bounced, then hard-failed
        self.assertEqual(reviewer_calls["count"], 0)   # reviewers never ran on a genus-invalid

    def test_genus_violation_blocks_publish_even_with_custom_publish_fn(self):
        published = []

        def publish_fn(artefato, proof):
            published.append(artefato)

        result = close.run_close(
            _genus_invalid_artefato(), produce_fn=_genus_invalid_artefato,
            reviewers=(lambda a, complete_fn=None: {"pass": True, "strikes": []},) * 2,
            complete_fn=lambda *a, **k: "", publish_fn=publish_fn,
        )
        self.assertFalse(result["pass"])
        self.assertEqual(published, [])  # genus-invalid never reaches publish_fn


class GenusViolationsAreFedToReProduction(unittest.TestCase):
    """Codex P2 (#30) — a genus violation (incl. a rich-rite floor strike) must be FED to the
    re-production path, not bounce silently to a static draft and hard-fail. When `improve_fn`
    is wired, a genus violation hands the named violations to `improve_fn(art, feedback)` so the
    draft is re-produced richer (the floor FORCES depth); without `improve_fn`, behaviour is the
    unchanged static bounce."""

    def _shallow_developed_prose(self, slug="shallow-dev"):
        # a developed prose synthesis (>= 3 prose blocks) missing all four cognitive moves —
        # check_genus returns rich-rite:* strikes.
        return {
            "slug": slug,
            "content": {"sections": [{"title": "Findings", "blocks": [
                {"type": "paragraph", "text": "The system has three components."},
                {"type": "paragraph", "text": "Each holds its own state."},
                {"type": "paragraph", "text": "They are wired at startup."},
            ]}]},
            "cites": [], "proposes": [{"body": "x", "kind": "constraint"}],
            "distills": [], "intent": "open: x; bet: y", "skill": "report",
        }

    def test_rich_rite_violation_is_handed_to_improve_fn_and_re_produced(self):
        seen_feedback = {"all": []}

        def improve_fn(art, feedback):
            # capture the feedback and FIX the violations (add the four moves) — the floor forced it
            seen_feedback["all"].append(feedback)
            fixed = {**art}
            fixed["cites"] = [{"ref": "arXiv:1", "kind": "mundo", "relevant": True,
                               "snippet": "an external benchmark"}]
            fixed["distills"] = ["cluster:recall"]
            fixed["content"] = {"sections": [{"title": "Argument", "blocks": [
                {"type": "paragraph", "text": "We derive it from first principles, therefore X."},
                {"type": "paragraph", "text": "What I don't know: whether it survives a crash."},
                {"type": "paragraph", "text": "This builds on the prior recall thread."},
            ]}]}
            return fixed

        published = []

        result = close.run_close(
            self._shallow_developed_prose(), produce_fn=lambda: self._shallow_developed_prose(),
            reviewers=(close.feynman_review, close.regular_review),
            complete_fn=lambda *a, **k: '{"pass": true, "scores": {}, "strikes": []}',
            improve_fn=improve_fn, publish_fn=lambda a, p: published.append(a),
        )
        self.assertTrue(result["pass"], "the floor must re-produce richer, not hard-fail")
        self.assertEqual(len(published), 1)
        # the genus feedback reached improve_fn at least once (it carried the rich-rite strikes)
        flat = str(seen_feedback["all"])
        self.assertIn("rich-rite", flat,
                      f"improve_fn was not handed the rich-rite genus feedback: {flat!r}")

    def test_without_improve_fn_genus_violation_is_the_unchanged_static_bounce(self):
        # no improve_fn → a persistent genus violation bounces to the static produce_fn and
        # hard-fails (behaviour unchanged; the gate still rejects).
        result = close.run_close(
            self._shallow_developed_prose(),
            produce_fn=lambda: self._shallow_developed_prose(),
            reviewers=(close.feynman_review, close.regular_review),
            complete_fn=lambda *a, **k: '{"pass": true, "scores": {}, "strikes": []}',
        )
        self.assertFalse(result["pass"])
        self.assertIn("genus_violations", result)
        self.assertTrue(any(v.startswith("rich-rite") for v in result["genus_violations"]))


class DegradedReviewerOutputCannotMintAPass(unittest.TestCase):
    """Codex round-7 [high]: a degraded/schema-drifted reviewer completion must NOT mint a
    proof. The verdict path (`_parse_verdict`) now fails closed on any non-bool `pass`, so a
    completer returning `{"pass":"false", ...}` (which `bool()` would coerce to True) yields a
    FAILING verdict — run_close bounces, then HARD-FAILS within BOUNCE_MAX and never calls
    publish_fn. A real boolean `{"pass": true}` still passes."""

    def test_string_false_completion_never_publishes_and_hard_fails(self):
        published = []

        def publish_fn(artefato, proof):
            published.append(artefato)

        art = _conformant_artefato()
        # the completer returns the degraded JSON the canonical reviewers will parse.
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(close.feynman_review, close.regular_review),
            complete_fn=lambda *a, **k: '{"pass": "false", "scores": {}, "strikes": ["x"]}',
            publish_fn=publish_fn,
        )
        self.assertFalse(result["pass"])      # no pass proof minted
        self.assertNotIn("token", result)     # not a minted proof
        self.assertEqual(published, [])       # publish_fn never called

    def test_string_true_completion_also_fails_closed(self):
        published = []

        def publish_fn(artefato, proof):
            published.append(artefato)

        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(close.feynman_review, close.regular_review),
            complete_fn=lambda *a, **k: '{"pass": "true", "scores": {}, "strikes": []}',
            publish_fn=publish_fn,
        )
        self.assertFalse(result["pass"])
        self.assertEqual(published, [])

    def test_real_bool_true_completion_mints_and_publishes(self):
        published = []

        def publish_fn(artefato, proof):
            published.append((artefato, proof))

        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(close.feynman_review, close.regular_review),
            complete_fn=lambda *a, **k: '{"pass": true, "scores": {}, "strikes": []}',
            publish_fn=publish_fn,
        )
        self.assertTrue(result["pass"])
        self.assertEqual(len(published), 1)

    def test_malformed_score_completion_fails_closed(self):
        published = []

        def publish_fn(artefato, proof):
            published.append(artefato)

        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(close.feynman_review, close.regular_review),
            complete_fn=lambda *a, **k: (
                '{"pass": true, "scores": {"content_depth": "high"}, "strikes": []}'),
            publish_fn=publish_fn,
        )
        self.assertFalse(result["pass"])  # malformed score → fail closed, no proof
        self.assertEqual(published, [])


class DegradedReviewerExceptionsBounceNeverCrash(unittest.TestCase):
    """Codex round-8 [medium] — close the whole degraded-reviewer-output class. A reviewer
    or its parser raising on schema drift must NOT crash run_close: ANY exception from a
    reviewer/`_parse_verdict` becomes a FAILING verdict (defense in depth), so run_close
    BOUNCES then HARD-FAILS within BOUNCE_MAX and NEVER calls publish_fn. A well-formed
    verdict still passes and publishes."""

    def _publisher(self):
        published = []

        def publish_fn(artefato, proof):
            published.append((artefato, proof))

        return publish_fn, published

    def test_completer_that_raises_bounces_then_hard_fails_never_publishes(self):
        publish_fn, published = self._publisher()
        produce_fn = _counting_producer()

        def exploding_completer(*a, **k):
            raise RuntimeError("review router exploded")

        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=produce_fn,
            reviewers=(close.feynman_review, close.regular_review),
            complete_fn=exploding_completer, publish_fn=publish_fn,
        )
        self.assertFalse(result["pass"])               # controlled failure, not a crash
        self.assertNotIn("token", result)              # no proof minted
        self.assertEqual(produce_fn.calls["count"], close.BOUNCE_MAX)  # bounced then hard-failed
        self.assertEqual(published, [])                 # publish_fn never called

    def test_reviewer_callable_that_raises_bounces_then_hard_fails(self):
        publish_fn, published = self._publisher()
        produce_fn = _counting_producer()

        def exploding_reviewer(artefato, complete_fn=None):
            raise ValueError("reviewer blew up")

        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=produce_fn,
            reviewers=(exploding_reviewer, _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "", publish_fn=publish_fn,
        )
        self.assertFalse(result["pass"])
        self.assertEqual(produce_fn.calls["count"], close.BOUNCE_MAX)
        self.assertEqual(published, [])

    def test_scores_null_completion_bounces_then_hard_fails_never_publishes(self):
        publish_fn, published = self._publisher()
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(close.feynman_review, close.regular_review),
            complete_fn=lambda *a, **k: '{"pass": true, "scores": null, "strikes": []}',
            publish_fn=publish_fn,
        )
        self.assertFalse(result["pass"])   # degraded shape → fail closed, no crash
        self.assertEqual(published, [])

    def test_scores_list_completion_bounces_then_hard_fails_never_publishes(self):
        publish_fn, published = self._publisher()
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(close.feynman_review, close.regular_review),
            complete_fn=lambda *a, **k: '{"pass": true, "scores": [], "strikes": []}',
            publish_fn=publish_fn,
        )
        self.assertFalse(result["pass"])
        self.assertEqual(published, [])

    def test_strikes_null_completion_bounces_then_hard_fails_never_publishes(self):
        publish_fn, published = self._publisher()
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(close.feynman_review, close.regular_review),
            complete_fn=lambda *a, **k: '{"pass": true, "scores": {}, "strikes": null}',
            publish_fn=publish_fn,
        )
        self.assertFalse(result["pass"])
        self.assertEqual(published, [])

    def test_non_dict_result_completion_bounces_then_hard_fails_never_publishes(self):
        publish_fn, published = self._publisher()
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(close.feynman_review, close.regular_review),
            complete_fn=lambda *a, **k: '[1, 2, 3]',  # JSON list, not a verdict dict
            publish_fn=publish_fn,
        )
        self.assertFalse(result["pass"])
        self.assertEqual(published, [])

    def test_well_formed_verdict_still_mints_and_publishes(self):
        publish_fn, published = self._publisher()
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(close.feynman_review, close.regular_review),
            complete_fn=lambda *a, **k: '{"pass": true, "scores": {}, "strikes": []}',
            publish_fn=publish_fn,
        )
        self.assertTrue(result["pass"])
        self.assertEqual(len(published), 1)


class StruckVerdictCannotMintOrVerifyAProof(unittest.TestCase):
    """Codex round-9 [high]: a struck reviewer verdict must NEVER mint or verify a passing
    proof. Even when both canonical reviewers return `{"pass":true,"strikes":["x"]}`, the
    close protocol says ANY strike must bounce/fail — so run_close BOUNCES then HARD-FAILS and
    publish_fn is NEVER called. A clean `{"pass":true,"strikes":[]}` still passes and publishes.
    A non-list strikes already fails closed (round-8). verify_proof also rejects a proof whose
    verdicts carry strikes."""

    def _publisher(self):
        published = []

        def publish_fn(artefato, proof):
            published.append((artefato, proof))

        return publish_fn, published

    def test_both_reviewers_pass_with_strikes_bounces_then_hard_fails_never_publishes(self):
        publish_fn, published = self._publisher()
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(close.feynman_review, close.regular_review),
            complete_fn=lambda *a, **k: '{"pass": true, "scores": {}, "strikes": ["uncited claim"]}',
            publish_fn=publish_fn,
        )
        self.assertFalse(result["pass"])      # struck → no pass proof
        self.assertNotIn("token", result)     # not a minted proof
        self.assertEqual(published, [])       # publish_fn never called

    def test_clean_empty_strikes_still_mints_and_publishes(self):
        publish_fn, published = self._publisher()
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(close.feynman_review, close.regular_review),
            complete_fn=lambda *a, **k: '{"pass": true, "scores": {}, "strikes": []}',
            publish_fn=publish_fn,
        )
        self.assertTrue(result["pass"])
        self.assertEqual(len(published), 1)

    def test_non_list_strikes_still_fails_closed(self):
        publish_fn, published = self._publisher()
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(close.feynman_review, close.regular_review),
            complete_fn=lambda *a, **k: '{"pass": true, "scores": {}, "strikes": "oops"}',
            publish_fn=publish_fn,
        )
        self.assertFalse(result["pass"])
        self.assertEqual(published, [])

    def test_verify_proof_rejects_a_proof_whose_verdicts_carry_strikes(self):
        # a proof whose verdicts pass-but-carry-strikes must be rejected at the publish seam.
        art = _conformant_artefato()
        # mint a legitimate proof, then poison its verdicts with strikes.
        proof = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(close.feynman_review, close.regular_review),
            complete_fn=lambda *a, **k: '{"pass": true, "scores": {}, "strikes": []}',
        )
        self.assertTrue(proof["pass"])
        struck = {
            **proof,
            "verdicts": [{**v, "strikes": ["uncited claim"]} for v in proof["verdicts"]],
        }
        with self.assertRaises(ValueError):
            close.verify_proof(
                struck, slug=art["slug"], spec=art["content"], intent=art["intent"],
                cites=art["cites"], proposes=art["proposes"], reviewer_count=2,
            )


class ImproveGatesRefineBeforeTheGate(unittest.TestCase):
    """The two improve-gates (one after the other). When `improve_fn` is given, run_close runs
    IMPROVE_ROUNDS UNCONDITIONAL review→improve passes BEFORE the gating close: each pass reviews
    the draft purely for FEEDBACK (rationales + strikes — the noisy score never gates) and hands
    it to improve_fn, which REVISES the draft. The refine never mints/publishes; the gating close
    seals the proof on the final, twice-improved artefato — so the reviewers' pass is always of
    exactly what publishes. With no improve_fn the stage is skipped and behaviour is unchanged."""

    def _passing_completer(self):
        return lambda *a, **k: '{"pass": true, "scores": {}, "strikes": []}'

    def test_improve_fn_runs_improve_rounds_times_then_gates_and_publishes(self):
        calls = {"count": 0, "feedback_lens": []}

        def improve_fn(art, feedback):
            calls["count"] += 1
            calls["feedback_lens"].append(len(feedback))  # both reviewers' feedback each round
            return art

        published = []

        def publish_fn(art, proof):
            published.append(art)

        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(close.feynman_review, close.regular_review),
            complete_fn=self._passing_completer(), publish_fn=publish_fn,
            improve_fn=improve_fn,
        )
        self.assertTrue(result["pass"])
        self.assertEqual(calls["count"], close.IMPROVE_ROUNDS)   # exactly two improve-gates
        self.assertEqual(calls["feedback_lens"], [2] * close.IMPROVE_ROUNDS)  # both reviewers
        self.assertEqual(len(published), 1)

    def test_no_improve_fn_means_no_refinement_behaviour_unchanged(self):
        published = []

        def publish_fn(art, proof):
            published.append(art)

        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(close.feynman_review, close.regular_review),
            complete_fn=self._passing_completer(), publish_fn=publish_fn,
        )
        self.assertTrue(result["pass"])
        self.assertEqual(len(published), 1)

    def test_published_artefato_is_the_improved_one_proof_binds_to_it(self):
        # improve_fn revises the draft; the gating close mints the proof on the REVISED artefato,
        # so what publishes is provably what the reviewers passed.
        def improve_fn(art, feedback):
            return {**art, "content": {"sections": [{"title": "Refined", "blocks": [
                {"type": "paragraph", "text": "improved from the reviewers' feedback."}]}]}}

        published = []

        def publish_fn(art, proof):
            published.append((art, proof))

        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(close.feynman_review, close.regular_review),
            complete_fn=self._passing_completer(), publish_fn=publish_fn,
            improve_fn=improve_fn,
        )
        self.assertTrue(result["pass"])
        self.assertEqual(len(published), 1)
        pub_art, proof = published[0]
        self.assertIn("Refined", str(pub_art["content"]))
        # the proof binds to the improved content — verify_proof accepts it against the published spec
        close.verify_proof(
            proof, slug=pub_art["slug"], spec=pub_art["content"], intent=pub_art["intent"],
            cites=pub_art["cites"], proposes=pub_art["proposes"], reviewer_count=2,
        )

    def test_improve_rounds_is_overridable_per_call(self):
        calls = {"count": 0}

        def improve_fn(art, feedback):
            calls["count"] += 1
            return art

        art = _conformant_artefato()
        close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(close.feynman_review, close.regular_review),
            complete_fn=self._passing_completer(), improve_fn=improve_fn, improve_rounds=3,
        )
        self.assertEqual(calls["count"], 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
