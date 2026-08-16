"""Nenhuma ferramenta lê o fenótipo por literal do repositório — ADR-0015, um seam só.

Num install com genótipo e home separados (o layout documentado), `agent.yaml` vive no HOME.
Um `REPO / "agent.yaml"` no genótipo lê um arquivo que não existe — e o dano é sempre silencioso,
porque quem lê o fenótipo costuma fazê-lo em best-effort:

  - wiki_render.render_model  -> FileNotFoundError, "wiki render skipped"
  - sweep._cfg                -> lookback do filme cai no default
  - _beat                     -> heartbeat lido do lugar errado
  - publisher (Genesis MERGE) -> try/except engole, e o nó de identidade nasce SEM codename e
                                 SEM voice (observado ao vivo: o Neo4j avisou "property `codename`
                                 does not exist" na consulta do Genesis de um install recém-nascido)

Este teste é estrutural de propósito: os quatro sítios foram encontrados um a um, por sintomas
diferentes, ao longo de um único onboarding. O que impede o quinto não é mais um caso de teste — é
a invariante.
"""
import pathlib
import re
import unittest

TOOLS = pathlib.Path(__file__).resolve().parent.parent / "tools"
PATTERN = re.compile(r'REPO\s*/\s*["\']agent\.yaml["\']')


class PhenotypeResolvesAtTheSeam(unittest.TestCase):
    def test_no_tool_reads_the_phenotype_by_repo_literal(self):
        offenders = []
        for path in sorted(TOOLS.glob("*.py")):
            for n, line in enumerate(path.read_text().splitlines(), 1):
                if PATTERN.search(line) and not line.lstrip().startswith("#"):
                    offenders.append(f"{path.name}:{n}: {line.strip()}")
        self.assertEqual(
            offenders, [],
            "o fenótipo tem que resolver por _identity.identity_path('agent.yaml') — um "
            "literal do repo lê o arquivo errado num install geno/home separado:\n  "
            + "\n  ".join(offenders))


if __name__ == "__main__":
    unittest.main()
