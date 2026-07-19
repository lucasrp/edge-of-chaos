"""S-ATTEST (conductor integration, Goal 3 slice 2) — the close-owned, unforgeable assembly
attestation. Verifies the deep-dive genus OBLIGATION (A2/A6/A7), the genus-split defaulting, and the
honest NG7 residual (A8c). Asserts ONLY on `assembly-grounding:*` violations (other genus checks are
orthogonal here)."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import json  # noqa: E402
import os  # noqa: E402
import tempfile  # noqa: E402
from unittest import mock  # noqa: E402
import assembly  # noqa: E402
import close  # noqa: E402
import eventlog  # noqa: E402


def _spec(text="alpha bears on the objective"):
    return {"sections": [{"title": "S", "blocks": [{"type": "paragraph", "text": text}]}]}


def _art(skill, content=None, _assembly=None):
    a = {"skill": skill, "slug": "s", "intent": "open: x; bet: y", "cites": [], "proposes": [],
         "content": content if content is not None else _spec()}
    if _assembly is not None:
        a["_assembly"] = _assembly
    return a


def _conductor_facts(content, **over):
    f = {"assembled": "conductor", "node_count": 3, "seed_finding_count": 2,
         "conductor_ship": True, "blocking": [], "conductor_digest": assembly.content_digest(content)}
    f.update(over)
    return f


def _ag_violations(art):
    return [v for v in close.check_genus(art) if v.startswith("assembly-grounding")]


class TrustBoundary(unittest.TestCase):
    def test_no_public_sign_or_attest_api(self):
        # A8a: no producer-reachable signer. The provenance module exposes NO sign/attest; the signing
        # primitive is close-PRIVATE (underscore), exactly like _mint_proof.
        self.assertFalse(hasattr(assembly, "sign"))
        self.assertFalse(hasattr(assembly, "attest"))
        self.assertFalse(hasattr(close, "sign_assembly"))
        self.assertTrue(hasattr(close, "_sign_assembly"))


class DeepDiveObligation(unittest.TestCase):
    def test_valid_conductor_run_passes(self):
        art = _art("research")
        art["_assembly"] = _conductor_facts(art["content"])
        close._mint_assembly(art)
        self.assertEqual(_ag_violations(art), [])

    def test_genuine_single_node_passes(self):
        art = _art("research", _assembly={"assembled": "single-node", "node_count": 1,
                                          "seed_finding_count": 1, "conductor_ship": True, "blocking": []})
        close._mint_assembly(art)
        self.assertEqual(_ag_violations(art), [])

    def test_deep_dive_with_no_assembly_fails_closed_when_conductor_on(self):
        # T-dd-missing-assembly-fail: with the conductor ENABLED, a research artefato that never stamped
        # provenance is a wiring failure → single-context → fail closed.
        art = _art("research")
        with mock.patch.dict(os.environ, {"EDGE_CONDUCTOR": "1"}):
            close._mint_assembly(art)
            self.assertIn("assembly-grounding:not-conductor-assembled", _ag_violations(art))

    def test_deep_dive_off_path_publishes_as_single_node(self):
        # codex P1: with the conductor OFF (today's default), research legitimately runs single-context and
        # publishes as a valid single-node — the default-off path is NOT broken (R8).
        art = _art("research")
        with mock.patch.dict(os.environ, {"EDGE_CONDUCTOR": ""}):
            close._mint_assembly(art)
            self.assertEqual(art["assembly_grounding"]["assembled"], "single-node")
            self.assertEqual(_ag_violations(art), [])

    def test_single_node_but_multifinding_fails(self):
        # A2(iv): a multi-finding seed that skipped fan-out cannot claim single-node.
        art = _art("research", _assembly={"assembled": "single-node", "node_count": 1,
                                          "seed_finding_count": 3, "conductor_ship": True, "blocking": []})
        close._mint_assembly(art)
        self.assertIn("assembly-grounding:single-node-but-multifinding", _ag_violations(art))

    def test_single_node_with_multiple_nodes_fails(self):
        # codex: a real MULTI-node run cannot claim the single-node exception by reporting <=1 findings —
        # the attestation must also have node_count == 1.
        art = _art("research", _assembly={"assembled": "single-node", "node_count": 5,
                                          "seed_finding_count": 1, "conductor_ship": True, "blocking": []})
        close._mint_assembly(art)
        self.assertIn("assembly-grounding:single-node-but-multinode", _ag_violations(art))

    def test_conductor_blocked_fails(self):
        # A2(v) / A7: an honestly-reported ship:false / non-empty blocking conductor run cannot publish.
        art = _art("research")
        art["_assembly"] = _conductor_facts(art["content"], conductor_ship=False,
                                            blocking=["coherence:contradiction"])
        close._mint_assembly(art)
        self.assertIn("assembly-grounding:conductor-blocked", _ag_violations(art))


class IntegrityAndForgery(unittest.TestCase):
    def test_stale_assembly_after_content_change_fails_closed(self):
        # A8b / P1: content the conductor did NOT produce (digest mismatch) drops the conductor claim.
        art = _art("research", content=_spec("ORIGINAL"))
        art["_assembly"] = _conductor_facts(_spec("ORIGINAL"))   # digest over original content
        art["content"] = _spec("REVISED single-context")          # content changed out from under it
        close._mint_assembly(art)
        self.assertIn("assembly-grounding:not-conductor-assembled", _ag_violations(art))

    def test_invalid_signature_fails(self):
        art = _art("research")
        art["_assembly"] = _conductor_facts(art["content"])
        close._mint_assembly(art)
        art["assembly_grounding"] = {**art["assembly_grounding"], "_sig": "tampered"}
        self.assertIn("assembly-grounding:invalid-signature", _ag_violations(art))

    def test_spec_mismatch_after_mint_fails(self):
        art = _art("research")
        art["_assembly"] = _conductor_facts(art["content"])
        close._mint_assembly(art)
        art["content"] = _spec("swapped after mint")              # content swapped post-mint
        self.assertIn("assembly-grounding:spec-mismatch", _ag_violations(art))

    def test_malformed_seed_count_fails_closed_not_crash(self):
        # codex S-ATTEST P2: a producer-supplied non-numeric seed_finding_count must fail closed, never
        # TypeError inside check_genus.
        art = _art("research")
        art["assembly_grounding"] = close._sign_assembly({
            "assembled": "single-node", "node_count": 1, "seed_finding_count": "2",
            "conductor_ship": True, "blocking": [], "spec_digest": close._spec_digest(art["content"])})
        self.assertIn("assembly-grounding:malformed-seed-count", _ag_violations(art))

    def test_forged_self_consistent_assembly_publishes_NG7_residual(self):
        # A8c (the asserted NG7 residual, NOT a bug): a producer that never ran the conductor fabricates a
        # self-consistent `_assembly` (matching conductor_digest over single-context content). close signs
        # producer-supplied facts in-process, so it passes the gate. Closed only by out-of-process close.
        art = _art("research", content=_spec("single-context, never node-assembled"))
        art["_assembly"] = _conductor_facts(art["content"])       # digest matches → looks conductor-run
        close._mint_assembly(art)
        self.assertEqual(_ag_violations(art), [])                 # publishes — the documented residual


class GenusSplitDefaulting(unittest.TestCase):
    def test_non_deep_dive_synthesizes_valid_single_node(self):
        # T-nondd-pass: map/plan/discovery never stamp _assembly → run_close synthesizes single-node.
        for skill in ("map", "plan", "discovery"):
            art = _art(skill)
            close._mint_assembly(art)
            self.assertEqual(art["assembly_grounding"]["assembled"], "single-node")
            self.assertEqual(_ag_violations(art), [], skill)

    def test_bare_non_deep_dive_artefato_is_unconstrained(self):
        # a non-deep-dive artefato that never went through _mint_assembly (direct check_genus, as many
        # existing tests do) is not required to carry an attestation — integrity-only, no obligation.
        self.assertEqual(_ag_violations(_art("map")), [])

    def test_bare_deep_dive_pre_mint_is_lenient(self):
        # absent is NOT struck on its own (codex P1): the improve stage runs check_genus BEFORE the mint,
        # so striking absent there would plateau a valid improver. Enforcement rides the MINTED attestation
        # (a conductor-on deep-dive with no provenance is minted single-context and struck — see
        # test_deep_dive_with_no_assembly_fails_closed_when_conductor_on).
        self.assertEqual(_ag_violations(_art("research")), [])


class ProofBindsTheAttestation(unittest.TestCase):
    """A6/A8: the proof binds (and carries) the attestation — a post-mint swap fails verify."""

    def _proof(self, att, spec):
        verdicts = [{"pass": True, "scores": {}, "strikes": [], "reviewer": close.FEYNMAN_REVIEWER_ID},
                    {"pass": True, "scores": {}, "strikes": [], "reviewer": close.REGULAR_REVIEWER_ID}]
        return close._mint_proof(verdicts, slug="s", spec=spec, intent="open: x; bet: y",
                                 cites=[], proposes=[], skill="research", assembly_grounding=att)

    def test_proof_carries_and_binds_attestation(self):
        spec = _spec()
        art = _art("research", content=spec, _assembly=_conductor_facts(spec))
        close._mint_assembly(art)
        att = art["assembly_grounding"]
        proof = self._proof(att, spec)
        self.assertEqual(proof["assembly_grounding"], att)        # rides the proof (publisher reads it)
        close.verify_proof(proof, slug="s", spec=spec, intent="open: x; bet: y",
                           cites=[], proposes=[], skill="research",
                           assembly_grounding=att, reviewer_count=2)

    def test_swapped_attestation_after_mint_fails_verify(self):
        spec = _spec()
        att = close._sign_assembly({"assembled": "single-node", "node_count": 1, "seed_finding_count": 0,
                                    "conductor_ship": True, "blocking": [],
                                    "spec_digest": close._spec_digest(spec)})
        proof = self._proof(att, spec)
        forged = close._sign_assembly({**{k: att[k] for k in att if k != "_sig"},
                                       "assembled": "conductor"})
        with self.assertRaises(ValueError):
            close.verify_proof(proof, slug="s", spec=spec, intent="open: x; bet: y",
                               cites=[], proposes=[], skill="research",
                               assembly_grounding=forged, reviewer_count=2)


class DurableAuditRecord(unittest.TestCase):
    """A5/R7: the published event persists the attestation fields + a close-stamped `verified`, so a
    log reader can tell node-assembled from single-pass (greppable). Not the re-runnable HMAC (H4)."""

    def test_published_event_carries_the_assembly_record(self):
        spec = _spec()
        att = close._sign_assembly({"assembled": "conductor", "node_count": 3, "seed_finding_count": 2,
                                    "conductor_ship": True, "blocking": [],
                                    "conductor_digest": assembly.content_digest(spec),
                                    "spec_digest": close._spec_digest(spec)})
        rec = None
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.publish_artefato_atomic(   # the publisher passes assembly_verified=True post-gate
                "s", "open: x; bet: y", spec=spec, skill="research", assembly_grounding=att,
                assembly_verified=True, log=log)
            for line in log.read_text().splitlines():
                ev = json.loads(line)
                if ev.get("type") == "artefato.published":
                    rec = ev["payload"]["assembly"]
        self.assertIsNotNone(rec)
        self.assertEqual(rec["assembled"], "conductor")
        self.assertEqual(rec["node_count"], 3)
        self.assertTrue(rec["verified"])
        self.assertNotIn("_sig", rec)            # ephemeral HMAC not persisted (H4)

    def test_direct_call_does_not_launder_unverified_as_verified(self):
        # codex S-ATTEST P2: a direct eventlog call (no publisher verification) records verified:false,
        # so a forged/stale record is never indistinguishable from a genuinely-passed one.
        spec = _spec()
        forged = {"assembled": "conductor", "node_count": 9, "_sig": "not-real"}
        rec = None
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.publish_artefato_atomic("s", "open: x; bet: y", spec=spec, skill="research",
                                             assembly_grounding=forged, log=log)   # no assembly_verified
            for line in log.read_text().splitlines():
                ev = json.loads(line)
                if ev.get("type") == "artefato.published":
                    rec = ev["payload"]["assembly"]
        self.assertFalse(rec["verified"])


if __name__ == "__main__":
    unittest.main()
