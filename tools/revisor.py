"""O revisor que só avisa — ADR-0025.

Decisão do dono (2026-11-01, literal): "quero que o revisor só avise dos furos, e o edge pode ou
corrigir ou só mencionar a nota do revisor, à sua conveniencia".

Um revisor, uma passada, sem veto. Ele aponta FUROS (fato sem fonte, número errado, conclusão que
não segue, trecho confuso, o que faltou) e nada mais: não dá nota, não aprova, não reprova, não
pede nova rodada. O autor recebe os furos e decide, furo a furo, à conveniência dele: CORRIGE no
texto, ou DEIXA e menciona a nota numa seção curta "Notas do revisor" (o furo e, se quiser, a
resposta). A publicação nunca espera o revisor concordar.

Este módulo guarda o CONTRATO (os blocos de texto que o runtime anexa aos prompts) e a observação
mecânica barata (quantos furos, se a seção de notas existe). A observação é registrada, nunca
bloqueia.
"""
from __future__ import annotations

import re

NOTES_HEADING = "Notas do revisor"

REVIEWER_CONTRACT = """\
=== CONTRATO DO REVISOR (só aviso, sem veto) ===
Você é o revisor. Você NÃO aprova nem reprova: aponte os FUROS deste texto e pare.
Um furo é uma destas coisas, concreta e localizável no texto:
- fato sem fonte (afirmação factual que não se apoia no dossier / numa fonte citada);
- número errado (não bate com a fonte, ou a conta não fecha);
- conclusão que não segue (o passo do raciocínio não sustenta o que vem depois);
- trecho confuso (termo sem glosa, referente que só entende quem viveu a sessão, rótulo sem
  mecanismo);
- o que faltou (a pergunta óbvia do leitor que o texto não responde).
Formato: uma lista numerada, uma linha por furo, começando por "FURO n:", citando o trecho.
Se não há furo, responda "SEM FUROS". Sem nota, sem placar, sem veredito, sem cabeçalho de
aceite. Comprimento não é furo; estilo de que você não gosta não é furo.
"""

AUTHOR_CONTRACT = f"""\
=== CONTRATO DO AUTOR (você decide cada furo) ===
O revisor apontou os furos abaixo. Ele não tem veto e não haverá outra rodada. Para CADA furo,
à sua conveniência:
- CORRIGIR: conserte no texto (sem inventar fato nem citação; o que não tem fonte sai do texto
  ou vira incerteza declarada); ou
- DEIXAR: mantenha o texto e mencione a nota numa seção curta no fim, "## {NOTES_HEADING}",
  com o furo em uma linha e, se quiser, a sua resposta.
Furo corrigido não entra na seção. Se todos foram corrigidos (ou não há furos), não crie a
seção. Devolva o texto completo, pronto para o leitor.
"""

_FURO_RE = re.compile(r"(?im)^\s*(?:[-*]\s*|\d+[.)]\s*)?FURO\s*\d*\s*:")
_NOTES_RE = re.compile(r"(?im)^\s{0,3}#{1,6}\s*" + re.escape(NOTES_HEADING) + r"\s*$")


def reviewer_prompt(producer_prompt: str, extra: str = "") -> str:
    """O prompt do revisor: o do produtor (o que olhar neste gênero) + o contrato fixo."""
    parts = [producer_prompt.rstrip(), REVIEWER_CONTRACT]
    if extra:
        parts.append(extra.strip())
    return "\n\n".join(parts)


def author_prompt(producer_prompt: str, notes: str) -> str:
    """O prompt da revisão do autor: o do produtor + o contrato + as notas do revisor."""
    return "\n\n".join([producer_prompt.rstrip(), AUTHOR_CONTRACT,
                        "NOTAS DO REVISOR:\n" + notes.strip()])


def count_furos(notes: str) -> int:
    """Quantos furos o revisor apontou (linhas "FURO n:"). Observação, nunca portão."""
    return len(_FURO_RE.findall(notes or ""))


def has_notes_section(markdown: str) -> bool:
    """O texto final traz a seção "Notas do revisor"? Observação, nunca portão."""
    return bool(_NOTES_RE.search(markdown or ""))


def default_reviewer_prompt(outputs: dict) -> str:
    return ("Revise o texto abaixo contra o dossier factual.\n\nDOSSIER:\n"
            f"{outputs.get('grounding1_dossier', '')}\n\nTEXTO:\n"
            f"{outputs.get('reader_facing') or outputs.get('first_authorial_draft', '')}")


def default_author_prompt(outputs: dict) -> str:
    return ("Revise o seu próprio texto a partir das notas do revisor, na mesma voz.\n\n"
            f"DOSSIER:\n{outputs.get('grounding1_dossier', '')}\n\nTEXTO:\n"
            f"{outputs.get('first_authorial_draft', '')}")


DEFAULT_PROMPTS = {
    "reviewer_notes": default_reviewer_prompt,
    "author_revision": default_author_prompt,
}
