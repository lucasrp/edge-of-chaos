"""Story S5 — operator-sanctioned Idiom rename: ``insumos`` -> ``evidence``.

Guards two things at once:

1. The term ``insumos`` is gone from every file under ``skills/`` (the rename
   landed everywhere it occurred).
2. The CONTEXT.md glossary keeps **exactly** the same number of glossary entity
   headers it had before the rename — a count-preserving rename adds no NEW
   glossary entity (the no-new-entity fence). A rename keeps the count; an
   addition would bump it.
"""

import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(REPO, "skills")
CONTEXT = os.path.join(REPO, "CONTEXT.md")

# A glossary entity header is a line that *starts* with a bold span immediately
# followed by a colon at end-of-line, e.g. ``**Mentee**:`` — the term, then its
# definition on the lines below. Sentence fragments that merely begin with a
# bold span (a wrapped paragraph) have text after the colon and are excluded.
GLOSSARY_HEADER = re.compile(r"^\*\*[^*]+\*\*:\s*$", re.MULTILINE)

# Count captured at test-write time, AFTER auditing CONTEXT.md: 30 headers.
# CONTEXT.md does not define ``insumos`` as a glossary entry, so the rename
# touches no header here. The fence is against ACCIDENTAL drift: a deliberate,
# Voz-ratified glossary change bumps this pin in the same commit.
# 2026-06-10 glossary grill (+10): Beat/Heartbeat, Producer-skill, Close,
# Rich rite, Grill, Genotype, Install, Steer, Wake, Recall, Space-0 (Wake and
# Recall share the grill; Dispatch header count net unchanged) → 40.
# 2026-06-15 dashboard comms-model (#38, Voz-ratified): +3 glossary entities from
# the mentee↔edge communication model (Medium / Voz-tier / Directive / Vote) → 43.
# 2026-06-16 cortex omnipresent memory (Voz-ratified): +1 Usage signal (the implicit,
# off-truth-path read telemetry — distinct from value/correction feedback) → 44.
# 2026-07-03 grounding iteration S8 (R1.1, Voz-ratified): +1 Grounding (the claim↔evidence
# relation, traceable — the arc's naming deliverable in the Language section) → 45.
# 2026-08-16 (#620): o pin deixa de ser uma CONTAGEM e passa a ser o CONJUNTO DE NOMES.
# A contagem não pegou a perda de 13 entidades no merge 9221924 porque a ADR-0024 somou 9 no
# mesmo intervalo — as duas derivas quase se cancelaram e 45 -> 42 pareceu manutenção.
GLOSSARY_ENTITIES = {
    "Artefato / Artifact",
    "Assemble / Consolidação prévia",
    "Atividade / Activity",
    "Briefing",
    "Briefing",
    "Catálogo",
    "Close",
    "Consolidação de hipóteses / Hypothesis consolidation",
    "Convergence",
    "Coringa / serendipidade (`ser`)",
    "Corpus",
    "Cortex",
    "Curated",
    "Delta",
    "Direction",
    "Directive",
    "Dispatch",
    "Domain",
    "Envelhecimento / Aging",
    "Experiment / Experimento",
    "Gate de PROPOSTA / plan-gate",
    "Genotype",
    "Grill",
    "Grounding",
    "Harm potential",
    "Hypothesis",
    "Idiom",
    "Install",
    "Intent kernel",
    "Knowledge cluster",
    "Lint",
    "Medium / Meio",
    "Mentee",
    "Mineração / Mining",
    "Mundo / World",
    "PROPOSTA",
    "Pauta",
    "Producer-skill / Producer",
    "Recall",
    "Recap",
    "Rich rite / Rito rico",
    "Shortlist A",
    "Source feedback",
    "Source roadmap",
    "Space-0",
    "Standing page",
    "Steer",
    "Usage signal",
    "Vote",
    "Voz / Voice",
    "Wake",
    "Worthwhile content",
    "delta_voz / Redigest",
    "llm-wiki",
}

GLOSSARY_HEADER_NAMED = re.compile(r"^\*\*([^*]+)\*\*:\s*$", re.MULTILINE)


def _glossary_header_count(text):
    return len(GLOSSARY_HEADER.findall(text))


class NoInsumosRemain(unittest.TestCase):
    def test_no_insumos_in_skills_tree(self):
        offenders = []
        for root, _dirs, files in os.walk(SKILLS):
            for name in files:
                path = os.path.join(root, name)
                try:
                    with open(path, encoding="utf-8") as fh:
                        if "insumos" in fh.read():
                            offenders.append(path)
                except (UnicodeDecodeError, OSError):
                    # Binary or unreadable file cannot carry the term.
                    continue
        self.assertEqual(
            offenders,
            [],
            "files still contain 'insumos': %s" % offenders,
        )

    def test_glossary_entities_are_exactly_the_declared_set(self):
        """O pin é o CONJUNTO DE NOMES, não a contagem — e a diferença não é estilo.

        Até 2026-08-16 este guarda fixava um número (45). Ele não pegou a perda de 13 entidades
        no merge `9221924` porque a ADR-0024 adicionou 9 no mesmo intervalo: -13 e +9 viraram uma
        diferença de 4, pequena o bastante para parecer manutenção. Uma contagem sabe QUANTOS;
        só um conjunto sabe QUAIS. Ver issue #620.

        Quem adicionar ou aposentar uma entidade acrescenta ou remove o nome aqui no mesmo
        commit — e o diff passa a mostrar o termo, não um número."""
        with open(CONTEXT, encoding="utf-8") as fh:
            found = {m.group(1).strip() for m in GLOSSARY_HEADER_NAMED.finditer(fh.read())}
        missing = sorted(GLOSSARY_ENTITIES - found)
        added = sorted(found - GLOSSARY_ENTITIES)
        self.assertEqual(
            (missing, added), ([], []),
            "o glossário do CONTEXT.md divergiu do conjunto declarado.\n"
            "  SUMIRAM (doutrina perdida — restaure ou aposente explicitamente): %s\n"
            "  ENTRARAM (declare no conjunto, no mesmo commit): %s" % (missing, added),
        )


if __name__ == "__main__":
    unittest.main()
