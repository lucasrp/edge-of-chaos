"""S-COHERENCE (conductor integration, Goal 3 slice 4) — the cross-node coherence gate (Q5), wired
INTO the circuit-breaker so a coherence/diversity failure forces ship:false and rides the attestation.

Pass = zero coherence strikes AND diversity in-band. The coherence reviewer is INJECTED (the skill's own
whole-doc subagent), so the dark path / offline default is unchanged (coherence_fn=None => no check).
"""
# NOTA (2026-08-16, issue #612): 5 testes deste arquivo foram removidos por decisão
# do operador. Eles cobravam o gate de coerência com circuit breaker — API que NUNCA existiu em tools/ em commit
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
sys.path.insert(0, str(REPO / "tests"))
import conductor  # noqa: E402
import assembly  # noqa: E402
from test_conductor_circuit_breaker import _SEED, _OBJECTIVE, _writer  # noqa: E402 — known-good harness


class CircuitBreakerFoldsCoherenceAndDiversity(unittest.TestCase):

    def test_diversity_violation_is_advisory_not_a_hard_gate(self):
        # uncalibrated diversity over-fires on normal prose-only multi-node output, so it is REPORTED, never
        # a hard ship gate (codex review) — the coherence reviewer is the gate, not the self-bleu heuristic.
        cb = conductor.circuit_breaker({"diversity": {"violations": ["distinct-signatures 0.2 < 0.5"]}})
        self.assertTrue(cb["ship"])
        self.assertFalse(any(b.startswith("diversity:") for b in cb["blocking"]))

    def test_clean_ships(self):
        cb = conductor.circuit_breaker({"coherence_flags": [], "diversity": {"violations": []}})
        self.assertTrue(cb["ship"])


