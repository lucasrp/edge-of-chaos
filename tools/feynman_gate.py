"""Feynman page gate — judge ONLY the page in front of you.

Deterministic content tooth the rite honors (StageFailure, no publish).
Adapted from old review-gate.py (3e6a407) to the FREE form: substance over
skeleton. No mandatory H2, no forced SVG, no YAML keys, no openai/xAI client.

Glossary and bibliography are CONTENT duties, not form:
- Glossary: every load-bearing term is taught on first use (a stranger can
  cash it). A heading named Glossário does not pass. Absence of that heading
  does not fail if the terms are taught inline.
- Bibliography / world lastro: the work is hung on named things in the world
  (paper, product, case, term of field) in the prose. A Bibliography H2 does
  not pass. Absence of that H2 does not fail if the outside names are in the
  prose. FAIL if the page never leaves the local idiom.

Calibration, sibling pages, and "operator already knows" do not waive.
"""
from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path

# ---------------------------------------------------------------------------
# Locked FAIL rule (quoted in tests and the operator report)
# ---------------------------------------------------------------------------

CRITICAL_RULE = (
    "A percentage on this page without whose evaluation, of what, and n "
    "is a critical fail. Naming the institution (Harvey, Stanford) and the "
    "defect label (invention, misgrounded) is not enough. Calibration, a "
    "sibling page, an assume-known, a Glossário H2, or a Bibliography H2 "
    "does not waive. FAIL also if the page never leaves the local idiom: "
    "no named thing in the world in the prose."
)

# Old weights minus structural-skeleton (15) and forced-SVG (8). Those 23
# points go to the two content duties Lucas kept: didatica (glossary) and
# mundo (bibliography / world lastro).
DIMENSION_WEIGHTS = {
    "profundidade": 0.15,
    "historia": 0.12,
    "feynman": 0.12,
    "prosa": 0.08,
    "honestidade": 0.10,
    "consistencia": 0.08,
    "didatica": 0.20,
    "mundo": 0.15,
}

DIMENSIONS = (
    "profundidade",
    "historia",
    "feynman",
    "prosa",
    "honestidade",
    "consistencia",
    "didatica",
    "mundo",
)

# ---------------------------------------------------------------------------
# Visible text (markdown or HTML). Form headings do not count as teaching.
# ---------------------------------------------------------------------------

_BLOCK_CLOSE = re.compile(r"(?i)</(?:p|div|h[1-6]|li|tr|blockquote|section|article)>")
_BR = re.compile(r"(?i)<br\s*/?>")
_TAG = re.compile(r"(?i)<[^>]+>")
_ATX = re.compile(r"^(#{1,6})\s+(.*)$")
_HTML_H = re.compile(r"(?i)^<h([1-6])[^>]*>(.*?)</h[1-6]>\s*$")
_FORM_HEADING = re.compile(
    r"(?i)^(gloss[aá]rio|glossary|bibliograf\w*|references|"
    r"refer[eê]ncias|contextualization(?:\s+and\s+glossary)?|"
    r"o que n[aã]o sei)$"
)
_SLUG = re.compile(r"#(?![\s#])[a-z][\w\-]{3,}")


def _visible_text(page: str) -> str:
    text = page or ""
    head = text[:400].lower()
    if "<p>" in head or "<html" in head or "<h1" in head or "<main" in head:
        text = _BLOCK_CLOSE.sub("\n\n", text)
        text = _BR.sub("\n", text)
        text = _TAG.sub(" ", text)
        text = unescape(text)
    text = text.replace("\r\n", "\n")
    return text


def _strip_slugs(text: str) -> str:
    return _SLUG.sub(" ", text)


def _iter_blocks(text: str):
    """Yield (kind, level, body) for heading | para over visible text."""
    buf: list[str] = []

    def flush():
        body = " ".join(line.strip() for line in buf).strip()
        buf.clear()
        if body:
            yield ("para", 0, body)

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            yield from flush()
            continue
        atx = _ATX.match(line)
        html_h = _HTML_H.match(line)
        if atx:
            yield from flush()
            yield ("heading", len(atx.group(1)), atx.group(2).strip())
        elif html_h:
            yield from flush()
            title = _TAG.sub(" ", html_h.group(2)).strip()
            yield ("heading", int(html_h.group(1)), title)
        else:
            buf.append(line)
    yield from flush()


def _prose_without_form_sections(text: str) -> str:
    """Drop Glossário / Bibliografia / O que Não Sei sections (form ≠ content)."""
    keep: list[str] = []
    skipping_level = 0
    for kind, level, body in _iter_blocks(text):
        if kind == "heading":
            if skipping_level and level > skipping_level:
                continue
            skipping_level = 0
            if _FORM_HEADING.match(body.strip()):
                skipping_level = level
                continue
            keep.append(body)
            continue
        if skipping_level:
            continue
        keep.append(body)
    return "\n\n".join(keep)


def _paragraphs(text: str) -> list[str]:
    return [body for kind, _level, body in _iter_blocks(text) if kind == "para"]


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

PCT_RE = re.compile(r"(?<![\d.])(\d{1,3}(?:[.,]\d+)?)\s*%")
POR_CENTO_RE = re.compile(r"(?<![\d.])(\d{1,3}(?:[.,]\d+)?)\s+por\s+cento\b", re.I)

N_RE = re.compile(
    r"(?i)(?:\bn\s*=\s*\d+"
    r"|\b(?:amostra|sample(?:\s+size)?)\s*(?:de|:)?\s*\d+"
    r"|\b\d{2,}\s+(?:cita[cç][oõ]es|casos|claims|exemplos|documentos|"
    r"perguntas|respostas|itens|pares|opini[oõ]es))"
)

WHOSE_RE = re.compile(
    r"(?i)(?:\bet\s+al\.?"
    r"|arxiv:\s*[\d.]+"
    r"|doi:\s*\S+"
    r"|\(\s*20\d{2}\s*\)"
    r"|avalia[cç][aã]o\s+(?:de|do|da|of|by)"
    r"|eval(?:uation)?\s+(?:de|of|by)"
    r"|benchmark\s+\w+"
    r"|[A-ZÁÉÍÓÚ][\w']+\s+et\s+al)"
)

OF_WHAT_RE = re.compile(
    r"(?i)(?:cita[cç][oõ]es\s+(?:gerad|produz|avaliad|de\s+ferrament)"
    r"|casos\s+(?:avaliad|gerad|do\s+corpus)"
    r"|claims\s+(?:avaliad|gerad)"
    r"|respostas\s+gerad"
    r"|autoridades\s+(?:citad|gerad)"
    r"|documentos\s+(?:citad|avaliad)"
    r"|opini[oõ]es\s+de\s+tribunal"
    r"|ferramentas\s+de\s+ia"
    r"|legal[- ]ai)"
)

LOCAL_RE = re.compile(
    r"(?ix)"
    r"(?:\#(?![\s#])[a-z][\w\-]{3,}"
    r"|\bexp\d{2,}\b"
    r"|\bed-\d{4}\b"
    r"|\b0[0-9]\d{2}\b"
    r"|\bULID\b"
    r"|\bpe[cç]a\s+anterior\b"
    r"|\boperador\s+j[aá]\s+sabe\b"
    r"|\bj[aá]\s+est[aá]\s+estabelecido\b"
    r"|\bn[aã]o\s+(?:vale|vamos)\s+reabrir\b"
    r"|\bassume(?:-|\s+)known\b"
    r"|\bticket\s+\S+"
    r")"
)

WORLD_RE = re.compile(
    r"(?x)"
    r"(?:\b(?:Stanford|Harvey|Bluebook|Lexis(?:Nexis)?|Casetext|Shepard' ?s?"
    r"|Farris|Verma|Magesh|Dahl|Harvard|Oxford|Cambridge|MIT|ACL|NeurIPS"
    r"|arXiv|Nature|Science|Westlaw|CoCounsel|Prot[eé]g[eé]|RegLab"
    r"|NetDocuments|LawSites|Ambrogi|Feynman|US\s+v\.)\b"
    r"|[A-Z][a-z]{2,}\s+et\s+al"
    r"|arxiv:\s*[\d.]+)"
)

WAIVER_RE = re.compile(
    r"(?i)(?:n[aã]o\s+(?:vale(?:\s+a\s+pena)?|vamos)\s+reabrir"
    r"|j[aá]\s+(?:est[aá]\s+estabelecido|ficou\s+resolvido)"
    r"|operador\s+j[aá]\s+sabe"
    r"|assume(?:-|\s+)known"
    r"|voc[eê]\s+j[aá]\s+sabe"
    r"|as\s+we\s+already\s+(?:showed|proved|established)"
    r"|pe[cç]a\s+anterior\s+nos\s+deixou)"
)

DERIVE_RE = re.compile(
    r"(?i)(?:hip[oó]tese"
    r"|antes de (?:buscar|pesquis|procur|ir buscar)"
    r"|deriva(?:r|ção|cao)?"
    r"|se o teste"
    r"|tentei\b"
    r"|meu palpite"
    r"|onde (?:quebra|trava|para)"
    r"|first principles"
    r"|do concreto)"
)

PLACEHOLDER_RE = re.compile(r"(?i)\b(?:TODO|TBD|lorem ipsum|placeholder)\b")


def _percentages(text: str) -> list[re.Match]:
    found = list(PCT_RE.finditer(text))
    found.extend(POR_CENTO_RE.finditer(text))
    return found


def _window_for(text: str, match: re.Match) -> str:
    paras = _paragraphs(text)
    if not paras:
        start = max(0, match.start() - 400)
        end = min(len(text), match.end() + 400)
        return text[start:end]
    pos = 0
    idx = 0
    for i, para in enumerate(paras):
        loc = text.find(para, pos)
        if loc == -1:
            loc = pos
        if loc <= match.start() <= loc + len(para) + 8:
            idx = i
            break
        pos = loc + len(para)
    lo = max(0, idx - 1)
    hi = min(len(paras), idx + 2)
    return "\n\n".join(paras[lo:hi])


def _rate_defects(text: str) -> list[str]:
    defects = []
    for match in _percentages(text):
        token = match.group(0)
        window = _window_for(text, match)
        missing = []
        if not WHOSE_RE.search(window):
            missing.append("whose evaluation")
        if not OF_WHAT_RE.search(window):
            missing.append("of what")
        if not N_RE.search(window):
            missing.append("n")
        if missing:
            defects.append(
                f"{token} lacks {', '.join(missing)} — institution + defect "
                f"label is not the instrument"
            )
    return defects


def _has_world(text: str) -> bool:
    return bool(WORLD_RE.search(_strip_slugs(text)))


def _has_local_idiom(text: str) -> bool:
    return bool(LOCAL_RE.search(text))


def _opening(text: str, n: int = 500) -> str:
    paras = _paragraphs(text)
    if not paras:
        return text[:n]
    return paras[0][:n]


# ---------------------------------------------------------------------------
# Dimension judges — each returns (pass: bool, reason: str)
# ---------------------------------------------------------------------------

def _dim_profundidade(text: str) -> tuple[bool, str]:
    paras = _paragraphs(text)
    body = " ".join(paras).strip()
    if PLACEHOLDER_RE.search(body) and len(body) < 200:
        return False, "page is a placeholder, not substance"
    if len(body) < 40:
        return False, "page has no substance"
    return True, "page has body"

def _dim_historia(text: str) -> tuple[bool, str]:
    opening = _opening(text)
    if _percentages(opening) and WAIVER_RE.search(opening):
        return False, "opens on a scoreboard the sibling already carried"
    if _SLUG.match(opening.lstrip()) or re.match(r"^#(?![\s#])[a-z][\w\-]{3,}", text.lstrip()):
        # first visible token is a slug — ID plate, not a door
        first = ( _paragraphs(text) or [opening] )[0]
        if _SLUG.search(first) and not re.search(r"[?¿]|por que|o que ", first, re.I):
            return False, "opens on an ID plate, not a door"
    return True, "opening is not a scoreboard/ID plate"

def _dim_feynman(text: str) -> tuple[bool, str]:
    if _percentages(text) and not DERIVE_RE.search(text):
        return False, "result on the page, no derivation visible"
    return True, "no dumped result without a derivation"

def _dim_prosa(text: str) -> tuple[bool, str]:
    paras = _paragraphs(text)
    bullets = 0
    for kind, _level, body in _iter_blocks(text):
        if kind == "para" and re.match(r"^[-*•]\s+", body):
            bullets += 1
    long_paras = [p for p in paras if len(p) >= 40 and not re.match(r"^[-*•]\s+", p)]
    if bullets >= 3 and not long_paras:
        return False, "telegram / bullet-only, no paragraph"
    return True, "has flowing prose or is too small to be a telegram"

def _dim_honestidade(text: str) -> tuple[bool, str]:
    if _rate_defects(text) and WAIVER_RE.search(text):
        return False, "uncertainty waived around unexplained numbers"
    return True, "no waived uncertainty around unexplained rates"

def _dim_consistencia(text: str) -> tuple[bool, str]:
    if WAIVER_RE.search(text):
        return False, "sibling / assume-known carries the briefing; this page does not"
    return True, "page does not defer the briefing to a sibling"

def _dim_didatica(text: str) -> tuple[bool, str]:
    defects = _rate_defects(text)
    if defects:
        return False, defects[0]
    return True, "no unexplained percentage"

def _dim_mundo(text: str) -> tuple[bool, str]:
    if _has_local_idiom(text) and not _has_world(text):
        return False, "page never leaves the local idiom — no named thing in the world"
    return True, "either has world lastro in the prose, or never entered the local idiom"


_DIM_FN = {
    "profundidade": _dim_profundidade,
    "historia": _dim_historia,
    "feynman": _dim_feynman,
    "prosa": _dim_prosa,
    "honestidade": _dim_honestidade,
    "consistencia": _dim_consistencia,
    "didatica": _dim_didatica,
    "mundo": _dim_mundo,
}


def judge(page: str) -> dict:
    """Structured content verdict for the page in front of you.

    Returns {
      verdict: PASS|FAIL,
      critical_issues: [str],
      dimensions: {name: {pass, reason, score}},
      overall: float,
      reasons: [str],
    }
    Calibration / assume-known / sibling / form H2 do not waive.
    """
    visible = _visible_text(page)
    body = _prose_without_form_sections(visible)

    dimensions = {}
    critical: list[str] = []
    reasons: list[str] = []

    for name in DIMENSIONS:
        ok, reason = _DIM_FN[name](body)
        dimensions[name] = {
            "pass": ok,
            "reason": reason,
            "score": 5 if ok else 1,
        }
        if not ok:
            reasons.append(f"{name}: {reason}")

    # Critical issues — the old gate's blocking list, content not form.
    rate_defects = _rate_defects(body)
    if rate_defects:
        critical.extend(rate_defects)
    if _has_local_idiom(body) and not _has_world(body):
        critical.append(
            "page never leaves the local idiom — no named thing in the world "
            "in the prose (a Bibliography H2 does not count)"
        )

    overall = sum(
        dimensions[name]["score"] * DIMENSION_WEIGHTS[name] for name in DIMENSIONS
    )
    passed = not critical and all(dimensions[name]["pass"] for name in DIMENSIONS)
    thin_spots = []
    if passed:
        thin_spots = [
            "Deepen world lastro: name one more outside paper, product, or case "
            "in the prose if the claim can bear it.",
            "Didática: any remaining number or load-bearing term taught on first "
            "use with whose evaluation, of what, and n.",
            "Feynman: keep the derivation visible; write the step that was skipped.",
        ]
    return {
        "verdict": "PASS" if passed else "FAIL",
        "critical_issues": critical,
        "dimensions": dimensions,
        "overall": round(overall, 3),
        "reasons": reasons,
        "thin_spots": thin_spots,
        "rule": CRITICAL_RULE,
    }


def briefing(verdict: dict) -> str:
    """What the next lastro goes after. Always non-empty: a FAIL names holes;
    a PASS still names remaining thin spots. The round is never skipped.
    """
    if verdict.get("critical_issues") or verdict.get("verdict") != "PASS":
        lines = ["FAIL holes the next lastro must fill:"]
        for item in verdict.get("critical_issues") or []:
            lines.append(f"- {item}")
        for item in verdict.get("reasons") or []:
            if item not in lines[-3:]:
                lines.append(f"- {item}")
        return "\n".join(lines)
    lines = [
        "PASS, but the next lastro still fills these thin spots "
        "(the round is not skipped because the gate passed lightly):"
    ]
    for item in verdict.get("thin_spots") or []:
        lines.append(f"- {item}")
    return "\n".join(lines)


def _default_ground_prompt(outputs: dict, letter: str) -> str:
    page = (
        outputs.get("feynman_page")
        or outputs.get("reader_facing")
        or outputs.get("author_correction")
        or ""
    )
    brief = outputs.get("feynman_briefing") or briefing(
        {"verdict": "FAIL", "critical_issues": ["gate briefing missing"], "reasons": []}
    )
    verdict_txt = outputs.get("feynman_gate_verdict") or ""
    return (
        f"Produce NEW lastro (fresh facts, names of instruments, n, sources in the "
        f"world) aimed at the holes or thin spots the Feynman content gate named "
        f"in round {letter}. Do not rewrite the article. Do not invent a fact or a "
        f"citation. FETCH and cite each source with a snippet. If the briefing is a "
        f"PASS thin-spot list, still bring new lastro that fills those spots.\n\n"
        f"BRIEFING:\n{brief}\n\nGATE JSON:\n{verdict_txt}\n\nPAGE:\n{page}"
    )


def _default_rewrite_prompt(outputs: dict, letter: str) -> str:
    page = (
        outputs.get("feynman_page")
        or outputs.get("author_correction")
        or ""
    )
    lastro_key = "feynman_grounding_a" if letter == "A" else "feynman_grounding_b"
    lastro = outputs.get(lastro_key) or ""
    brief = outputs.get("feynman_briefing") or ""
    return (
        f"Rewrite the page using the new lastro from round {letter}. Judge ONLY this "
        f"page: teach every load-bearing term on first use; hang the work on named "
        f"things in the world in the prose; derive before the scoreboard; put "
        f"specific uncertainty where the reasoning stops. A Glossário or Bibliografia "
        f"H2 does not satisfy those duties. No forced SVG. Do not leak treatment "
        f"words (draft, rascunho, prompt, harness).\n\n"
        f"BRIEFING:\n{brief}\n\nLASTRO:\n{lastro}\n\nPAGE:\n{page}"
    )


LOOP_PROMPTS = {
    "feynman_grounding_a": lambda o: _default_ground_prompt(o, "A"),
    "feynman_rewrite_1": lambda o: _default_rewrite_prompt(o, "A"),
    "feynman_grounding_b": lambda o: _default_ground_prompt(o, "B"),
    "feynman_rewrite_2": lambda o: _default_rewrite_prompt(o, "B"),
}


def header(verdict: dict) -> str:
    return f"FEYNMAN: {verdict.get('verdict', 'FAIL')}"


# ---------------------------------------------------------------------------
# Legacy LLM helper (not the tooth). Kept so LENS_BLOCK callers stay stable.
# Do not invoke from the rite. Do not call xAI.
# ---------------------------------------------------------------------------

RUBRIC = """\
You are judging prose against the pedagogical standard of *The Feynman Lectures on Physics*.
The bar (each is a real, testable quality of that book):

1. FIRST PRINCIPLES / INTUITION FIRST — builds understanding from the ground up; the idea
   is motivated before it is used.
2. NO UNEXPLAINED REFERENT — every term, name, jargon word, slug (e.g. `#foo-bar`), date-code,
   ULID, ticket id, or internal handle is NAMED AND EXPLAINED. A reader who did NOT live the
   session can still follow it. A bare `#slug`, a bare date like "07-13", or a raw ID with no
   gloss is a defect.
3. CONTEXTUALIZE THE NEW, ASSUME ONLY THE SHARED — what is genuinely new is explained; only
   what is truly common knowledge is assumed. Not condescending, not cryptic.
4. CONCRETE BEFORE ABSTRACT — a concrete instance grounds each abstraction.
5. OUTSIDER-FOLLOWABLE — an intelligent outsider hungry for context can reconstruct the
   argument without a glossary they don't have.
6. HONEST ABOUT THE UNKNOWN — states plainly what is not known or not decided.

Judge ONLY clarity/pedagogy against this bar. Do NOT judge whether the subject is worth writing
about — assume the subject is legitimate. The failure mode you hunt is: text that assumes the
reader lived the session.

Return STRICT JSON, nothing else, in this exact shape:
{
  "passa": <true|false>,           // true only if a context-hungry outsider could follow it
  "score_0_10": <int 0-10>,        // 10 = Feynman-clear, 0 = fully cryptic/insider-only
  "gaps": [<string>, ...],         // each a CONCRETE, ACTIONABLE clarity defect
  "veredito": <string>
}
Every gap must point to a specific defect in THIS text. If it is already clear, gaps is [].
pass threshold: passa=true iff score_0_10 >= 7.
"""


def feynman_gate(text, complete_fn):
    """Legacy LLM judge. Not the rite tooth. Prefer judge()."""
    prompt = (
        f"{RUBRIC}\n\n=== TEXT TO JUDGE ===\n{text}\n=== END TEXT ===\n\n"
        "Return ONLY the JSON object."
    )
    raw = complete_fn(prompt)
    return _parse(raw)


def _parse(raw):
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ValueError(f"no JSON in judge output: {raw[:300]!r}")
    obj = json.loads(m.group(0))
    return {
        "passa": bool(obj.get("passa", obj.get("score_0_10", 0) >= 7)),
        "score_0_10": int(obj.get("score_0_10", 0)),
        "gaps": list(obj.get("gaps", [])),
        "veredito": str(obj.get("veredito", "")),
    }


LENS_BLOCK = """\
=== LENTE LECTURES-ON-PHYSICS (parte integrante desta revisão) ===
Julgue TAMBÉM a clareza pedagógica do texto contra a régua das *Feynman Lectures on
Physics*: intuição/primeiros princípios antes do uso; NENHUM referente sem nome e sem
glosa (termo, slug, id, data-código — tudo explicado para um leitor que NÃO viveu a
sessão); o novo contextualizado; o concreto ancorando cada abstração; um outsider
inteligente consegue reconstruir o argumento; honestidade explícita sobre o que não se
sabe. Um defeito CONCRETO de clareza (referente sem nome, rótulo sem mecanismo, texto
que assume que o leitor viveu a sessão) é STRIKE como qualquer outro strike desta
revisão.

Contrapesos vinculantes desta lente:
1. Ela julga se um leitor de fora consegue SEGUIR — correção factual pertence ao
   fact-audit (estágio próprio); não re-julgue fatos aqui.
2. Comprimento NÃO é defeito: enriquecimento pedagógico cresce por natureza. O strike é
   para ENCHIMENTO — prosa que não adiciona entendimento por palavra (repetição, rótulo
   re-embalado, cerimônia) — nunca para o texto ter ficado maior.
"""


if __name__ == "__main__":
    import sys

    src = Path(sys.argv[1]).read_text(encoding="utf-8") if len(sys.argv) > 1 else sys.stdin.read()
    verdict = judge(src)
    print(header(verdict))
    print(json.dumps(verdict, ensure_ascii=False, indent=2))
    sys.exit(0 if verdict["verdict"] == "PASS" else 1)
