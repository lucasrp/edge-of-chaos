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

    # R7 (S1): the improve loop is NOT a fixed N. It runs while the refiner keeps CHANGING the draft;
    # it stops on convergence (no outstanding issue) or plateau (refiner returns the draft unchanged),
    # and IMPROVE_BACKSTOP bounds a refiner that changes the draft without ever converging (cosmetic
    # churn / receding-target). It NEVER cuts off a still-improving loop. These tests replace the old
    # "runs exactly IMPROVE_ROUNDS times" test, whose fixed-count premise R7 overturns.

    @staticmethod
    def _changing_improve():
        calls = {"count": 0}

        def improve(art, feedback):
            calls["count"] += 1
            return {**art, "content": {"sections": [{"title": f"v{calls['count']}", "blocks": [
                {"type": "paragraph", "text": f"changed pass {calls['count']}."}]}]}}
        improve.calls = calls
        return improve

    @staticmethod
    def _countdown_reviewer(start_n):
        # strikes `start_n` issues on call 1, one fewer each call (the refiner resolving one per round),
        # passing once it reaches 0 — i.e. the outstanding-issue set shrinks each round.
        rounds = {"n": 0}

        def reviewer(artefato, complete_fn=None):
            rounds["n"] += 1
            remaining = max(0, start_n - (rounds["n"] - 1))
            strikes = [f"issue-{i}" for i in range(remaining)]
            return {"pass": not strikes, "scores": {}, "strikes": strikes,
                    "overall": 4.0 if not strikes else 2.0}
        return reviewer

    def test_converged_clean_draft_skips_improve_and_is_preserved(self):
        # Codex S1 review #6: a draft with NO outstanding issues needs no refinement — the improve loop
        # does 0 rounds and goes straight to the gating close; a non-idempotent improver never churns
        # the clean artifact.
        calls = {"count": 0}

        def churning_improve(art, feedback):
            calls["count"] += 1
            return {**art, "content": {"sections": [{"title": f"churn{calls['count']}", "blocks": [
                {"type": "paragraph", "text": "needless rewrite."}]}]}}

        published = []
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(close.feynman_review, close.regular_review),
            complete_fn=self._passing_completer(),
            publish_fn=lambda a, p: published.append(a), improve_fn=churning_improve,
        )
        self.assertTrue(result["pass"])
        self.assertEqual(calls["count"], 0)            # converged → 0 improve rounds
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0], art)            # clean artifact preserved, not churned

    def test_unchanged_draft_with_issues_plateaus(self):
        # issues present but the refiner returns the draft UNCHANGED → plateau (revised==artefato),
        # stop after one attempt rather than spin to the backstop.
        calls = {"count": 0}

        def noop_improve(art, feedback):
            calls["count"] += 1
            return art

        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(_reviewer_always_strikes(), _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "", improve_fn=noop_improve,
        )
        self.assertEqual(calls["count"], 1)
        # Codex S1 #21: the plateau failure preserves the last blocking verdicts (actionable strikes),
        # not an opaque empty failure.
        self.assertFalse(result["pass"])
        self.assertTrue(any(v.get("strikes") for v in result.get("verdicts", [])))

    def test_plateau_with_outstanding_issue_fails_closed_even_if_reviewer_then_passes(self):
        # Codex S1 #12: a reviewer strikes the draft, improve_fn returns it UNCHANGED (plateau with an
        # outstanding issue), and the SAME stateful reviewer would PASS on the next call. The plateau
        # must HARD FAIL-CLOSED before the gate — never mint on the would-be-clean gating verdict.
        rounds = {"n": 0}

        def strike_then_pass(artefato, complete_fn=None):
            rounds["n"] += 1
            return ({"pass": False, "scores": {}, "strikes": ["needs work"], "overall": 2.0}
                    if rounds["n"] == 1 else
                    {"pass": True, "scores": {}, "strikes": [], "overall": 4.0})

        published = []
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(strike_then_pass, _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "", improve_fn=lambda a, fb: a,   # unchanged → plateau
            publish_fn=lambda a, p: published.append(a),
        )
        self.assertFalse(result["pass"])     # plateau-with-issue → fail-closed, not minted on round-2 pass
        self.assertEqual(len(published), 0)

    def test_stops_when_issues_resolved_and_does_not_churn(self):
        # Codex S1 review #6: once issues reach 0 the loop stops BEFORE calling improve_fn again, so a
        # non-idempotent improver cannot churn or break a converged artifact.
        rounds = {"n": 0}

        def countdown2(artefato, complete_fn=None):
            rounds["n"] += 1
            remaining = max(0, 2 - (rounds["n"] - 1))   # 2,1,0,...
            return {"pass": not remaining, "scores": {},
                    "strikes": [f"i{i}" for i in range(remaining)], "overall": 2.0}

        improve = self._changing_improve()
        art = _conformant_artefato()
        close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(countdown2, _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "", improve_fn=improve,
        )
        self.assertEqual(improve.calls["count"], 2)    # 2 resolving rounds; stops at the zero-issue round

    def test_style_category_residual_cannot_launder_a_blocker(self):
        # Codex S1 review #6: broad categories (style/wording) are NOT on the cosmetic allowlist, so an
        # R0/correctness finding filed under category 'style' is default-denied → strike → fail-closed.
        def launder_style(artefato, complete_fn=None):
            return {"pass": True, "scores": {}, "strikes": [], "residual": [
                {"severity": "non_blocking", "category": "style",
                 "note": "storytelling is thin and the visual replaces the explanation"}]}

        published = []
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(launder_style, _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "", publish_fn=lambda a, p: published.append(a),
        )
        self.assertFalse(result["pass"])
        self.assertEqual(len(published), 0)

    def test_continues_while_issues_resolve(self):
        # progress = the outstanding-issue set SHRINKS. A reviewer whose strikes count down each round
        # keeps the loop going PAST the old fixed 2 — it is NOT cut off while real progress happens —
        # and a persistent set that only shrinks never trips the churn detector (Codex S1 review #4).
        improve = self._changing_improve()
        art = _conformant_artefato()
        close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(self._countdown_reviewer(3), _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "", improve_fn=improve,
        )
        self.assertGreaterEqual(improve.calls["count"], 3)        # ran while resolving (> old fixed 2)
        self.assertLess(improve.calls["count"], close.IMPROVE_BACKSTOP)

    def test_one_at_a_time_blockers_reach_clean_not_cut_off(self):
        # Codex S1 review #8: reviewers expose one blocker at a time (A, then B, then C, then clean).
        # Count stays at 1 each round, but each fix reveals the next — the loop must RESOLVE THROUGH to
        # clean, never cut off. (Draft-equality, not count, is the stop signal → no false cutoff.)
        rounds = {"n": 0}

        def one_at_a_time(artefato, complete_fn=None):
            rounds["n"] += 1
            return ({"pass": True, "scores": {}, "strikes": [], "overall": 4.0}
                    if rounds["n"] > 3 else
                    {"pass": False, "scores": {}, "strikes": [f"blocker-{rounds['n']}"], "overall": 2.0})

        improve = self._changing_improve()
        art = _conformant_artefato()
        close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(one_at_a_time, _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "", improve_fn=improve,
        )
        self.assertEqual(improve.calls["count"], 3)   # resolved A,B,C then converged — NOT cut at 2

    def test_exact_cap_fix_converges_at_verification_review_and_publishes(self):
        # Codex S1 #13: the draft is fixed by the FINAL permitted improve (improve_rounds=3) — there is
        # no 4th loop-top check, so the exhausted-but-CHANGED draft gets ONE verification review at the
        # gate, which now passes → it MINTS. A within-budget fix is never falsely cut off.
        rounds = {"n": 0}

        def strike_thrice_then_pass(artefato, complete_fn=None):
            rounds["n"] += 1
            return ({"pass": False, "scores": {}, "strikes": [f"b{rounds['n']}"], "overall": 2.0}
                    if rounds["n"] <= 3 else
                    {"pass": True, "scores": {}, "strikes": [], "overall": 4.0})

        improve = self._changing_improve()
        published = []
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(strike_thrice_then_pass, _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "", improve_fn=improve, improve_rounds=3,
            publish_fn=lambda a, p: published.append(a),
        )
        self.assertTrue(result["pass"])               # the final fix converges at the verification review
        self.assertEqual(len(published), 1)
        self.assertEqual(improve.calls["count"], 3)   # exactly the cap, then minted (not falsely failed)

    def test_in_place_mutating_improver_is_not_misclassified_as_plateau(self):
        # Codex S1 #14: an improve_fn that MUTATES the draft in place and returns the SAME object must
        # not be read as a plateau. A pre-call snapshot detects the real change → not plateau → the
        # in-place fix on the last round still gets the verification review and converges.
        def in_place_fix(artefato, feedback):
            artefato["content"]["sections"][0]["blocks"][0]["text"] += " (revised)"
            return artefato                            # mutated in place, SAME object

        rounds = {"n": 0}

        def strike_then_pass(artefato, complete_fn=None):
            rounds["n"] += 1
            return ({"pass": False, "scores": {}, "strikes": ["fix it"], "overall": 2.0}
                    if rounds["n"] == 1 else
                    {"pass": True, "scores": {}, "strikes": [], "overall": 4.0})

        published = []
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(strike_then_pass, _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "", improve_fn=in_place_fix, improve_rounds=1,
            publish_fn=lambda a, p: published.append(a),
        )
        self.assertTrue(result["pass"])     # in-place change detected → NOT plateau → verified → mint
        self.assertEqual(len(published), 1)

    def test_improve_stage_malformed_reviewer_return_fails_closed_not_crash(self):
        # Codex S1 #15: a reviewer that RETURNS a malformed shape (non-dict, or non-list strikes) in the
        # improve stage must be normalized to a bounded failing verdict — never crash issue counting —
        # so the schema-drift fail-closed contract holds with improve_fn enabled.
        def malformed(artefato, complete_fn=None):
            return None    # not a dict

        published = []
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(malformed, _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "", improve_fn=lambda a, fb: a,
            publish_fn=lambda a, p: published.append(a),
        )
        self.assertFalse(result["pass"])    # treated as a failing verdict → fail-closed, no crash
        self.assertEqual(len(published), 0)

    def test_residual_with_malformed_strikes_fails_closed_not_crash(self):
        # Codex S1 #16: a verdict carrying `residual` AND a truthy non-list `strikes` (e.g. 1) must not
        # crash the residual sanitizer in the gating close — it coerces safely and fails closed.
        def malformed(artefato, complete_fn=None):
            return {"pass": True, "scores": {}, "strikes": 1, "residual": ["x"]}

        published = []
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(malformed, _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "",
            publish_fn=lambda a, p: published.append(a),
        )
        self.assertFalse(result["pass"])
        self.assertEqual(len(published), 0)

    def test_identity_stamped_reviewer_returning_non_dict_fails_closed_not_crash(self):
        # Codex S1 #19: an identity-stamped reviewer that RETURNS a non-dict in the final gate must be
        # normalized before the identity-stamp spread — fail closed, never crash.
        def bad(artefato, complete_fn=None):
            return None
        bad.identity = "feynman_review"   # has identity but returns a non-dict

        published = []
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(bad, _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "",
            publish_fn=lambda a, p: published.append(a),
        )
        self.assertFalse(result["pass"])
        self.assertEqual(len(published), 0)

    def test_malformed_scores_direct_reviewer_fails_closed(self):
        # Codex S1 #23: a direct reviewer returning pass:true with malformed `scores` (non-dict) must
        # NOT mint — _normalize_verdict enforces the full shape contract → fail-closed.
        def bad_scores(artefato, complete_fn=None):
            return {"pass": True, "scores": None, "strikes": []}

        published = []
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(bad_scores, _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "",
            publish_fn=lambda a, p: published.append(a),
        )
        self.assertFalse(result["pass"])
        self.assertEqual(len(published), 0)

    def test_malformed_score_value_direct_reviewer_fails_closed(self):
        # a bool/non-numeric dimension score also fails closed (matches _parse_verdict).
        def bad_score_value(artefato, complete_fn=None):
            return {"pass": True, "scores": {"narrative_depth": "high"}, "strikes": []}

        published = []
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(bad_score_value, _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "",
            publish_fn=lambda a, p: published.append(a),
        )
        self.assertFalse(result["pass"])
        self.assertEqual(len(published), 0)

    def test_mixed_type_malformed_score_keys_fail_closed_not_crash(self):
        # Codex S1 #24: heterogeneous malformed score keys (int + str) must not crash the bad-score
        # report (which sorts the keys) — fail closed, never raise.
        def mixed(artefato, complete_fn=None):
            return {"pass": True, "scores": {1: "bad", "x": "bad"}, "strikes": []}

        published = []
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(mixed, _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "",
            publish_fn=lambda a, p: published.append(a),
        )
        self.assertFalse(result["pass"])
        self.assertEqual(len(published), 0)

    def test_improve_fn_raising_in_loop_fails_closed_not_crash(self):
        # Codex S1 #22: a refiner that RAISES in the improve loop is a non-convergence → fail closed,
        # not a crash; the last blocking feedback is preserved.
        def boom(art, fb):
            raise RuntimeError("refiner exploded")

        published = []
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(_reviewer_always_strikes(), _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "", improve_fn=boom,
            publish_fn=lambda a, p: published.append(a),
        )
        self.assertFalse(result["pass"])
        self.assertEqual(len(published), 0)
        self.assertTrue(any(v.get("strikes") for v in result.get("verdicts", [])))

    def test_improve_fn_raising_in_genus_bounce_fails_closed_not_crash(self):
        # Codex S1 #22: a refiner that RAISES during the genus-bounce repair fails closed, not a crash.
        def boom(art, fb):
            raise RuntimeError("refiner exploded")

        published = []
        result = close.run_close(
            _genus_invalid_artefato(), produce_fn=_genus_invalid_artefato,
            reviewers=(_reviewer_always_passes(), _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "", improve_fn=boom, improve_rounds=0,
            publish_fn=lambda a, p: published.append(a),
        )
        self.assertFalse(result["pass"])
        self.assertEqual(len(published), 0)

    def test_improve_fn_returning_non_dict_fails_closed_not_crash(self):
        # Codex S1 #17: improve_fn returning a non-dict (None/scalar) with issues outstanding must not
        # be passed to check_genus — it fails closed, never crashes.
        published = []
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(_reviewer_always_strikes(), _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "", improve_fn=lambda a, fb: None,
            publish_fn=lambda a, p: published.append(a),
        )
        self.assertFalse(result["pass"])
        self.assertEqual(len(published), 0)

    def test_genus_bounce_nondict_improver_fails_closed_not_crash(self):
        # Codex S1 #18: with improve_rounds=0 (pre-loop skipped) but improve_fn provided, a genus-invalid
        # artefato enters the gate's genus-bounce; if improve_fn returns a non-dict it must fail closed,
        # never reach check_genus(None).
        published = []
        result = close.run_close(
            _genus_invalid_artefato(), produce_fn=_genus_invalid_artefato,
            reviewers=(_reviewer_always_passes(), _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "", improve_fn=lambda a, fb: None, improve_rounds=0,
            publish_fn=lambda a, p: published.append(a),
        )
        self.assertFalse(result["pass"])
        self.assertEqual(len(published), 0)

    def test_cosmetic_churn_is_bounded_and_fails_closed(self):
        # a refiner that rewrites the draft but never resolves the strike never converges — the improve
        # loop is BOUNDED by the backstop (never unbounded) and the still-broken artefato then FAILS the
        # gating close CLOSED (never a false pass). (Codex S1 #8.)
        improve = self._changing_improve()
        published = []
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(_reviewer_always_strikes(), _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "", improve_fn=improve,
            publish_fn=lambda a, p: published.append(a),
        )
        self.assertLessEqual(improve.calls["count"], close.IMPROVE_BACKSTOP)  # bounded
        self.assertFalse(result["pass"])                                      # fail-closed
        self.assertEqual(len(published), 0)

    def test_receding_target_is_bounded_and_fails_closed(self):
        # the receding-target trap (the roberto bail): a DIFFERENT strike each round, draft changes,
        # never converges → bounded by the backstop AND failed closed by the gating close — never the
        # 15+ rounds it used to run, never a false pass.
        rounds = {"n": 0}

        def morphing(artefato, complete_fn=None):
            rounds["n"] += 1
            return {"pass": False, "scores": {}, "strikes": [f"different issue {rounds['n']}"],
                    "overall": 2.0}

        improve = self._changing_improve()
        published = []
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(morphing, _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "", improve_fn=improve,
            publish_fn=lambda a, p: published.append(a),
        )
        self.assertLessEqual(improve.calls["count"], close.IMPROVE_BACKSTOP)
        self.assertFalse(result["pass"])
        self.assertEqual(len(published), 0)

    def test_backstop_exhaustion_with_outstanding_issues_fails_closed(self):
        # a sequence that needs MORE than the backstop to resolve (count starts > backstop) is bounded
        # by the backstop and then FAILS the gating close CLOSED — bounded compute, never a false pass
        # of a non-converged artefato (Codex S1 #8). Resolving deeper than the backstop is a documented
        # limitation that needs the deferred stable-issue-id reviewer contract, not a silent pass.
        improve = self._changing_improve()
        published = []
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(self._countdown_reviewer(20), _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "", improve_fn=improve,
            publish_fn=lambda a, p: published.append(a),
        )
        self.assertLessEqual(improve.calls["count"], close.IMPROVE_BACKSTOP)
        self.assertFalse(result["pass"])
        self.assertEqual(len(published), 0)

    def test_backstop_exhaustion_blocks_stateful_bounce_to_pass(self):
        # Codex S1 #9: with exactly IMPROVE_BACKSTOP+1 one-at-a-time failures and a STATIC produce_fn,
        # the normal gating bounce would let the stateful countdown reach 0 on retry and falsely PASS.
        # Backstop exhaustion disables the bounce → one review, fail-closed. No false pass.
        improve = self._changing_improve()
        published = []
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,    # static: a bounce would re-review the SAME draft
            reviewers=(self._countdown_reviewer(close.IMPROVE_BACKSTOP + 1), _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "", improve_fn=improve,
            publish_fn=lambda a, p: published.append(a),
        )
        self.assertFalse(result["pass"])
        self.assertEqual(len(published), 0)

    def test_improve_rounds_zero_preserves_normal_gate_bounce(self):
        # Codex S1 #10: improve_rounds=0 SKIPS the improve stage but must NOT disable the gating bounce
        # (an empty backstop is a skip, not an exhaustion). A one-strike-then-pass reviewer bounces once
        # via produce_fn and passes — normal BOUNCE_MAX behavior preserved.
        produce = _counting_producer()
        striker = _reviewer_strikes_n_then_passes(1)
        result = close.run_close(
            _conformant_artefato("first"), produce,
            reviewers=(striker, _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "", improve_fn=lambda art, fb: art, improve_rounds=0,
        )
        self.assertTrue(result["pass"])              # bounce still available → striker passes on retry
        self.assertEqual(produce.calls["count"], 1)  # exactly one re-produce (BOUNCE_MAX), not cut to 0

    def test_reviewer_residual_even_cosmetic_is_promoted_to_strike(self):
        # Codex S1 review #7: a reviewer's SELF-classified residual is never trusted — even a
        # cosmetic-tagged residual is promoted to a strike → fail-closed. The non-blocking channel is
        # reserved for a deterministic cosmetic classifier (future slice), never the reviewer.
        def passer_with_residual(artefato, complete_fn=None):
            return {"pass": True, "scores": {}, "strikes": [], "residual": [
                {"severity": "non_blocking", "category": "formatting", "note": "minor: spacing nit"}]}

        published = []
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(passer_with_residual, _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "",
            publish_fn=lambda a, p: published.append(a),
        )
        self.assertFalse(result["pass"])      # reviewer residual promoted → fail-closed
        self.assertEqual(len(published), 0)

    def test_strikeless_pass_false_converges_without_churning_the_refiner(self):
        # Issue #65 SUPERSEDES Codex S1 #7: a pass:false verdict with NO strikes is an UNNAMED,
        # unactionable veto (gpt-5.4 emits it even on clean rich content). `pass` is derived from
        # strikes, so a strikeless verdict is CLEAN — the improve loop converges instead of churning
        # the refiner on criticism that names nothing to fix. A reviewer that wants a revision must
        # NAME a strike. (A NAMED strike still engages the refiner — covered by the sibling tests.)
        calls = {"count": 0}

        def strikeless_false(artefato, complete_fn=None):
            return {"pass": False, "scores": {"rigor": 4}, "strikes": [], "overall": 4.0}

        def noop_improve(art, feedback):
            calls["count"] += 1
            return art

        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(strikeless_false, _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "", improve_fn=noop_improve,
        )
        self.assertEqual(calls["count"], 0)   # converged — no named issue → no refine churn
        self.assertTrue(result.get("pass"))   # and the clean draft mints

    def test_blocking_residual_is_promoted_to_strike_and_fails_closed(self):
        # R5/S1 default-deny (Codex S1 review): a blocking finding MISCHANNELED into `residual` (even
        # tagged non_blocking) is detected by its category marker, promoted to a strike, and fails the
        # close CLOSED — it can never ship as residual. This proves the construction in CODE.
        def launderer(artefato, complete_fn=None):
            return {"pass": True, "scores": {}, "strikes": [],
                    "residual": [{"severity": "non_blocking", "note": "grounding: unsupported datum"}]}

        published = []
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(launderer, _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "",
            publish_fn=lambda a, p: published.append(a),
        )
        self.assertFalse(result["pass"])     # promoted to a strike → fail-closed
        self.assertEqual(len(published), 0)  # never published

    def test_untagged_residual_is_default_denied_and_fails_closed(self):
        # default-deny: a bare-string (untagged) residual is NOT a proven non-blocking note → promoted
        # to a strike → fail-closed. The residual channel is trustworthy only for explicit tags.
        def untagged(artefato, complete_fn=None):
            return {"pass": True, "scores": {}, "strikes": [], "residual": ["minor: tighten the title"]}

        published = []
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(untagged, _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "",
            publish_fn=lambda a, p: published.append(a),
        )
        self.assertFalse(result["pass"])
        self.assertEqual(len(published), 0)

    def test_blocking_strike_never_becomes_residual_fails_closed(self):
        # R5/S1: a blocking finding is a STRIKE — it can never ship as a residual. Even with a
        # residual on the same verdict, the strike fails the close CLOSED (no publish, no proof).
        def striker_with_residual(artefato, complete_fn=None):
            return {"pass": False, "scores": {}, "strikes": ["correctness: claim X unsupported"],
                    "residual": ["minor: tighten the title"]}

        published = []
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(striker_with_residual, _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "",
            publish_fn=lambda a, p: published.append(a),
        )
        self.assertFalse(result["pass"])      # blocking → fail-closed
        self.assertEqual(len(published), 0)   # never published
        self.assertNotIn("residual", result)  # a failed close mints no proof → no residual channel

    def test_blocking_residual_without_keyword_markers_still_fails_closed(self):
        # Codex S1 review #2: a blocking factual finding worded to dodge any keyword list, tagged
        # non_blocking but with NO cosmetic category, must STILL fail closed — the allowlist gates on
        # the structured category, never on the note text.
        def sneaky(artefato, complete_fn=None):
            return {"pass": True, "scores": {}, "strikes": [], "residual": [
                {"severity": "non_blocking",
                 "note": "the chart says E2 beat DS1, but the cited run shows DS1 higher"}]}

        published = []
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(sneaky, _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "",
            publish_fn=lambda a, p: published.append(a),
        )
        self.assertFalse(result["pass"])     # no cosmetic category → default-denied → fail-closed
        self.assertEqual(len(published), 0)

    def test_noncosmetic_category_residual_fails_closed(self):
        # even an explicit category NOT on the cosmetic allowlist (e.g. "evidence") is denied.
        def miscategorized(artefato, complete_fn=None):
            return {"pass": True, "scores": {}, "strikes": [], "residual": [
                {"severity": "non_blocking", "category": "evidence", "note": "a small data caveat"}]}

        published = []
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(miscategorized, _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "",
            publish_fn=lambda a, p: published.append(a),
        )
        self.assertFalse(result["pass"])
        self.assertEqual(len(published), 0)

    def test_production_parser_path_blocking_residual_fails_closed(self):
        # Codex S1 review [high]: drive the CANONICAL reviewers through complete_fn JSON — a blocking
        # finding in `residual` must survive _parse_verdict, be promoted to a strike by the sanitizer,
        # and fail the close CLOSED (the production path, not just injected reviewers).
        blocking_json = ('{"pass": true, "scores": {}, "strikes": [], "residual": '
                         '[{"severity": "non_blocking", "note": "grounding: unsupported datum"}]}')
        published = []
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(close.feynman_review, close.regular_review),
            complete_fn=lambda *a, **k: blocking_json,
            publish_fn=lambda a, p: published.append(a),
        )
        self.assertFalse(result["pass"])     # blocking residual → strike → fail-closed
        self.assertEqual(len(published), 0)

    def test_production_parser_path_reviewer_residual_promoted_to_strike(self):
        # on the production parser path too, a reviewer-authored residual (any tag) is promoted to a
        # strike and fails closed — never trusted as non-blocking (Codex S1 review #7).
        ok_json = ('{"pass": true, "scores": {}, "strikes": [], "residual": '
                   '[{"severity": "non_blocking", "category": "formatting", "note": "minor: spacing nit"}]}')
        published = []
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(close.feynman_review, close.regular_review),
            complete_fn=lambda *a, **k: ok_json,
            publish_fn=lambda a, p: published.append(a),
        )
        self.assertFalse(result["pass"])
        self.assertEqual(len(published), 0)

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
        # improve_fn revises the draft; the gating close mints the proof on the REVISED artefato, so
        # what publishes is provably what the reviewers passed. An issue drives the refinement (R7:
        # the loop engages because there's something to resolve, then converges once it's refined).
        def improve_fn(art, feedback):
            return {**art, "content": {"sections": [{"title": "Refined", "blocks": [
                {"type": "paragraph", "text": "improved from the reviewers' feedback."}]}]}}

        # canonical reviewers (so the proof carries their identities for verify_proof), driven by a
        # completer that strikes UNTIL the refined draft appears in the review prompt, then passes.
        def completer(prompt, *a, **k):
            if "Refined" in str(prompt):
                return '{"pass": true, "scores": {}, "strikes": []}'
            return '{"pass": false, "scores": {}, "strikes": ["needs refinement"]}'

        published = []

        def publish_fn(art, proof):
            published.append((art, proof))

        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(close.feynman_review, close.regular_review),
            complete_fn=completer, publish_fn=publish_fn,
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

    def test_improve_rounds_overrides_the_backstop(self):
        # improve_rounds overrides IMPROVE_BACKSTOP as the cap. Use a loop that makes progress every
        # round (issues shrink, so the patience/churn detector never trips) starting from more issues
        # than the cap, so improve_rounds=3 is what stops it — at 3, not the default backstop.
        rounds = {"n": 0}

        def countdown(artefato, complete_fn=None):
            rounds["n"] += 1
            remaining = max(0, 20 - (rounds["n"] - 1))
            return {"pass": False, "scores": {},
                    "strikes": [f"issue-{i}" for i in range(remaining)], "overall": 2.0}

        calls = {"count": 0}

        def improve_fn(art, feedback):
            calls["count"] += 1
            return {**art, "content": {"sections": [{"title": f"d{calls['count']}", "blocks": [
                {"type": "paragraph", "text": f"changed {calls['count']}."}]}]}}

        art = _conformant_artefato()
        close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(countdown, _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "", improve_fn=improve_fn, improve_rounds=3,
        )
        self.assertEqual(calls["count"], 3)


class DischargePersistsAcrossRounds(unittest.TestCase):
    """R9 (S4): a finding RESOLVED in an earlier round (raised, then absent once the draft changed) is
    STAMPED discharged and not re-litigated in the same terms by a later round — anti stochastic
    re-emergence (the roberto livelock: a flaky reviewer re-raising a cleared strike forever). Discharge
    is for the STOCHASTIC reviewer strikes only; genus violations are deterministic and never discharged.
    It combines with R7 (cap) and R5 so the loop converges instead of running to the backstop."""

    @staticmethod
    def _changing_improve():
        calls = {"count": 0}

        def improve(art, feedback):
            calls["count"] += 1
            # changes the draft each round (so it's not a plateau) while staying genus-conformant.
            return {**art, "content": {"sections": [{"title": "Body", "blocks": [
                {"type": "paragraph", "text": f"revision {calls['count']}."}]}]}}
        improve.calls = calls
        return improve

    @staticmethod
    def _alternating_reviewer():
        # call 1:[A]  call 2:[B]  call 3:[A]  call 4:[B] ... — each strike is RESOLVED the round it is
        # absent, then RE-EMERGES the next round in the same terms (the receding-target trap).
        calls = {"n": 0}

        def reviewer(artefato, complete_fn=None):
            calls["n"] += 1
            strike = "issue-A" if calls["n"] % 2 == 1 else "issue-B"
            return {"pass": False, "scores": {}, "strikes": [strike], "overall": 2.0}
        reviewer.calls = calls
        return reviewer

    def test_reemergent_strike_stops_the_improve_loop_churning(self):
        # the core R9 win (anti-livelock): WITHOUT discharge the alternating re-emergence never reaches
        # issue_count 0 → the improve loop churns to IMPROVE_BACKSTOP (roberto's 15 rounds, "saiu na marra").
        # WITH discharge each strike is stamped resolved the round it goes absent and its re-emergence is
        # suppressed, so the loop CONVERGES in a couple of rounds instead of burning the whole cap.
        improve = self._changing_improve()
        art = _conformant_artefato()
        close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(self._alternating_reviewer(), _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "", improve_fn=improve,
        )
        self.assertLessEqual(improve.calls["count"], 3)                  # converged fast …
        self.assertLess(improve.calls["count"], close.IMPROVE_BACKSTOP)  # … did NOT churn to the cap

    def test_flaky_absence_then_gate_reraise_fails_closed(self):
        # Codex S4 #1 (no proof bypass): a strike raised, ABSENT for one improved round (a reviewer
        # false-negative, NOT a real fix), then RE-RAISED at the authoritative gate must FAIL CLOSED and
        # never publish — discharge is loop-only; the gate requires the current reviewers to be clean.
        rounds = {"n": 0}

        def flaky_then_gate(artefato, complete_fn=None):
            rounds["n"] += 1
            # call 1: A ; call 2: absent (flaky miss) ; call 3+ (incl. the gate): A re-raised, never resolved
            return ({"pass": True, "scores": {}, "strikes": [], "overall": 4.0}
                    if rounds["n"] == 2 else
                    {"pass": False, "scores": {}, "strikes": ["issue-A"], "overall": 2.0})

        published = []
        improve = self._changing_improve()
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(flaky_then_gate, _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "", improve_fn=improve,
            publish_fn=lambda a, p: published.append(a),
        )
        self.assertFalse(result.get("pass"))
        self.assertEqual(len(published), 0)

    def test_persistent_strike_is_never_discharged(self):
        # guard against over-suppression: a strike that is ALWAYS raised (never resolved by any round) is a
        # real unresolved issue — it must NEVER be discharged, so the close fails closed (never mints).
        published = []
        improve = self._changing_improve()
        art = _conformant_artefato()
        result = close.run_close(
            art, produce_fn=lambda: art,
            reviewers=(_reviewer_always_strikes(), _reviewer_always_passes()),
            complete_fn=lambda *a, **k: "", improve_fn=improve,
            publish_fn=lambda a, p: published.append(a),
        )
        self.assertFalse(result.get("pass"))
        self.assertEqual(len(published), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
