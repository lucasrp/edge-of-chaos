"""quente — o 4º brief do wake (o SENTIR passivo): o construtor do insumo de dois trilhos.

Pins the PURE CORE of the input builder (bare python): ordinal-K selection of substantial
sessions (E1: turnos-op >=5 E chars-op >=1k), operator-prompt extraction (verbatim, cap 500c,
scaffolding filtered — trilho voz), and the two-rail bundle assembly (voz + âncoras mecânicas
injetadas). O leitor é um subagente (skills/quente); aqui só a máquina de preparar o insumo.
Proposta: docs/agencia/proposta-novo-wake.md (16k default, K=3 ordinal, dois trilhos).
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import quente  # noqa: E402


META = [  # (id, op_turns, op_chars, last_ts) — mais recente primeiro após seleção
    {"id": "s-novo", "op_turns": 20, "op_chars": 9000, "last": "2026-07-05T01:00:00Z"},
    {"id": "s-agente", "op_turns": 0, "op_chars": 0, "last": "2026-07-05T00:00:00Z"},
    {"id": "s-medio", "op_turns": 8, "op_chars": 2000, "last": "2026-07-03T10:00:00Z"},
    {"id": "s-raso", "op_turns": 2, "op_chars": 100, "last": "2026-07-02T10:00:00Z"},
    {"id": "s-velho", "op_turns": 30, "op_chars": 15000, "last": "2026-06-20T10:00:00Z"},
]


class TestOrdinalSelection(unittest.TestCase):
    def test_last_k_substantial_ordinal(self):
        """K=2: pega as 2 substanciais MAIS RECENTES; agente-only e rasa ficam fora."""
        sel = quente.select_sessions(META, k=2)
        self.assertEqual([s["id"] for s in sel], ["s-novo", "s-medio"])

    def test_wallclock_is_ceiling_not_ruler(self):
        """Teto wall-clock: sessão substancial FORA do teto não entra mesmo com K sobrando."""
        sel = quente.select_sessions(META, k=5, max_age_days=7,
                                     now="2026-07-05T02:00:00Z")
        self.assertNotIn("s-velho", [s["id"] for s in sel])
        self.assertEqual([s["id"] for s in sel], ["s-novo", "s-medio", "s-raso"][:2] if False
                         else ["s-novo", "s-medio"])  # só as substanciais dentro do teto


class TestVozRail(unittest.TestCase):
    TURNS = [
        ("user", "faz o X direito"),
        ("assistant", "feito"),
        ("user", "<system-reminder>lixo injetado</system-reminder>"),
        ("user", "heartbeat keep-warm: reporte"),
        ("user", "b" * 900),
    ]

    def test_prompts_verbatim_cap_and_filter(self):
        out = quente.operator_prompts(self.TURNS, cap=500)
        self.assertEqual(out[0], "faz o X direito")     # verbatim
        self.assertEqual(len(out), 2)                    # scaffolding/heartbeat fora
        self.assertEqual(len(out[1]), 500)               # cap aplicado


class TestBundle(unittest.TestCase):
    def test_two_rails_assembled(self):
        """O insumo carrega os DOIS trilhos rotulados — voz e âncoras — e nada de prosa nossa."""
        bundle = quente.build_input(
            sessions=[{"id": "s1", "prompts": ["oi", "faz Y"]}],
            anchors="## git log\nabc123 feat: x")
        self.assertIn("TRILHO VOZ", bundle)
        self.assertIn("faz Y", bundle)
        self.assertIn("ÂNCORAS MECÂNICAS", bundle)
        self.assertIn("abc123", bundle)


if __name__ == "__main__":
    unittest.main()
