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


if __name__ == "__main__":
    unittest.main(verbosity=2)
