"""The close (ADR-0012/0013, review per ADR-0025).

Owner, 2026-11-01 (verbatim): "quero que o revisor só avise dos furos, e o edge pode ou corrigir
ou só mencionar a nota do revisor, à sua conveniencia".

`run_close` runs the MECHANICAL genus contract first (bounded bounce, `BOUNCE_MAX`), then ONE
advisory reviewer that only points out furos. The producer fixes each furo (`improve_fn`, called
once) or keeps it; kept furos ride a "Notas do revisor" section appended before the mint. The
review never blocks and never asks for another round. `run_loop2` is the producer-loop brake:
the critic converges, serendipity is advisory and bounded by `LOOP2_MAX_REOPENS`.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import _llm  # noqa: E402
import close  # noqa: E402

CLEAN = lambda *a, **k: '{"furos": []}'  # noqa: E731 — the real reviewer, no furo


def _reviewer_with(furos):
    """A canonical-identity reviewer stub returning fixed furos."""
    calls = {"count": 0}

    def reviewer(artefato, complete_fn=None):
        calls["count"] += 1
        return {"furos": list(furos)}

    reviewer.identity = close.REVIEWER_ID
    reviewer.calls = calls
    return reviewer


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


def _notes(art):
    return (art.get("content") or {}).get("reviewer_notes")


class Loop2Brake(unittest.TestCase):
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



class ReviewNeverBlocks(unittest.TestCase):
    """ADR-0025: the reviewer only warns. Furos never stop the publication and never trigger
    a second review round."""

    def test_furos_without_improve_fn_publish_with_every_note(self):
        published = []
        reviewer = _reviewer_with(["FURO 1: 29 vitorias sem fonte", "FURO 2: conclusao nao segue"])
        proof = close.run_close(_conformant_artefato(), produce_fn=lambda: None,
                                reviewer=reviewer, publish_fn=lambda a, p: published.append(a))
        self.assertTrue(proof["pass"])
        self.assertEqual(len(published), 1)
        self.assertEqual(reviewer.calls["count"], 1)          # one pass, never re-reviewed
        self.assertEqual(_notes(published[0]),
                         ["FURO 1: 29 vitorias sem fonte", "FURO 2: conclusao nao segue"])
        self.assertEqual(proof["reviewer_notes"], _notes(published[0]))

    def test_no_furo_publishes_without_a_notes_section(self):
        published = []
        close.run_close(_conformant_artefato(), produce_fn=lambda: None,
                        reviewer=_reviewer_with([]), publish_fn=lambda a, p: published.append(a))
        self.assertIsNone(_notes(published[0]))

    def test_broken_reviewer_degrades_to_a_note_never_a_block(self):
        def boom(artefato, complete_fn=None):
            raise RuntimeError("reviewer crashed")
        boom.identity = close.REVIEWER_ID
        published = []
        proof = close.run_close(_conformant_artefato(), produce_fn=lambda: None, reviewer=boom,
                                publish_fn=lambda a, p: published.append(a))
        self.assertTrue(proof["pass"])
        self.assertEqual(len(published), 1)
        self.assertIn("reviewer raised", proof["verdicts"][0]["degraded"])

    def test_unparseable_real_reviewer_answer_never_blocks(self):
        published = []
        proof = close.run_close(_conformant_artefato(), produce_fn=lambda: None,
                                complete_fn=lambda *a, **k: "ACCEPTANCE: FAIL",
                                publish_fn=lambda a, p: published.append(a))
        self.assertTrue(proof["pass"])
        self.assertEqual(len(published), 1)
        self.assertEqual(proof["verdicts"][0]["furos"], [])

    def test_infra_error_propagates_it_is_not_a_review(self):
        def no_quota(prompt):
            raise _llm.LLMTransportError("quota", "429")
        with self.assertRaises(_llm.LLMTransportError):
            close.run_close(_conformant_artefato(), produce_fn=lambda: None,
                            complete_fn=no_quota)


class ProducerFixesOrMentions(unittest.TestCase):
    """The producer decides each furo, at its convenience: fix it, or keep it and mention it."""

    def test_fixed_furos_leave_no_note(self):
        published = []

        def improve_fn(art, verdict):
            fixed = {**art, "content": {"sections": [{"title": "Body", "blocks": [
                {"type": "paragraph", "text": "the proof is bound to this exact payload, fixed."}]}]}}
            fixed["reviewer_notes"] = []              # every furo fixed
            return fixed

        proof = close.run_close(_conformant_artefato(), produce_fn=lambda: None,
                                reviewer=_reviewer_with(["FURO 1: vago"]), improve_fn=improve_fn,
                                publish_fn=lambda a, p: published.append(a))
        self.assertIsNone(_notes(published[0]))
        self.assertIn("fixed", str(published[0]["content"]))
        self.assertEqual(proof["reviewer_notes"], [])

    def test_kept_furo_appears_in_the_artefato_with_the_answer(self):
        published = []

        def improve_fn(art, verdict):
            self.assertEqual(verdict["furos"], ["FURO 1: vago", "FURO 2: sem fonte"])
            return {**art, "reviewer_notes": [
                {"furo": "FURO 2: sem fonte", "resposta": "o log da rodada nao foi guardado"}]}

        close.run_close(_conformant_artefato(), produce_fn=lambda: None,
                        reviewer=_reviewer_with(["FURO 1: vago", "FURO 2: sem fonte"]),
                        improve_fn=improve_fn, publish_fn=lambda a, p: published.append(a))
        self.assertEqual(_notes(published[0]),
                         ["FURO 2: sem fonte — Resposta: o log da rodada nao foi guardado"])
        self.assertNotIn("reviewer_notes", published[0])  # never leaks as a payload field

    def test_revision_without_a_decision_keeps_every_furo(self):
        published = []
        close.run_close(_conformant_artefato(), produce_fn=lambda: None,
                        reviewer=_reviewer_with(["FURO 1: vago"]),
                        improve_fn=lambda art, verdict: dict(art),
                        publish_fn=lambda a, p: published.append(a))
        self.assertEqual(_notes(published[0]), ["FURO 1: vago"])

    def test_crashing_or_genus_breaking_revision_is_discarded_not_a_block(self):
        for bad in (lambda art, v: (_ for _ in ()).throw(RuntimeError("x")),
                    lambda art, v: "not a dict",
                    lambda art, v: _genus_invalid_artefato(art["slug"])):
            published = []
            proof = close.run_close(_conformant_artefato(), produce_fn=lambda: None,
                                    reviewer=_reviewer_with(["FURO 1: vago"]), improve_fn=bad,
                                    publish_fn=lambda a, p: published.append(a))
            self.assertTrue(proof["pass"])
            self.assertEqual(published[0]["cites"], _conformant_artefato()["cites"])
            self.assertEqual(_notes(published[0]),
                             ["FURO 1: vago"])

    def test_the_digest_binds_the_notes_section(self):
        art = _conformant_artefato()
        proof = close.run_close(art, produce_fn=lambda: None,
                                reviewer=_reviewer_with(["FURO 1: vago"]))
        with self.assertRaises(ValueError):   # the original content (no notes) does not verify
            close.verify_proof(proof, slug=art["slug"], spec=art["content"],
                               intent=art["intent"], cites=art["cites"],
                               proposes=art["proposes"])


class ProofIsBoundAndUnforgeable(unittest.TestCase):
    """The minted proof is UNFORGEABLE and BOUND (Codex re-review #2/#3): a run_close-only token,
    a sha256 digest of the EXACT publish payload, and the canonical reviewer identity (the review
    ran). A hand-built dict, a proof for another payload, or a proof from a fake reviewer is
    rejected BEFORE any publish."""

    def _mint(self, art):
        return close.run_close(art, produce_fn=lambda: art, complete_fn=CLEAN)

    def _verify(self, proof, art, **over):
        kw = dict(slug=art["slug"], spec=art["content"], intent=art["intent"],
                  cites=art["cites"], proposes=art["proposes"])
        kw.update(over)
        close.verify_proof(proof, **kw)

    def test_minted_proof_carries_token_digest_and_the_verdict(self):
        art = _conformant_artefato()
        proof = self._mint(art)
        self.assertTrue(proof["pass"])
        self.assertIn("token", proof)
        self.assertIn("digest", proof)
        self.assertEqual(len(proof["verdicts"]), 1)
        self.assertEqual(proof["verdicts"][0]["reviewer"], close.REVIEWER_ID)
        self._verify(proof, art)

    def test_hand_built_proof_is_rejected_no_valid_token(self):
        art = _conformant_artefato()
        forged = {"pass": True, "verdicts": [{"reviewer": close.REVIEWER_ID}],
                  "digest": "whatever", "token": "guessed"}
        with self.assertRaises(ValueError):
            self._verify(forged, art)

    def test_proof_for_artefato_A_cannot_verify_artefato_B(self):
        art_a, art_b = _conformant_artefato("artefato-a"), _conformant_artefato("artefato-b")
        proof = self._mint(art_a)
        with self.assertRaises(ValueError):
            self._verify(proof, art_b)

    def test_proof_from_a_fake_reviewer_fails_identity(self):
        art = _conformant_artefato()
        proof = close.run_close(art, produce_fn=lambda: art,
                                reviewer=lambda a, complete_fn=None: {"furos": []})
        with self.assertRaises(ValueError):
            self._verify(proof, art)

    def test_mint_proof_is_not_a_public_attribute(self):
        self.assertFalse(hasattr(close, "mint_proof"))
        self.assertTrue(hasattr(close, "_mint_proof"))

    def test_altering_distills_or_skill_after_mint_fails_verify(self):
        art = _conformant_artefato()
        proof = self._mint(art)
        self._verify(proof, art, distills=art.get("distills"), skill=art.get("skill"))
        with self.assertRaises(ValueError):
            self._verify(proof, art, distills=[{"page": "poisoned"}])
        with self.assertRaises(ValueError):
            self._verify(proof, art, skill="a-different-skill")


class GenusRunsBeforeTheReview(unittest.TestCase):
    """The MECHANICAL genus contract still blocks: a violation bounces (bounded by BOUNCE_MAX)
    BEFORE the reviewer runs or any proof is minted — that is a check, not a review."""

    def test_genus_invalid_never_mints_and_bounces_then_hard_fails(self):
        produce_calls = {"count": 0}

        def produce_fn():
            produce_calls["count"] += 1
            return _genus_invalid_artefato()

        reviewer = _reviewer_with([])
        result = close.run_close(_genus_invalid_artefato(), produce_fn=produce_fn,
                                 reviewer=reviewer)
        self.assertFalse(result["pass"])
        self.assertNotIn("token", result)
        self.assertEqual(produce_calls["count"], close.BOUNCE_MAX)
        self.assertEqual(reviewer.calls["count"], 0)

    def test_genus_violation_blocks_publish_even_with_custom_publish_fn(self):
        published = []
        result = close.run_close(_genus_invalid_artefato(), produce_fn=_genus_invalid_artefato,
                                 reviewer=_reviewer_with([]),
                                 publish_fn=lambda a, p: published.append(a))
        self.assertFalse(result["pass"])
        self.assertEqual(published, [])


class GenusViolationsAreFedToReProduction(unittest.TestCase):
    """Codex P2 (#30) — a genus violation (incl. a rich-rite floor strike) is FED to
    `improve_fn` so the draft is re-produced; without `improve_fn` it is the static bounce."""

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
        seen = []

        def improve_fn(art, feedback):
            seen.append(feedback)
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
        result = close.run_close(self._shallow_developed_prose(),
                                 produce_fn=self._shallow_developed_prose, complete_fn=CLEAN,
                                 improve_fn=improve_fn, publish_fn=lambda a, p: published.append(a))
        self.assertTrue(result["pass"])
        self.assertEqual(len(published), 1)
        self.assertIn("rich-rite", str(seen))

    def test_without_improve_fn_genus_violation_is_the_static_bounce(self):
        result = close.run_close(self._shallow_developed_prose(),
                                 produce_fn=self._shallow_developed_prose, complete_fn=CLEAN)
        self.assertFalse(result["pass"])
        self.assertTrue(any(v.startswith("rich-rite") for v in result["genus_violations"]))


if __name__ == "__main__":
    unittest.main()
