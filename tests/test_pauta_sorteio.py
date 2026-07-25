"""Pauta R1 — o sorteio (spec assinada: docs/agencia/pauta-tabela-normativa.md §2/§3.1).

{objeto, abordagem} sorteados INDEPENDENTES com pesos uniformes, ANTES de ler o wake — a
leitura já sai mirada. Voz trava campos (campo travado não é sorteado; célula travada ainda
é célula). Sem blocklist de células: {ser, ser} é sorteável (~1/28). Puro: nenhum evento.
"""
import random
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import pauta  # noqa: E402


class MatrixIsTheSignedTable(unittest.TestCase):
    def test_axes_carry_the_signed_values_including_coringa(self):
        self.assertEqual(pauta.OBJETOS, ("mundo", "atividade", "si", "ser"))
        self.assertEqual(
            pauta.ABORDAGENS,
            ("fog", "operacional", "estrategico", "meta_dica",
             "tempo_gasto", "curiosidade", "ser"))


class DrawIsUniformAndIndependent(unittest.TestCase):
    def test_uniform_over_both_axes_and_full_coringa_reachable(self):
        rng = random.Random(42)
        n = 2800  # esperado: 700/objeto, 400/abordagem, ~100 {ser,ser}
        obj, abo, ser_ser = {}, {}, 0
        for _ in range(n):
            cell = pauta.sortear(rng=rng)
            obj[cell["objeto"]] = obj.get(cell["objeto"], 0) + 1
            abo[cell["abordagem"]] = abo.get(cell["abordagem"], 0) + 1
            if cell["objeto"] == "ser" and cell["abordagem"] == "ser":
                ser_ser += 1
        for o in pauta.OBJETOS:
            self.assertGreater(obj.get(o, 0), 700 * 0.8, f"objeto {o} sub-representado")
            self.assertLess(obj.get(o, 0), 700 * 1.2, f"objeto {o} sobre-representado")
        for a in pauta.ABORDAGENS:
            self.assertGreater(abo.get(a, 0), 400 * 0.75, f"abordagem {a} sub-representada")
            self.assertLess(abo.get(a, 0), 400 * 1.25, f"abordagem {a} sobre-representada")
        self.assertGreater(ser_ser, 0, "sem blocklist: {ser,ser} tem de ser sorteável")

    def test_draw_is_pure_no_log_parameter(self):
        # O sorteio roda ANTES do wake e não pena evento — a assinatura não aceita log.
        import inspect
        self.assertNotIn("log", inspect.signature(pauta.sortear).parameters)


class VozLocksFields(unittest.TestCase):
    def test_locked_field_is_never_drawn(self):
        for seed in range(30):
            cell = pauta.sortear({"objeto": "si"}, rng=random.Random(seed))
            self.assertEqual(cell["objeto"], "si")
            self.assertIn(cell["abordagem"], pauta.ABORDAGENS)
            self.assertEqual(cell["locked"], ["objeto"])

    def test_both_locked_is_still_a_cell(self):
        cell = pauta.sortear({"objeto": "mundo", "abordagem": "fog"})
        self.assertEqual((cell["objeto"], cell["abordagem"]), ("mundo", "fog"))
        self.assertEqual(cell["locked"], ["objeto", "abordagem"])

    def test_invalid_lock_fails_loud(self):
        with self.assertRaises(ValueError):
            pauta.sortear({"objeto": "balada"})
        with self.assertRaises(ValueError):
            pauta.sortear({"abordagem": "vibes"})

    def test_non_axis_constraints_do_not_lock_the_draw(self):
        cell = pauta.sortear({"tema": "X", "forma": "report", "origem": "voz"},
                             rng=random.Random(7))
        self.assertEqual(cell["locked"], [])
        self.assertIn(cell["objeto"], pauta.OBJETOS)


if __name__ == "__main__":
    unittest.main()
