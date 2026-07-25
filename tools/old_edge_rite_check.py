#!/usr/bin/env python3
"""Check whether an artifact reproduces the approved old-edge grounded rite.

This is intentionally not a generic quality score. It is a regression harness
for the specific failure mode found during the exp072/genus work: an artifact can
pass close/genus metadata while still using the old report shell and missing the
approved arm's authorial movement.
"""
from __future__ import annotations

import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text: list[str] = []
        self.tags: list[str] = []
        self.attrs: list[tuple[str, str]] = []
        self.tag_classes: list[tuple[str, set[str]]] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        class_tokens = set()
        for key, value in attrs:
            if value is not None:
                self.attrs.append((key, value))
                if key == "class":
                    class_tokens.update(value.split())
        self.tag_classes.append((tag, class_tokens))

    def handle_data(self, data):
        if data.strip():
            self.text.append(data.strip())


def _read(path: Path | None) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path else ""


def _html_text_and_meta(html: str):
    parser = _TextExtractor()
    parser.feed(html)
    text = "\n".join(parser.text)
    classes = " ".join(v for k, v in parser.attrs if k == "class")
    return text, set(parser.tags), classes, parser.tag_classes


def _norm(text: str) -> str:
    text = text.lower()
    text = text.replace("ç", "c").replace("ã", "a").replace("á", "a")
    text = text.replace("é", "e").replace("í", "i").replace("ó", "o")
    text = text.replace("ú", "u").replace("õ", "o").replace("â", "a")
    return re.sub(r"\s+", " ", text)


def _count_any(text: str, patterns: list[str]) -> int:
    return sum(1 for pattern in patterns if pattern in text)


def check_page_shell(html: str, *, require_edge_artifact: bool = True) -> dict:
    """Check the material page shell, independent of the artifact's topic.

    This is the mechanical half of the old-edge regression: the approved arm is a
    direct reading page (`body > main`), while the rejected Roberto artifact still
    used the old generated report shell. New publisher output also carries the
    `edge-artifact` class on that main element. Historical experiment fixtures
    predate that class, so the content regression can opt out of that stricter
    publisher contract without weakening publish-time checks.
    """
    _visible, tags, classes, tag_classes = _html_text_and_meta(html)
    class_tokens = set(classes.split())
    has_main_edge_artifact = any(
        tag == "main" and "edge-artifact" in classes
        for tag, classes in tag_classes
    )
    old_shell_markers = {
        "report-header", "report-content", "metric-card", "next-step-card"
    }
    failures = []
    if "main" not in tags:
        failures.append("old-edge-shell:missing-main")
    elif require_edge_artifact and not has_main_edge_artifact:
        failures.append("old-edge-shell:missing-main-edge-artifact")
    if "article" in tags and "report" in class_tokens:
        failures.append("old-edge-shell:article-report")
    present = sorted(old_shell_markers & class_tokens)
    if present:
        failures.append("old-edge-shell:old-component-classes:" + ",".join(present))
    return {
        "pass": not failures,
        "failures": failures,
        "signals": {
            "tags": sorted(tags),
            "has_main_edge_artifact": has_main_edge_artifact,
            "require_edge_artifact": require_edge_artifact,
            "old_shell_classes": present,
        },
    }


def check(html: str, markdown: str = "") -> dict:
    visible = _html_text_and_meta(html)[0]
    corpus = _norm("\n".join([visible, markdown]))

    checks = []

    def add(name: str, ok: bool, detail: str):
        checks.append({"name": name, "pass": bool(ok), "detail": detail})

    shell = check_page_shell(html, require_edge_artifact=False)
    add(
        "reading_frame_matches_approved_arm",
        shell["pass"],
        "approved arm is a direct reading page: <body><main>, no article.report/cards/metrics shell",
    )

    add(
        "opens_with_live_question_not_meta_process",
        ("pergunta viva" in corpus and "produto" in corpus and "pesquisa" in corpus),
        "opening should frame the live product/research question, not audit the deploy/process itself",
    )

    add(
        "arms_and_config_reconstructed",
        all(term in corpus for term in ("raw_only", "v9_only", "raw_plus_v9_product"))
        and _count_any(corpus, ["arms", "configuracao", "rodadas", "casos"]) >= 3,
        "reader must see the compared arms/configs without relying on memory",
    )

    add(
        "qualitative_mechanism_case_round",
        all(term in corpus for term in (
            "mecanismo qualitativo concreto", "caso:", "rodada:", "melhor arm:"
        )),
        "approved rite includes one concrete case/round mechanism, not only abstract mechanism prose",
    )

    add(
        "mundo_repositions_claims",
        _count_any(corpus, ["fit com", "mismatch", "comparador", "praticas", "estudos"]) >= 4
        and _count_any(corpus, ["muda", "reposiciona", "next", "proximo experimento"]) >= 2,
        "Mundo must change claim/caveat/next decision with fit/mismatch, not decorate the text",
    )

    add(
        "numbered_lineage_with_inheritance_rejection",
        all(f"l{i}" in corpus for i in range(0, 7))
        and all(term in corpus for term in ("herdo", "rejeicao", "limite")),
        "lineage should be explicit L0..L6 with what is inherited and rejected/limited",
    )

    add(
        "decision_packaging_and_next_validation",
        all(term in corpus for term in (
            "o que muda agora", "para produto", "para o report",
            "para paper", "proxima validacao", "fechamento"
        )),
        "approved rite packages action by audience/surface and names the next validation",
    )

    add(
        "claim_boundary_is_operational",
        _count_any(corpus, ["nao da para afirmar", "nao claimar", "o que eu ainda nao sei"]) >= 2,
        "boundaries should be operational claims-not-to-make, not generic caveats",
    )

    failed = [c for c in checks if not c["pass"]]
    return {
        "pass": not failed,
        "checks": checks,
        "failures": failed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument("--md", type=Path)
    args = parser.parse_args()
    result = check(_read(args.html), _read(args.md))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
