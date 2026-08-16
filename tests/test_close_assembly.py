"""S-ATTEST (conductor integration, Goal 3 slice 2) — the close-owned, unforgeable assembly
attestation. Verifies the deep-dive genus OBLIGATION (A2/A6/A7), the genus-split defaulting, and the
honest NG7 residual (A8c). Asserts ONLY on `assembly-grounding:*` violations (other genus checks are
orthogonal here)."""
# NOTA (2026-08-16, issue #612): 18 testes deste arquivo foram removidos por decisão
# do operador. Eles cobravam a atestação de assembly (mint/sign/spec-digest) — API que NUNCA existiu em tools/ em commit
# algum. Não eram testes envelhecidos: chegaram órfãos em 401feee, vindos de uma
# árvore que ainda acreditava numa feature que be3aea5 ("Rollback failed genus rite
# rollout") já havia revertido, levando o código e deixando os testes.
#
# A especificação que eles descreviam está preservada na issue #612 — apagá-la daqui
# não a perde. O que sobrou neste arquivo cobre código que EXISTE e passa.

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


class GenusSplitDefaulting(unittest.TestCase):

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




