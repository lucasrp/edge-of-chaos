"""Feynman page reviewer — judge ONLY the page in front of you.

Old-edge review-gate reviewer (3e6a407 REVIEWER_SYSTEM + DIMENSIONS), adapted
to FREE form: substance over skeleton. A model scores eight axes 0-4 with
written feedback (ceiling 4: a 5 would mean "nothing to say"). Every axis
must name a page-specific improvement. The rite always runs two evaluate
→ lastro → rewrite rounds; a score does not skip a lastro and a low score
does not extra-loop. The notes are a briefing for the next lastro, not a
ticket that blesses or aborts the loop. There is no minimum score to pass.

No mandatory H2, no forced SVG, no YAML keys, no openai/xAI client.

Glossary and bibliography are CONTENT duties, not form:
- Glossary: every load-bearing term is taught on first use (a stranger can
  cash it). A heading named Glossário does not pass. Absence of that heading
  does not fail if the terms are taught inline.
- Bibliography / world lastro: the work is hung on named things in the world
  (paper, product, case, term of field) in the prose. A Bibliography H2 does
  not pass. Absence of that H2 does not fail if the outside names are in the
  prose. Critical issue (briefing flag) if the page never leaves the local idiom.

Calibration, sibling pages, and "operator already knows" do not waive.
"""
from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path

# ---------------------------------------------------------------------------
# Locked critical-issue rule (quoted in tests and the operator report)
# ---------------------------------------------------------------------------

CRITICAL_RULE = (
    "A percentage on this page without whose evaluation, of what, and n "
    "is a critical issue (briefing flag, not a ticket). Naming the institution "
    "(Harvey, Stanford) and the "
    "defect label (invention, misgrounded) is not enough. Calibration, a "
    "sibling page, an assume-known, a Glossário H2, or a Bibliography H2 "
    "does not waive. Flag also if the page never leaves the local idiom: "
    "no named thing in the world in the prose."
)

SCORE_MAX = 4
REVIEW_MAX_TOKENS = 4_000
REVIEWER_MARKER = "OLD-EDGE-STYLE PAGE REVIEWER"

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

# Adapted from 3e6a407 tools/review-gate.py DIMENSIONS to FREE form.
DIMENSION_SPECS = {
    "profundidade": (
        "Substance, not placeholders. Concrete details, data, numbers, real "
        "examples. No empty or stub page. Score the thought, not the length."
    ),
    "historia": (
        "The page tells a STORY — a narrative arc (setup → tension → "
        "exploration → resolution), not a section skeleton. Headings do not "
        "make an arc. The opening is a door onto the object, not a scoreboard "
        "or an ID plate. The end closes the opening."
    ),
    "feynman": (
        "Locked genus: 'deriva antes de ir buscar fora.' Derive first; the "
        "process of thinking is visible; the hole sits inline where the "
        "author's knowledge stopped. Explanations teach someone intelligent "
        "but unfamiliar. No jargon without definition. A dumped result with "
        "no derivation is a low score."
    ),
    "prosa": (
        "Flowing prose, not telegram / bullet-only. Transitions. Reflective, "
        "not robotic. Titles evocative, not merely descriptive."
    ),
    "honestidade": (
        "Specific uncertainty where thought actually stops — a real hole, "
        "named. NOT a required H2 'O que Não Sei'. Missing that heading does "
        "not fail. A boilerplate honesty section does not pass. Waiver "
        "language around a number is a defect."
    ),
    "consistencia": (
        "THIS PAGE CARRIES. A sibling page, a calibration, or 'já está "
        "estabelecido' / assume-known cannot save a number or a claim. "
        "Lineage one-liner is fine; deferring the briefing to a prior piece "
        "is not."
    ),
    "didatica": (
        "Glossary-as-content, not form. Locked: 'todo termo na primeira vez. "
        "o nome da ferramenta pelo que ela faz, não pelo que ela é.' Every "
        "load-bearing term is taught on first use; a tool is named by what "
        "it does, not what it is. A percentage needs whose evaluation, of "
        "what, and n. A heading named Glossário does not pass. Absence of "
        "that heading does not fail if the terms are taught inline. "
        "Score 4 = a stranger understands; still name one next term or rate "
        "to tighten on THIS page. "
        "Score 3 = most things explained, a few insider terms slip through. "
        "Score 1 = internal notes."
    ),
    "mundo": (
        "Bibliography-as-content, not form. Locked: 'contextualizar o "
        "trabalho com o mundo.' Named things in the world live IN THE PROSE "
        "(paper, product, case, field term). An H2 Bibliografia / References "
        "does not pass. Missing that H2 does not fail if the names are in "
        "the prose. Low score (and a critical issue) if the page never "
        "leaves the local idiom: no world name in the prose."
    ),
}

# ---------------------------------------------------------------------------
# Old-edge reviewer prompt (page only, no tools)
# ---------------------------------------------------------------------------

def _dimension_block() -> str:
    return "\n".join(
        f"- **{name}**: {DIMENSION_SPECS[name]}" for name in DIMENSIONS
    )


REVIEWER_SYSTEM = """You are {marker}.

You are the old Edge review-gate reviewer, adapted to FREE-FORM pages (content, not H2). Your job: evaluate the page AS-IS against the dimensions and give structured, SPECIFIC written feedback. Cite phrases and numbers from THIS page. Your notes feed a later grounding (lastro) and a rewrite. You do not bless the page. You do not abort a loop. You do not skip a round. Two iterations always run regardless of your scores.

IMPORTANT: You are evaluating the artifact AS-IS. You have no tools and no external context. Judge ONLY the page in front of you. If a claim seems unverified, flag it. If context seems missing, note it. A sibling page, a calibration, or "the operator already knows" cannot save this page.

Language: respond in Portuguese (PT-BR) for feedback strings. JSON keys stay in English.

## Evaluation Dimensions

{dimensions}

## Scoring Scale

Rate each dimension 0-4. There is no 5. A 5 would mean "nothing to say" and there is always something that can improve. Never emit 5.
- 0: Completely missing or broken
- 1: Present but severely deficient — major rework needed
- 2: Below a working bar — significant issues
- 3: Working bar — still name one concrete next improvement citing THIS page
- 4: Strong — and STILL name one concrete next improvement citing THIS page

Never write "no issues found". Never leave feedback empty. Every dimension MUST point to something that can be improved, written, page-specific. Empty or canned thin_spots are forbidden.

There is NO minimum score to pass. The score only contextualizes the next lastro (how thin that axis is). It is not a ticket. You do not bless the page. You do not fail the page.

## Critical Issues (briefing flags, CONTENT only — not a ticket)

Flag as critical_issues if ANY of these. Do NOT flag missing headings.
- A percentage without whose evaluation / of what / n. Naming the institution (Harvey, Stanford) and the defect label (invention, misgrounded) is not enough. Calibration, a sibling page, an assume-known, a Glossário H2, or a Bibliography H2 does not waive.
- The page never leaves the local idiom: no named thing in the world in the prose.
- 3+ load-bearing terms unused or unexplained.
- assume-known / "já está estabelecido" carrying a number or a claim.

Do NOT restore or require: mandatory Glossário H2, mandatory "O que Não Sei" H2, mandatory Bibliografia H2, forced SVG, executive_summary, YAML spec keys. Missing those headings is not a defect. Heading-only glossary or bibliography does not satisfy didática or mundo.

## Output Format

Respond with ONLY valid JSON (no markdown fences, no text outside JSON):
{{
  "overall": 0.0,
  "dimensions": {{
    "profundidade": {{"score": 0, "feedback": "..."}},
    "historia": {{"score": 0, "feedback": "..."}},
    "feynman": {{"score": 0, "feedback": "..."}},
    "prosa": {{"score": 0, "feedback": "..."}},
    "honestidade": {{"score": 0, "feedback": "..."}},
    "consistencia": {{"score": 0, "feedback": "..."}},
    "didatica": {{"score": 0, "feedback": "..."}},
    "mundo": {{"score": 0, "feedback": "..."}}
  }},
  "critical_issues": [],
  "suggestions": []
}}

Notes:
- overall = weighted average (profundidade 15%, historia 12%, feynman 12%, prosa 8%, honestidade 10%, consistencia 8%, didatica 20%, mundo 15%). The runtime recomputes this; still fill it. It is briefing context, not a pass ticket.
- suggestions: MUST be 3-7 specific, actionable, PAGE-SPECIFIC improvements the next lastro can fetch or the rewrite can apply. Never empty. Never canned.
- Each dimension.feedback MUST name one concrete next improvement citing THIS page (PT-BR). Never "no issues found". Never blank.
- Do not invent a source. If you need a name, n, or instrument that is not on the page, say so in the notes so the lastro can fetch it.
"""


def reviewer_prompt(page: str) -> str:
    """System + page. No tools. Judge only this page."""
    system = REVIEWER_SYSTEM.format(
        marker=REVIEWER_MARKER,
        dimensions=_dimension_block(),
    )
    body = page if isinstance(page, str) else ""
    return (
        f"{system}\n\n"
        f"## Page to review\n\n"
        f"{body}\n\n"
        f"Review ONLY the page above. Return ONLY the JSON object."
    )


def _call_complete(complete_fn, prompt: str, max_tokens: int = REVIEW_MAX_TOKENS) -> str:
    """Rite transport is complete_fn(route, prompt, max_tokens). Tests may pass that."""
    return complete_fn("review", prompt, max_tokens)


def _strip_fences(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3].strip()
    return text


# Duty of each axis, used when the model leaves feedback blank or writes
# "no issues". Always a hole to chase — never empty, never canned thin_spots.
AXIS_DUTY_HOLE = {
    "profundidade": (
        "eixo profundidade: ainda falta um detalhe concreto, dado, número ou "
        "exemplo real citado nesta página — nunca 'sem issues'."
    ),
    "historia": (
        "eixo historia: ainda dá para fechar melhor o arco (porta → tensão → "
        "resolução) citando a abertura ou o fim desta página."
    ),
    "feynman": (
        "eixo feynman: ainda dá para tornar visível a derivação antes do "
        "resultado, citando o ponto desta página em que o raciocínio some."
    ),
    "prosa": (
        "eixo prosa: ainda dá para trocar um trecho telegráfico desta página "
        "por prosa com transição."
    ),
    "honestidade": (
        "eixo honestidade: ainda dá para nomear o buraco real onde o "
        "pensamento desta página para — heading 'O que Não Sei' não conta."
    ),
    "consistencia": (
        "eixo consistencia: esta página ainda precisa carregar o claim "
        "sozinha; cite o ponto em que ela remete a irmão/calibração."
    ),
    "didatica": (
        "eixo didatica: ainda falta ensinar na prosa um termo ou taxa desta "
        "página (whose / of what / n); Glossário H2 não conta."
    ),
    "mundo": (
        "eixo mundo: ainda falta pendurar o trabalho num nome do mundo na "
        "prosa desta página; Bibliografia H2 não conta."
    ),
}

_NO_ISSUE_RE = re.compile(
    r"(?i)^(n/?a|ok\.?|none|sem (?:issues?|problemas?|notas?)|"
    r"no issues?(?:\s+found)?|nothing to (?:say|improve)|"
    r"sem nada a (?:dizer|melhorar)|excellent(?:\s+—\s+no issues found)?)$"
)


def _is_blank_or_no_issues(text: str) -> bool:
    fb = (text or "").strip()
    if not fb:
        return True
    low = fb.lower()
    if "no issues" in low or "sem issues" in low or "nothing to say" in low:
        return True
    return bool(_NO_ISSUE_RE.match(fb))


def _feedback_or_hole(name: str, feedback: str) -> str:
    if _is_blank_or_no_issues(feedback):
        return AXIS_DUTY_HOLE[name]
    return feedback.strip()


def parse_review(raw: str) -> dict:
    """Parse reviewer JSON and recompute overall. No pass/fail ticket.

    Scores are clamped to 0..4 (a model 5 is stored as 4). overall is the
    weighted average so the lastro can see which axis is thinner. critical_issues
    are briefing flags, not a StageFailure switch.
    """
    text = _strip_fences(raw)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON in reviewer output: {text[:300]!r}")
    obj = json.loads(match.group(0))
    return finalize_verdict(obj)


def finalize_verdict(obj: dict) -> dict:
    raw_dims = obj.get("dimensions") or {}
    dimensions = {}
    for name in DIMENSIONS:
        data = raw_dims.get(name) or {}
        if not isinstance(data, dict):
            data = {}
        try:
            score = int(data.get("score", 0))
        except (TypeError, ValueError):
            score = 0
        score = max(0, min(SCORE_MAX, score))
        feedback = _feedback_or_hole(
            name, str(data.get("feedback") or data.get("reason") or "")
        )
        dimensions[name] = {
            "score": score,
            "feedback": feedback,
            "reason": feedback,
        }
    overall = sum(dimensions[name]["score"] * DIMENSION_WEIGHTS[name] for name in DIMENSIONS)
    critical = [str(x) for x in (obj.get("critical_issues") or []) if str(x).strip()]
    suggestions = [str(x) for x in (obj.get("suggestions") or []) if str(x).strip()]
    if not suggestions:
        suggestions = [AXIS_DUTY_HOLE[name] for name in DIMENSIONS[:3]]
    return {
        "verdict": "NOTES",
        "overall": round(overall, 3),
        "dimensions": dimensions,
        "critical_issues": critical,
        "suggestions": suggestions,
        "reasons": [
            f"{name}: {dimensions[name]['feedback']}"
            for name in DIMENSIONS
            if dimensions[name]["score"] < 3
        ],
        "rule": CRITICAL_RULE,
    }


def review(page: str, complete_fn) -> dict:
    """Rite tooth: call the review-route LLM, parse JSON, clamp scores.

    No tools. Page only. Does not raise on a low score or a critical issue —
    those are briefing flags. Mid-loop the rite records the notes and
    continues. The close tooth may store notes; it must not StageFailure.
    The loop never consults a score to skip a round.
    """
    prompt = reviewer_prompt(page)
    raw = _call_complete(complete_fn, prompt)
    if not (isinstance(raw, str) and raw.strip()):
        raise ValueError("reviewer returned an empty response")
    return parse_review(raw)


def briefing(verdict: dict) -> str:
    """Page-specific notes for the next lastro. Always non-empty.

    Uses the model's feedback / critical_issues / suggestions. Not the
    canned three thin_spots. Not a PASS/FAIL ticket. Every axis is listed
    with a written hole — empty / "no issues" becomes the axis duty.
    A high score still produces notes the lastro can chase.
    """
    lines = [
        "Anotações do revisor (briefing para o próximo lastro — não é "
        "ticket de passar/falhar; as duas rodadas sempre correm; o score "
        "só contextualiza o quão fino está o eixo):"
    ]
    dims = verdict.get("dimensions") or {}
    for name in DIMENSIONS:
        data = dims.get(name) or {}
        score = data.get("score", "?")
        fb = _feedback_or_hole(
            name, data.get("feedback") or data.get("reason") or ""
        )
        lines.append(f"- {name} ({score}/{SCORE_MAX}): {fb}")
    critical = verdict.get("critical_issues") or []
    if critical:
        lines.append("Critical issues (briefing flags, not a ticket):")
        for item in critical:
            lines.append(f"- {item}")
    suggestions = [str(x) for x in (verdict.get("suggestions") or []) if str(x).strip()]
    if not suggestions:
        suggestions = [AXIS_DUTY_HOLE[name] for name in DIMENSIONS[:3]]
    lines.append("Suggestions:")
    for item in suggestions:
        lines.append(f"- {item}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Visible text (markdown or HTML). Form headings do not count as teaching.
# Kept for the deterministic helper `judge()` (CLI / tests), not the rite tooth.
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
# Detectors (deterministic helper only)
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
# Deterministic helper only. The rite tooth is review().
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
    """Deterministic helper (CLI / tests). Not the rite tooth.

    The rite calls review() — the old-edge LLM reviewer. This stays so a
    host without a transport can still smoke-check a page. Scores cap at 4.
    Not a pass/fail ticket.
    """
    visible = _visible_text(page)
    body = _prose_without_form_sections(visible)

    dimensions = {}
    critical: list[str] = []
    reasons: list[str] = []

    for name in DIMENSIONS:
        ok, reason = _DIM_FN[name](body)
        dimensions[name] = {
            "reason": reason,
            "feedback": reason,
            "score": SCORE_MAX if ok else 1,
        }
        if not ok:
            reasons.append(f"{name}: {reason}")

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
    suggestions = reasons[:7] or [AXIS_DUTY_HOLE[name] for name in DIMENSIONS[:3]]
    return {
        "verdict": "NOTES",
        "critical_issues": critical,
        "dimensions": dimensions,
        "overall": round(overall, 3),
        "reasons": reasons,
        "suggestions": suggestions,
        "rule": CRITICAL_RULE,
    }


def _page_from(outputs: dict) -> str:
    return (
        outputs.get("feynman_page")
        or outputs.get("reader_facing")
        or outputs.get("author_correction")
        or ""
    )


def _default_ground_prompt(outputs: dict, letter: str) -> str:
    page = _page_from(outputs)
    brief = outputs.get("feynman_briefing") or briefing({})
    verdict_txt = outputs.get("feynman_gate_verdict") or ""
    return (
        f"Produce NEW lastro (fresh facts, names of instruments, n, sources in the "
        f"world) aimed at the reviewer notes in the briefing for round {letter}. "
        f"Do not rewrite the article. Do not invent a fact or a citation. FETCH "
        f"and cite each source with a snippet. A high score does not skip this "
        f"lastro. A low score does not add an extra loop. Two rounds always run.\n\n"
        f"BRIEFING:\n{brief}\n\nREVIEW JSON:\n{verdict_txt}\n\nPAGE:\n{page}"
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


def _default_review_prompt(outputs: dict) -> str:
    return reviewer_prompt(_page_from(outputs))


LOOP_PROMPTS = {
    "feynman_gate_1": _default_review_prompt,
    "feynman_gate_2": _default_review_prompt,
    "feynman_grounding_a": lambda o: _default_ground_prompt(o, "A"),
    "feynman_rewrite_1": lambda o: _default_rewrite_prompt(o, "A"),
    "feynman_grounding_b": lambda o: _default_ground_prompt(o, "B"),
    "feynman_rewrite_2": lambda o: _default_rewrite_prompt(o, "B"),
}


def header(verdict: dict) -> str:
    return (
        f"FEYNMAN: NOTES overall={verdict.get('overall', 0)} "
        f"(briefing, not a ticket)"
    )


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
    """Legacy LLM judge. Not the rite tooth. Prefer review()."""
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
    sys.exit(0)
