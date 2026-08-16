"""Uma falha de ingest tem que ser ALTA no resumo do wake — não uma linha soterrada.

Caso de campo (2026-08-16): o modelo do extractor foi trocado por um que a dependência não
aceita (`graphiti_core` envia `reasoning.effort="minimal"` fixo; o modelo devolveu HTTP 400).
O efeito não foi degradação — foi apagão: a sessão inteira deixou de ser filmada.

O wake seguiu e reportou sucesso em todas as outras pernas. As falhas por episódio ERAM
impressas, uma a uma, e foi exatamente por isso que sumiram: soterradas num traço longo, com
todas as linhas de resumo seguintes ('communities consolidadas — 0 clusters') parecendo
normais. O operador não viu uma falha; viu calmaria. Só apareceu num grep.

Ingest é o órgão do qual todo o resto depende. Sua falha não pode custar um grep.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import sweep  # noqa: E402


class IngestFailureIsLoud(unittest.TestCase):
    def test_a_clean_run_says_nothing(self):
        self.assertIsNone(sweep._ingest_summary(3, []),
                          "sem falha não há linha — ruído em run limpo treina a ignorar a linha")

    def test_total_blackout_is_reported_with_the_first_cause(self):
        line = sweep._ingest_summary(
            0, ["session-abc: BadRequestError: 'minimal' is not supported"])
        self.assertIsNotNone(line)
        self.assertIn("FALHARAM", line)
        self.assertIn("1 de 1", line)
        self.assertIn("BadRequestError", line,
                      "a causa tem que vir junto: 'falhou' sem por quê ainda custa um grep")

    def test_partial_failure_shows_the_proportion(self):
        line = sweep._ingest_summary(2, ["session-y: TimeoutError: t"])
        self.assertIn("1 de 3", line,
                      "proporção, não contagem solta: 1 de 3 e 1 de 300 pedem reações diferentes")

    def test_the_summary_is_emitted_by_the_ingest_path(self):
        """O helper existir não basta — o caminho de ingest tem que chamá-lo."""
        source = (REPO / "tools" / "sweep.py").read_text()
        self.assertIn("_ingest_summary(len(", source)
        marker = source.index("def graphiti_ingest(")
        self.assertIn("_ingest_summary", source[marker:],
                      "graphiti_ingest tem que emitir o resumo, não só o módulo defini-lo")


if __name__ == "__main__":
    unittest.main()
