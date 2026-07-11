"""Vertical acceptances for generated portfolio views and legacy migration."""
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog  # noqa: E402
import portfolio  # noqa: E402


FIXTURE = REPO / "tests" / "fixtures" / "portfolio-dogfood-20260711.md"


def _fixture_ticket_rows():
    rows = {}
    for line in FIXTURE.read_text().splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 5 and re.fullmatch(r"M\d+\.\w+", cells[0]):
            rows[cells[0]] = {
                "titulo": cells[1], "estado": cells[2].strip("*"),
                "depends_on": cells[3], "rationale": cells[4],
            }
    return rows


class PortfolioRender(unittest.TestCase):
    def test_render_is_a_byte_deterministic_view_of_the_fold(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "log.jsonl"
            out = root / "views" / "portfolio.md"
            opened_map = eventlog.open_map(
                operacao="edge", titulo="Mapa vivo", rationale="Escolher o próximo passo",
                dispatch_id="d1", author="operador", log=log,
            )
            map_ref = f"edge/{opened_map['payload']['num']}"
            eventlog.open_ticket(
                map=map_ref, titulo="Pergunta decisiva", question="Qual ramo testar?",
                rationale="Reduzir a incerteza", dispatch_id="d1",
                author="operador", log=log,
            )

            self.assertEqual(portfolio.render(log, out=out), out)
            first = out.read_bytes()
            portfolio.render(log, out=out)

            self.assertEqual(out.read_bytes(), first)
            rendered = first.decode("utf-8")
            self.assertTrue(rendered.startswith("<!-- GERADO — edite via eventos"))
            self.assertIn("Mapa vivo", rendered)
            self.assertIn("Pergunta decisiva", rendered)
            self.assertIn("Reduzir a incerteza", rendered)


class PortfolioMigration(unittest.TestCase):
    def test_migrate_preserves_one_open_ticket_and_the_verbatim_source(self):
        source = """# Portfólio legado

## M1 — Descoberta (ATIVO)
*Visão: reduzir a incerteza antes de construir.*

| id | ticket | estado | depende de | rationale |
|---|---|---|---|---|
| M1.1 | Encontrar o seam | ABERTO, trivial | — | começar pelo caminho barato |
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "portfolio-legado.md"
            path.write_text(source)
            log = root / "log.jsonl"

            portfolio.migrate(path, log)

            folded = eventlog.wayfinds_at(log=log)
            self.assertEqual(len(folded["maps"]), 1)
            self.assertEqual(len(folded["tickets"]), 1)
            ticket = next(iter(folded["tickets"].values()))
            self.assertEqual(ticket["legacy_ref"], "M1.1")
            self.assertEqual(ticket["titulo"], "Encontrar o seam")
            self.assertEqual(ticket["rationale"], "começar pelo caminho barato")
            self.assertEqual(ticket["annotations"]["raw_state"], "ABERTO, trivial")
            self.assertEqual(eventlog.docs_at(log=log)["live"][0]["body"], source)

    def test_golden_fixture_migrates_with_semantic_equivalence(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"

            portfolio.migrate(FIXTURE, log)

            folded = eventlog.wayfinds_at(log=log)
            expected = _fixture_ticket_rows()
            by_legacy = {ticket["legacy_ref"]: ticket
                         for ticket in folded["tickets"].values()}
            self.assertEqual(set(by_legacy), set(expected))
            self.assertEqual(len(folded["tickets"]), len(expected))
            self.assertEqual(len(by_legacy), 24)

            legacy_by_ulid = {ticket["ulid"]: ticket["legacy_ref"]
                              for ticket in by_legacy.values()}
            for legacy_ref, row in expected.items():
                ticket = by_legacy[legacy_ref]
                self.assertEqual(ticket["titulo"], row["titulo"])
                self.assertEqual(ticket["rationale"], row["rationale"])
                if row["estado"].startswith("FECHADO"):
                    self.assertEqual(ticket["estado"], "closed")
                    self.assertEqual(ticket["fecho"]["valencia"], "inconclusive")
                    self.assertEqual(ticket["fecho"]["resolucao"], row["estado"])
                else:
                    self.assertEqual(ticket["estado"], "open")

            self.assertEqual(by_legacy["M2.8"]["tier"], "llm_judged")
            self.assertEqual(by_legacy["M2.8"]["author"], "edge")
            self.assertEqual(
                [legacy_by_ulid[ref] for ref in by_legacy["M1.7"]["blocked_by"]],
                ["M1.5", "M1.6"],
            )
            self.assertEqual(
                [legacy_by_ulid[ref] for ref in by_legacy["M4.3"]["blocked_by"]],
                ["M4.2"],
            )
            self.assertIn("dig-prior-art",
                          by_legacy["M2.5"]["annotations"]["raw_state"])
            self.assertIn("prune não existe",
                          by_legacy["M2.7"]["annotations"]["raw_state"])
            self.assertTrue(by_legacy["M1.4"]["annotations"]["raw_state"].startswith(
                "SUSPENSA como confirmatória"
            ))
            self.assertEqual(by_legacy["M2.8"]["annotations"]["raw_state"],
                             "PROPOSTO — autor: edge")
            self.assertEqual(by_legacy["M3.2"]["annotations"]["raw_state"],
                             "ABERTO — CONTIGO")
            self.assertEqual(by_legacy["M3.4"]["annotations"]["raw_state"],
                             "ABERTO, DESBLOQUEADO")
            self.assertEqual(by_legacy["M3.5"]["annotations"]["raw_state"],
                             "ABERTO, trivial")

            paused = [item for item in folded["maps"].values()
                      if item["estado"] == "pausado"]
            self.assertEqual({item["titulo"] for item in paused}, {
                "grok-as-builder (free tier morreu; achado registrado; retomar só por decisão tua)",
                "PR #129 (aguarda teu merge)",
                "rotação da XAI key (recomendada, contigo)",
                "#131 spec formal (alimentada por M2.5/M2.6)",
            })
            self.assertEqual(eventlog.docs_at(log=log)["live"][0]["body"],
                             FIXTURE.read_text())

    def test_rerunning_the_same_migration_refuses_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            portfolio.migrate(FIXTURE, log)
            before = eventlog.read(log=log)

            with self.assertRaisesRegex(ValueError, "already migrated"):
                portfolio.migrate(FIXTURE, log)

            self.assertEqual(eventlog.read(log=log), before)


class DirectionGate(unittest.TestCase):
    def test_other_dispatch_and_direction_report_do_not_satisfy_the_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.open_map(
                operacao="edge", titulo="Mapa alheio", rationale="Outro gesto",
                dispatch_id="dispatch-other", author="grill", log=log,
            )
            eventlog.report_direction("Prosa sem gesto do dispatch alvo", log=log)

            with self.assertRaisesRegex(ValueError, "portfolio diff|confirmed"):
                portfolio.direction_gate("dispatch-target", log)

    def test_matching_portfolio_confirmation_satisfies_the_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.confirm_portfolio(
                rationale="Li os mapas; nada muda",
                dispatch_id="dispatch-target", log=log,
            )

            self.assertTrue(portfolio.direction_gate("dispatch-target", log))

    def test_map_state_from_the_exact_dispatch_satisfies_the_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened = eventlog.open_map(
                operacao="edge", titulo="Mapa", rationale="Abrir",
                dispatch_id="dispatch-open", author="grill", log=log,
            )
            eventlog.set_map_state(
                ref=f"edge/{opened['payload']['num']}", estado="pausado",
                rationale="Pausar conscientemente", dispatch_id="dispatch-target",
                author="grill", log=log,
            )

            self.assertTrue(portfolio.direction_gate("dispatch-target", log))


if __name__ == "__main__":
    unittest.main()
