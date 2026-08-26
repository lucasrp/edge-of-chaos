#!/usr/bin/env python3
"""Old-Edge review-gate via grok CLI — NOT OpenAI/xAI API.

Two review→refine rounds. Criteria: 9 dims, all >= 3, overall >= 3.5, zero critical.
No word-count cap (the March gate did not have one).

Binding fail is LEITURA ISOLADA / isolated reading: a colleague of the operator,
same shop, who missed this session and did not read this week's beats, still
understands the page alone. Required H2 skeleton (Glossário / O que não sei /
Referências / Linhagem) is gone. Linhagem-first is a fail, not a required section.

Usage:
  tools/edge-python tools/review-gate.py SPEC.yaml \
      --html OUT.html --outdir DIR [--rounds 2]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import traceback
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
os.environ.setdefault("PATH", "")
os.environ["PATH"] = (
    "/home/roberto/.local/bin:" + str(SCRIPT_DIR) + ":" + os.environ["PATH"]
)
sys.path.insert(0, str(SCRIPT_DIR))

import _llm  # noqa: E402
# grok CLI only — never llm_routes completer_for (that can be xAI/OpenAI HTTP).

DIMENSIONS = {
    "structural_completeness": (
        "THE page is a self-contained artifact. Sections are FREE. "
        "Do NOT require H2 Glossário, O que não sei, Referências, or Linhagem. "
        "Missing those headings is not a defect. Heading-only costume does not pass. "
        "Linhagem-first is a FAIL, not a required section: put the object on the table "
        "before any outside name, prior beat, or date-stamped index. "
        "All blocks use valid types from the report template. "
        "An opener that indexes internal beats/dates without teaching the object "
        "(canonical fail: Galison 25/08 + ledger 25/08 + occupy-hedge 24/08) "
        "fails this dimension — leitura isolada died in sentence one."
    ),
    "content_depth": (
        "Sections have substance, not placeholders. "
        "Concrete details, data, numbers, real examples. "
        "No empty sections or stub content. "
        "Tables have real data, not lorem ipsum."
    ),
    "storytelling": (
        "Saturday coffee, tell a friend. The report tells a STORY, not a section skeleton. "
        "Open on a runnable object, cut first. Narrative arc: the object "
        "(why this matters) → tension → exploration → resolution. "
        "Headings do not make an arc. A sequel disclaimer "
        "('this page does not reopen X from yesterday') is a fail, not a hook. "
        "The reader should want to keep reading — not just scanning headers. "
        "Analogies and concrete scenarios make abstract ideas tangible. "
        "The conclusion connects back to the opening object — the arc closes."
    ),
    "feynman_method": (
        "Object and derivation BEFORE any outside name. "
        "Reason from first principles BEFORE searching or citing. "
        "Linhagem-first (name-drop, then maybe explain) is a fail. "
        "Gaps sit inline where the author's knowledge stopped — not a required H2. "
        "Explanations teach someone intelligent but unfamiliar. "
        "No jargon without definition. Analogies used to test understanding. "
        "The process of thinking is visible — not just conclusions. "
        "Uncertainty is quantified or bounded, not hand-waved."
    ),
    "writing_quality": (
        "Text in paragraph blocks is fluido (flowing prose), not telegráfico "
        "(bullet-point-only). Transitions between ideas. "
        "Reflective tone, not didactic or robotic. "
        "Blockquotes sound like crystallized thoughts. "
        "Titles are evocative, not descriptive."
    ),
    "visualization": (
        "At least 1 SVG visualization (inline in raw-html block). "
        "Data tables paired with charts when 3+ values compared. "
        "Diagrams where relationships/flows communicate better visually. "
        "SVG follows standards: viewBox, font-family, semantic colors."
    ),
    "intellectual_honesty": (
        "Specific uncertainty where thought actually stops — a real hole, named. "
        "NOT a required H2 'O que Não Sei' / 'O que Nao Sei'. "
        "Missing that heading does not fail. A boilerplate honesty section does not pass. "
        "Uncertainty stated clearly. Blind spots acknowledged. "
        "Assumptions marked as untested. gap-marker / gap-table where the thought stalled."
    ),
    "internal_consistency": (
        "THIS PAGE CARRIES — leitura isolada / isolated reading. "
        "A sibling page, a prior beat, a date stamp, or 'já está estabelecido' "
        "cannot save a claim. Sequel / needs previous artifact = FAIL. "
        "Lineage one-liner AFTER the object is fine; deferring the briefing "
        "to a prior piece is not. Title matches actual scope. "
        "Numbers consistent throughout. Executive summary matches section content "
        "when present (it is not a required H2)."
    ),
    "didactic_clarity": (
        "BINDING FAIL — leitura isolada / isolated reading: a colleague of the "
        "operator, same shop, who missed this session and did not read this week's "
        "beats, cannot follow the page alone → FAIL. "
        "Every load-bearing term is taught on first use IN THE PROSE. "
        "A heading named Glossário does not pass. Absence of that heading does not "
        "fail if the terms are taught inline. "
        "Acronyms expanded on first mention. Tool/system names by what they DO, "
        "not what they ARE. Numbers have whose evaluation / of what / n. "
        "Score 5 = isolated reading passes — the colleague understands everything. "
        "Score 3 = most things explained, a few insider terms slip through. "
        "Score 1 = encrypted index of internal beats — full of unexplained jargon."
    ),
}

DIM_ORDER = list(DIMENSIONS.keys())
# 3e6a4071a weights (must match DIMENSIONS order, sum 1.0)
DIMENSION_WEIGHTS = {
    "structural_completeness": 0.15,
    "content_depth": 0.15,
    "storytelling": 0.12,
    "feynman_method": 0.12,
    "writing_quality": 0.08,
    "visualization": 0.08,
    "intellectual_honesty": 0.10,
    "internal_consistency": 0.08,
    "didactic_clarity": 0.12,
}
THRESHOLD = 3.5


def _extract_first_json(text: str) -> str:
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.endswith("```"):
            t = t[:-3].strip()
    i = t.find("{")
    if i < 0:
        return t
    depth = 0
    in_str = False
    esc = False
    for j, ch in enumerate(t[i:], start=i):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return t[i : j + 1]
    j = t.rfind("}")
    if j > i:
        return t[i : j + 1]
    return t[i:]


def _extract_yaml(text: str) -> str:
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    t = text.strip()
    if t.startswith("```"):
        lines = t.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def _call_grok(prompt: str, raw_path: Path, *, max_tokens: int = 8000) -> str:
    """Judge/refine via grok CLI subscription only — no xAI/OpenAI HTTP."""
    client = _llm.GrokClient()
    raw = _llm.complete(client, "grok-4.5", prompt, max_tokens=max_tokens)
    text = raw if isinstance(raw, str) else ("" if raw is None else str(raw))
    try:
        raw_path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    except Exception:
        pass
    return text


def _build_review_prompt(yaml_text: str, html_text: str | None) -> str:
    dim_lines = []
    for name, desc in DIMENSIONS.items():
        w = DIMENSION_WEIGHTS[name]
        dim_lines.append(f"- **{name}** (peso {w:.2f}): {desc}")
    dims = "\n".join(dim_lines)
    html_part = ""
    if html_text:
        # keep prompt bounded
        clipped = html_text if len(html_text) < 120000 else html_text[:120000] + "\n<!-- clipped -->"
        html_part = f"\n## HTML renderizado (apoio visual; julgue o spec + a página)\n\n{clipped}\n"
    return f"""Você é o review-gate do produce (pipe Tetris / generate_report).
Avalie o artefato YAML (spec do relatório) + a página contra a rubrica abaixo.
Idioma da resposta: português (PT-BR).
Responda com UM objeto JSON válido. Sem markdown, sem texto fora do JSON.

O TESTE QUE DECIDE É A LEITURA ISOLADA. Não é slogan. É o fail binding do produce.
Isolated reading = uma pessoa que trabalha com o operador, mesma loja, que NÃO
leu os beats desta semana e NÃO viveu a sessão, ainda entende a página sozinha.

NÃO julgue com a rubrica de close.py / "o que esta página decide".
NÃO invente teto de palavras. Este gate NÃO tem banda 1800–2200.
NÃO restaure H2 obrigatório Glossário / O que não sei / Referências / Linhagem.
Ausência desses headings NÃO é defeito. Heading-only NÃO passa leitura isolada.

## Dimensões (nota 0–5 cada)

{dims}

## Escala
- 0: ausente ou quebrado
- 1: gravemente deficiente
- 2: abaixo do mínimo
- 3: mínimo aceitável
- 4: bom — só ajustes menores
- 5: excelente

## critical_issues (bloqueantes) — flag se QUALQUER:
- LEITURA ISOLADA FALHOU: colega do operador, mesma loja, perdeu esta sessão e não leu os beats da semana, não consegue seguir a página sozinho
- Opener que cita beats/datas internas sem pôr o objeto na mesa (canónico: "Galison 25/08" + "ledger 25/08" + "occupy-hedge 24/08" — índice interno, disclaimer de sequel, objeto nunca entra)
- Sequel / precisa do artefato anterior — "esta página não reabre X", "já fechou o seu objeto", assume-known, "já está estabelecido"
- Linhagem-first: nome de fora ou beat anterior ANTES do objeto/derivação
- 3+ siglas ou termos técnicos sem explicação na primeira ocorrência NA PROSA (H2 Glossário não salva)
- Seções vazias (título sem blocos/conteúdo)
- Zero visualizações SVG no spec (precisa de raw-html com SVG inline)
- Contradição interna (seção cita dado/evento que não existe no spec)

NÃO flaggeie ausência de H2 Glossário / O que não sei / Referências / Linhagem.
Esses headings NÃO são obrigatórios. Um H2 com esses nomes NÃO passa leitura isolada.
executive_summary e metrics são forma YAML do pipe (quando o spec é YAML), não H2 de esqueleto.

## Formato de saída (SOMENTE este JSON)
{{
  "pass": true,
  "overall": 0.0,
  "dimensions": {{
    "structural_completeness": {{"score": 0, "feedback": "..."}},
    "content_depth": {{"score": 0, "feedback": "..."}},
    "storytelling": {{"score": 0, "feedback": "..."}},
    "feynman_method": {{"score": 0, "feedback": "..."}},
    "writing_quality": {{"score": 0, "feedback": "..."}},
    "visualization": {{"score": 0, "feedback": "..."}},
    "intellectual_honesty": {{"score": 0, "feedback": "..."}},
    "internal_consistency": {{"score": 0, "feedback": "..."}},
    "didactic_clarity": {{"score": 0, "feedback": "..."}}
  }},
  "critical_issues": [],
  "suggestions": []
}}

Regras de pass (o harness RECALCULA):
- pass = true SOMENTE se TODAS as notas >= 3 E zero critical_issues E overall >= 3.5
- overall = média ponderada (structural 15%, depth 15%, storytelling 12%, feynman 12%, writing 8%, visualization 8%, honesty 10%, consistency 8%, didactic 12%)
- suggestions: 3 a 7 melhorias específicas e acionáveis, em PT-BR

## YAML spec

{yaml_text}
{html_part}
"""


def _build_refine_prompt(yaml_text: str, verdict: dict) -> str:
    dims = verdict.get("dimensions") or {}
    fb_lines = []
    for name in DIM_ORDER:
        d = dims.get(name) or {}
        fb_lines.append(f"- {name} ({d.get('score', '?')}/5): {d.get('feedback', '')}")
    critical = verdict.get("critical_issues") or []
    suggestions = verdict.get("suggestions") or []
    crit_txt = "\n".join(f"  - {c}" for c in critical) or "  (nenhum)"
    sug_txt = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(suggestions)) or "  (nenhuma)"
    return f"""Você é o editor YAML do Edge antigo. Recebe o spec e o veredito do review-gate.
REESCREVA o YAML completo aplicando o veredito.
Saída: SOMENTE o YAML completo. Sem markdown, sem comentário, sem fences.

## Regras
- Conserte TODOS os critical_issues primeiro — leitura isolada é o teste que decide
- Depois notas < 4; depois suggestions aplicáveis
- NÃO remova substância boa — só acrescentar, aprofundar, reestruturar
- Preserve title/subtitle/date e o que já funciona; executive_summary/metrics são forma YAML, não H2
- Seções LIVRES. NÃO invente nem exija H2 Glossário / O que não sei / Referências / Linhagem
- Linhagem-first é FAIL: objeto e derivação ANTES de qualquer nome de fora
- Sequel / precisa do artefato de ontem = FAIL. Esta página carrega.
- Ensine cada termo na primeira ocorrência na prosa (H2 Glossário não conta)
- Pelo menos 1 SVG inline em bloco raw-html (viewBox, font-family)
- Derivação visível (bloco derivation ou passos reais no corpo)
- Gaps específicos no sítio onde o pensamento parou, não boilerplate
- Voz: café de sábado — objeto primeiro, corte primeiro; sem chrome "o que esta página decide"
- Idioma: PT-BR

## Veredito
pass={verdict.get("pass")} overall={verdict.get("overall")}

critical_issues:
{crit_txt}

dimensões:
{chr(10).join(fb_lines)}

suggestions:
{sug_txt}

## YAML atual

{yaml_text}
"""


def _finalize_verdict(raw_obj: dict, meta: dict) -> dict:
    dims_in = raw_obj.get("dimensions") or {}
    dimensions = {}
    scores = []
    weighted = 0.0
    for name in DIM_ORDER:
        cell = dims_in.get(name) or {}
        try:
            score = int(cell.get("score", 0))
        except (TypeError, ValueError):
            score = 0
        score = max(0, min(5, score))
        feedback = cell.get("feedback") or ""
        if not isinstance(feedback, str):
            feedback = str(feedback)
        dimensions[name] = {"score": score, "feedback": feedback}
        scores.append(score)
        weighted += score * DIMENSION_WEIGHTS[name]
    overall = round(weighted, 2)
    critical = raw_obj.get("critical_issues") or []
    if not isinstance(critical, list):
        critical = [str(critical)]
    critical = [str(c) for c in critical]
    suggestions = raw_obj.get("suggestions") or []
    if not isinstance(suggestions, list):
        suggestions = [str(suggestions)]
    suggestions = [str(s) for s in suggestions][:7]
    passed = bool(scores) and min(scores) >= 3 and len(critical) == 0 and overall >= THRESHOLD
    return {
        "pass": passed,
        "overall": overall,
        "dimensions": dimensions,
        "critical_issues": critical,
        "suggestions": suggestions,
        "_meta": meta,
    }


def _regen_html(yaml_path: Path, html_path: Path | None) -> bool:
    if html_path is None:
        return False
    gen = SCRIPT_DIR / "generate_report.py"
    if not gen.is_file():
        print(f"review-gate: generate_report.py missing at {gen}", file=sys.stderr)
        return False
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SCRIPT_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    html_path.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [sys.executable, str(gen), "--yaml", str(yaml_path), "--output", str(html_path)],
        cwd=str(SCRIPT_DIR),
        env=env,
        capture_output=True,
        text=True,
    )
    print(r.stdout or "", end="", file=sys.stderr)
    if r.returncode != 0:
        print(r.stderr or "", end="", file=sys.stderr)
        print(f"review-gate: generate_report exit {r.returncode}", file=sys.stderr)
        return False
    return True


def review_once(yaml_text: str, html_text: str | None, raw_path: Path) -> dict:
    meta = {
        "gate": "old-edge-3e6a407-grok-cli",
        "complete_fn": "_llm.GrokClient / grok CLI",
        "grok_bin": "/home/roberto/.local/bin/grok",
        "grok_model": "grok-4.5",
        "threshold": THRESHOLD,
        "dims": DIM_ORDER,
        "weights": DIMENSION_WEIGHTS,
        "word_cap": None,
        "yaml_chars": len(yaml_text),
        "html_chars": len(html_text or ""),
    }
    prompt = _build_review_prompt(yaml_text, html_text)
    meta["prompt_chars"] = len(prompt)
    try:
        raw = _call_grok(prompt, raw_path, max_tokens=8000)
        blob = _extract_first_json(raw)
        raw_obj = json.loads(blob)
        return _finalize_verdict(raw_obj, meta)
    except Exception as e:  # noqa: BLE001
        status = getattr(e, "status", None)
        detail = getattr(e, "detail", None) or str(e)
        infra = {
            "type": type(e).__name__,
            "status": status,
            "detail": detail,
            "is_transport": bool(_llm and isinstance(e, getattr(_llm, "LLMTransportError", ()))),
            "traceback": traceback.format_exc()[-2000:],
        }
        return {
            "pass": False,
            "overall": 0.0,
            "dimensions": {},
            "critical_issues": [f"infra: {type(e).__name__} status={status} detail={detail}"],
            "suggestions": [],
            "_meta": meta,
            "infra_error": infra,
        }


def refine_once(yaml_path: Path, verdict: dict, raw_path: Path) -> bool:
    yaml_text = yaml_path.read_text(encoding="utf-8")
    prompt = _build_refine_prompt(yaml_text, verdict)
    try:
        raw = _call_grok(prompt, raw_path, max_tokens=16000)
        new_yaml = _extract_yaml(raw)
        if len(new_yaml) < 200 or "title:" not in new_yaml:
            print("review-gate: refine did not return usable YAML", file=sys.stderr)
            return False
        yaml_path.write_text(new_yaml if new_yaml.endswith("\n") else new_yaml + "\n", encoding="utf-8")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"review-gate: refine failed: {type(e).__name__}: {e}", file=sys.stderr)
        return False


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Old-Edge review-gate via grok CLI")
    p.add_argument("yaml", help="YAML spec path")
    p.add_argument("--html", default=None, help="HTML output path (regenerated after refine)")
    p.add_argument("--outdir", default=None, help="Where to write gate-N.json")
    p.add_argument("--rounds", type=int, default=2)
    p.add_argument("--entry", default=None, help="Optional blog entry (unused except noted)")
    args = p.parse_args(argv)

    yaml_path = Path(args.yaml).resolve()
    if not yaml_path.is_file():
        print(f"ERROR: YAML not found: {yaml_path}", file=sys.stderr)
        return 2
    html_path = Path(args.html).resolve() if args.html else None
    outdir = Path(args.outdir).resolve() if args.outdir else yaml_path.parent
    outdir.mkdir(parents=True, exist_ok=True)

    rounds = max(1, int(args.rounds))
    last = None
    for r in range(1, rounds + 1):
        yaml_text = yaml_path.read_text(encoding="utf-8")
        html_text = None
        if html_path and html_path.is_file():
            html_text = html_path.read_text(encoding="utf-8")
        raw_path = outdir / f"gate-{r}.raw.txt"
        print(f"── Round {r}/{rounds}: Review ──", file=sys.stderr)
        verdict = review_once(yaml_text, html_text, raw_path)
        last = verdict
        (outdir / f"gate-{r}.json").write_text(
            json.dumps(verdict, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "round": r,
                    "pass": verdict.get("pass"),
                    "overall": verdict.get("overall"),
                    "n_critical": len(verdict.get("critical_issues") or []),
                    "infra": bool(verdict.get("infra_error")),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        if verdict.get("pass") or r == rounds:
            break
        print(f"── Round {r}/{rounds}: Refine ──", file=sys.stderr)
        ok = refine_once(yaml_path, verdict, outdir / f"gate-{r}.refine.raw.txt")
        if ok and html_path is not None:
            _regen_html(yaml_path, html_path)

    # If last refine happened because we broke only on pass/last: when last failed
    # and we refined inside the loop only when r < rounds. After final refine of
    # an earlier round we already re-reviewed. If the last review failed we still
    # try one trailing refine + regen so the published HTML is the improved one.
    if last is not None and not last.get("pass"):
        # already refined if r < rounds; if we exited on last review fail, refine now
        refine_marker = outdir / f"gate-{rounds}.refine.raw.txt"
        if not refine_marker.exists():
            print("── Trailing refine after last review ──", file=sys.stderr)
            ok = refine_once(yaml_path, last, refine_marker)
            if ok and html_path is not None:
                _regen_html(yaml_path, html_path)

    feedback = {"final_review": last, "rounds": rounds, "yaml": str(yaml_path), "html": str(html_path) if html_path else None}
    (outdir / "review-gate.feedback.json").write_text(
        json.dumps(feedback, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"ok": True, "pass": bool(last and last.get("pass")), "overall": (last or {}).get("overall"), "outdir": str(outdir)}, ensure_ascii=False))
    return 0 if last and last.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
