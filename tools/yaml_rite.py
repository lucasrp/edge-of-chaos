"""YAML-block authoring + the mechanical yaml-rite gate (exp/yaml-blocks).

Old edge: the author wrote YAML choosing block types; choosing the block WAS
choosing how to think. This experiment brings that back for the report form.

This module is the smallest seam:

  - parse an authorial draft (a YAML document, or a markdown fence with yaml)
    into the existing structured spec `render.spec_to_html` already knows;
  - `check_yaml_rite(artefato)` is the mechanical close gate (not an LLM count,
    not a word floor, not named H2s);
  - `page_bytes(text)` is the one render seam rito / publisher / verify share:
    YAML → spec_to_html wrapped in a page; free markdown stays the pinned
    markdown renderer (byte-identical for existing rito tests).

Substance is `blocks.normalize_block` — empty chrome (a comparison with only a
title, a derivation with only a heading) does not count.
"""
from __future__ import annotations

import re
from typing import Any

import html
import yaml

import blocks as block_validation
import render
from lineage import normalize_lineage

# Report-form skills that owe the yaml-rite when the piece is a developed synthesis.
# Maps / plans / prototypes / anything else owe nothing (content-relative).
REPORT_FORM_SKILLS = frozenset({"report", "report-deep"})

# Same structural trigger idea as close.RICH_RITE_PROSE_THRESHOLD — a count of
# authored units, NEVER a word floor.
YAML_RITE_PROSE_THRESHOLD = 3

COMPARISON_TYPES = frozenset({"comparison", "comparison-table", "compare", "pros-cons"})
DERIVATION_TYPES = frozenset({"derivation"})
GAP_TYPES = frozenset({"gap-marker", "gap-table", "gap-resolution"})
LINEAGE_TYPES = frozenset({"lineage", "builds-on", "builds_on"})
COGNITIVE_TYPES = COMPARISON_TYPES | DERIVATION_TYPES | GAP_TYPES

# The page-bytes renderer id when the sealed draft is YAML. Markdown drafts keep
# render.RENDERER_ID so existing rito pins stay byte-identical.
YAML_RENDERER_ID = "edge-yaml-spec/v1"

_FENCE_RE = re.compile(r"```(?:yaml|yml)\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def is_yaml_draft(text: str) -> bool:
    """True iff `text` is a YAML authorial draft (whole document or a yaml fence)."""
    return parse_authorial_draft(text) is not None


def parse_authorial_draft(text: str):
    """Parse a producer draft into a YAML mapping, or None if it is free markdown/HTML.

    Accepts:
      - a YAML document whose root is a mapping with `blocks` / `content` / typical
        report root fields;
      - a markdown document carrying a ```yaml ... ``` fence with that mapping.
    Never raises. A free-markdown report (H1 + paragraphs) returns None.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    candidates = []
    for m in _FENCE_RE.finditer(text):
        candidates.append(m.group(1))
    candidates.append(text)
    for raw in candidates:
        try:
            doc = yaml.safe_load(raw)
        except Exception:  # noqa: BLE001 — parse is fail-closed
            continue
        if _is_yaml_mapping(doc):
            return doc
    return None


def _is_yaml_mapping(doc) -> bool:
    if not isinstance(doc, dict):
        return False
    if doc.get("format") in {"edge-yaml/v1", "yaml", "edge-yaml"}:
        return True
    if isinstance(doc.get("blocks"), list):
        return True
    content = doc.get("content")
    if isinstance(content, dict) and (
        isinstance(content.get("blocks"), list)
        or isinstance(content.get("sections"), list)
    ):
        return True
    # frontmatter-ish report: intent/cites/lineage plus something block-shaped
    if any(k in doc for k in ("intent", "cites", "lineage", "bibliography")) and (
        "blocks" in doc or "content" in doc or "sections" in doc
    ):
        return True
    return False


def draft_to_spec(doc: dict) -> dict:
    """Normalize a parsed YAML document to the spec `render.spec_to_html` reads.

    Two authoring shapes, one spec:
      - root `blocks:` (optionally with `title` / `bibliography` / `executive_summary`)
      - existing `content.sections[].blocks` (passed through)
    """
    if not isinstance(doc, dict):
        return {}
    if isinstance(doc.get("content"), dict):
        spec = dict(doc["content"])
    else:
        spec = {}
        for key in ("executive_summary", "executive_summary_title", "metrics",
                    "sections", "additional_sections", "bibliography", "title"):
            if key in doc:
                spec[key] = doc[key]
        if isinstance(doc.get("blocks"), list) and "sections" not in spec:
            spec["sections"] = [{"title": doc.get("title") or "", "blocks": doc["blocks"]}]
        elif isinstance(doc.get("sections"), list) and "sections" not in spec:
            spec["sections"] = doc["sections"]
    if "bibliography" not in spec and doc.get("bibliography"):
        spec["bibliography"] = doc["bibliography"]
    if "title" not in spec and doc.get("title"):
        spec["title"] = doc["title"]
    return spec


def artefato_from_draft(text: str, *, intent=None, skill="report",
                        cites=None, lineage=None, bibliography=None) -> dict:
    """Build the artefato dict the yaml-rite gate reads from a sealed draft + rito meta."""
    doc = parse_authorial_draft(text)
    if doc is None:
        return {
            "skill": skill or "report",
            "intent": intent or "",
            "cites": list(cites or []),
            "lineage": list(lineage or []),
            "content": {"markdown": text or ""},
        }
    spec = draft_to_spec(doc)
    art_cites = doc.get("cites") if isinstance(doc.get("cites"), list) else None
    art_lineage = doc.get("lineage") if doc.get("lineage") is not None else None
    art_intent = doc.get("intent") if doc.get("intent") else intent
    if bibliography is None:
        bibliography = doc.get("bibliography") or spec.get("bibliography")
    if bibliography and not spec.get("bibliography"):
        spec["bibliography"] = bibliography
    return {
        "skill": skill or doc.get("skill") or "report",
        "intent": art_intent or "",
        "cites": art_cites if art_cites is not None else list(cites or []),
        "lineage": art_lineage if art_lineage is not None else list(lineage or []),
        "content": spec,
        "format": "edge-yaml/v1",
        "blocks": spec_blocks(spec),
    }


def spec_blocks(spec: dict) -> list:
    """Every authored block in a spec, in document order (sections then additional)."""
    out = []
    if not isinstance(spec, dict):
        return out
    if isinstance(spec.get("blocks"), list):
        out.extend(b for b in spec["blocks"] if isinstance(b, dict))
    for key in ("sections", "additional_sections"):
        for section in spec.get(key) or []:
            if not isinstance(section, dict):
                continue
            for b in section.get("blocks") or []:
                if isinstance(b, dict):
                    out.append(b)
    return out


def authored_blocks(artefato: dict) -> list:
    """Authored blocks from a finished artefato (YAML root or content.sections)."""
    if not isinstance(artefato, dict):
        return []
    if isinstance(artefato.get("blocks"), list):
        root = [b for b in artefato["blocks"] if isinstance(b, dict)]
        if root:
            return root
    content = artefato.get("content") or {}
    if isinstance(content, dict):
        return spec_blocks(content)
    return []


def _raw_type(block: dict) -> str:
    t = block.get("type") or "paragraph"
    return t if isinstance(t, str) else "paragraph"


def _canon_type(block: dict) -> str:
    bt, _ = render.canonical_block(block)
    return bt or _raw_type(block)


def _is_lineage_block(block: dict) -> bool:
    if not isinstance(block, dict):
        return False
    raw = _raw_type(block).lower().replace("_", "-")
    if raw in LINEAGE_TYPES or raw.replace("-", "_") in {"builds_on"}:
        return True
    for key in ("role", "kind"):
        v = block.get(key)
        if isinstance(v, str) and v.lower().replace("_", "-") in LINEAGE_TYPES:
            return True
    if block.get("lineage") or block.get("builds_on") or block.get("builds-on"):
        return True
    return False


def _cite_qualified(c) -> bool:
    """A cite is the qualify movement: nonblank ref AND snippet. String refs fail."""
    return (
        isinstance(c, dict)
        and isinstance(c.get("ref"), str) and c["ref"].strip()
        and isinstance(c.get("snippet"), str) and c["snippet"].strip()
    )


def _has_cites(artefato: dict) -> bool:
    cites = artefato.get("cites")
    if isinstance(cites, list) and any(_cite_qualified(c) for c in cites):
        return True
    return False


def _has_intent(artefato: dict) -> bool:
    intent = artefato.get("intent")
    return isinstance(intent, str) and bool(intent.strip())


def _has_lineage(artefato: dict, blocks: list) -> bool:
    if normalize_lineage(artefato.get("lineage")):
        return True
    if blocks and _is_lineage_block(blocks[0]):
        return True
    return any(_is_lineage_block(b) for b in blocks)


def _has_substantive(blocks: list, types: frozenset) -> bool:
    """True iff a block of one of `types` survives `normalize_block` (payload, not chrome)."""
    for b in blocks:
        raw = _raw_type(b)
        canon = _canon_type(b)
        if raw not in types and canon not in types:
            continue
        if block_validation.normalize_block(b) is not None:
            return True
    return False


def _prose_count(artefato: dict) -> int:
    content = artefato.get("content") or {}
    if not isinstance(content, dict):
        return 0
    n = 0
    summary = content.get("executive_summary") or []
    n += sum(1 for s in summary if isinstance(s, str) and s.strip())
    for b in authored_blocks(artefato):
        if _canon_type(b) in {"paragraph", "callout"}:
            n += 1
    return n


def _markdown_prose_units(artefato: dict) -> int:
    """Structural count of prose units in a free-markdown body — not a word floor.

    A heading is not a unit. A list/table row is not a unit. A non-empty paragraph
    or blockquote is. Mirrors RICH_RITE_PROSE_THRESHOLD's 'enough authored material'.
    """
    content = artefato.get("content")
    text = ""
    if isinstance(content, str):
        text = content
    elif isinstance(content, dict):
        text = content.get("markdown") or ""
    if not isinstance(text, str) or not text.strip():
        return 0
    units = 0
    for chunk in re.split(r"\n\s*\n", text):
        line = chunk.strip()
        if not line:
            continue
        first = line.splitlines()[0].strip()
        if first.startswith("#"):
            rest = "\n".join(ln for ln in line.splitlines()[1:] if ln.strip() and not ln.strip().startswith("#"))
            if not rest:
                continue
            first = rest.splitlines()[0].strip()
        if first.startswith("|") or first.startswith("- ") or first.startswith("* "):
            continue
        if first.startswith("```"):
            continue
        units += 1
    return units


def _is_yaml_shaped(artefato: dict) -> bool:
    if not isinstance(artefato, dict):
        return False
    if artefato.get("format") in {"edge-yaml/v1", "yaml", "edge-yaml"}:
        return True
    if isinstance(artefato.get("blocks"), list):
        return True
    content = artefato.get("content")
    if isinstance(content, dict) and content.get("format") in {"edge-yaml/v1", "yaml"}:
        return True
    return False


def _has_typed_cognitive(artefato: dict) -> bool:
    for b in authored_blocks(artefato):
        raw = _raw_type(b)
        canon = _canon_type(b)
        if raw in COGNITIVE_TYPES or canon in COGNITIVE_TYPES or _is_lineage_block(b):
            return True
    return False


def _normalized_skill(skill) -> str:
    if isinstance(skill, str):
        return skill.strip()
    return ""


def owes_yaml_rite(artefato: dict) -> bool:
    """Content-relative trigger: a developed report-form synthesis owes the gate.

    Maps/plans/prototypes (explicit skill) owe nothing. If skill is missing/empty,
    treat as report when the body is a developed markdown draft OR yaml-shaped
    (rito path — omitting skill used to skip the gate). A short YAML that already
    carries typed cognitive blocks OWES — the blocks are the authored material;
    there is no word floor.
    """
    if not isinstance(artefato, dict):
        return False
    skill = _normalized_skill(artefato.get("skill"))
    if skill and skill not in REPORT_FORM_SKILLS:
        return False
    if _is_yaml_shaped(artefato) or _has_typed_cognitive(artefato):
        return True
    # Free-markdown / free-HTML body (rito draft, not the historic sections+paragraphs spec).
    # Structured-spec paragraph reports stay on rich-rite; this gate is the YAML/markdown draft.
    if _markdown_prose_units(artefato) >= YAML_RITE_PROSE_THRESHOLD:
        return True
    return False


def check_yaml_rite(artefato: dict, skill=None) -> list[str]:
    """Mechanical yaml-rite violations ([] iff the gate is not owed or all present).

    A developed report-form synthesis MUST contain:
      - non-empty cites / bibliography
      - a substantive comparison OR derivation (`normalize_block` — empty chrome fails)
      - a substantive gap block
      - lineage declared (root `lineage` or a lineage / builds-on block)
      - first authored block is lineage (close check, not an H2 name)
    Free-markdown-only drafts (no typed cognitive blocks) fail as `yaml-rite:typed-blocks`.
    `skill` (the run's skill, default report) is applied when the caller has it —
    rito must pass it so a missing artefato skill cannot skip the gate.
    """
    if not isinstance(artefato, dict):
        return []
    if skill is not None:
        artefato = dict(artefato)
        artefato["skill"] = skill
    if not owes_yaml_rite(artefato):
        return []
    violations: list[str] = []
    blocks = authored_blocks(artefato)

    if not _has_cites(artefato):
        violations.append("yaml-rite:cites")
    if not _has_intent(artefato):
        violations.append("yaml-rite:intent")

    typed = [
        b for b in blocks
        if _raw_type(b) in COGNITIVE_TYPES
        or _canon_type(b) in COGNITIVE_TYPES
        or _is_lineage_block(b)
    ]
    if not typed:
        violations.append("yaml-rite:typed-blocks")

    if not _has_substantive(blocks, COMPARISON_TYPES | DERIVATION_TYPES):
        violations.append("yaml-rite:comparison-or-derivation")
    if not _has_substantive(blocks, GAP_TYPES):
        violations.append("yaml-rite:gap")
    if not _has_lineage(artefato, blocks):
        violations.append("yaml-rite:lineage")
    if blocks and not _is_lineage_block(blocks[0]):
        violations.append("yaml-rite:lineage-first")
    return violations


def spec_page_bytes(spec: dict) -> bytes:
    """YAML spec → self-contained HTML page via existing `render.spec_to_html`."""
    title = ""
    if isinstance(spec, dict):
        title = spec.get("title") or ""
    if not title:
        for b in spec_blocks(spec) if isinstance(spec, dict) else []:
            if isinstance(b.get("text"), str) and b["text"].strip():
                title = b["text"].strip().splitlines()[0][:80]
                break
    title = title or "artefato"
    body = render.spec_to_html(spec if isinstance(spec, dict) else {})
    page = _YAML_PAGE.format(title=html.escape(str(title)), body=body)
    return (page.rstrip() + "\n").encode("utf-8")


def renderer_id_for(text: str) -> str:
    return YAML_RENDERER_ID if is_yaml_draft(text) else render.RENDERER_ID


def page_bytes(text: str) -> bytes:
    """The SINGLE byte seam for a sealed authorial draft: YAML or markdown.

    Markdown path is `render.markdown_page_bytes` — existing rito tests stay
    byte-identical. YAML path is spec_to_html wrapped in a self-contained page.
    """
    doc = parse_authorial_draft(text)
    if doc is not None:
        return spec_page_bytes(draft_to_spec(doc))
    return render.markdown_page_bytes(text)


def page_text(text: str) -> str:
    return page_bytes(text).decode("utf-8")


_STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.DOTALL | re.IGNORECASE)


def reader_facing_text(text: str) -> str:
    """What the mentee reads — the probe / final_review / Feynman input.

    YAML drafts become the same HTML `page_bytes` would publish (the CSS
    block is dropped so a Feynman reader is not asked to judge stylesheets).
    Markdown drafts stay as-is. yaml-rite still runs on the YAML source.
    """
    if not isinstance(text, str):
        return "" if text is None else str(text)
    if parse_authorial_draft(text) is None:
        return text
    page = page_text(text)
    return _STYLE_RE.sub("", page).strip() + "\n"


def reader_facing_from_artefato(artefato: dict):
    """Rendered page for a YAML-shaped artefato, or None if not YAML-shaped.

    Used by close._build_prompt so a Feynman reviewer judges the mentee's
    page, not the spec keys.
    """
    if not isinstance(artefato, dict) or not _is_yaml_shaped(artefato):
        return None
    content = artefato.get("content")
    if isinstance(content, dict) and (
        spec_blocks(content) or content.get("sections") or content.get("blocks")
    ):
        page = spec_page_bytes(content).decode("utf-8")
        return _STYLE_RE.sub("", page).strip() + "\n"
    return None


# Compact chrome so comparison / derivation / gap actually read as those moves.
# Palette classes match tools/assets/base.css; this is a self-contained subset so
# rito does not have to import publisher / BASE_CSS.
_YAML_PAGE = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body{{font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.58;color:#17202a;background:#fbfbf8;margin:0}}
main{{max-width:960px;margin:0 auto;padding:48px 24px 72px}}
h1{{font-size:2rem;line-height:1.15;margin:0 0 24px;color:#111827}}
h2,h3,.section-title{{font-size:1.25rem;margin:28px 0 10px;color:#111827}}
p,li{{font-size:1rem}}
.comparison-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:24px;margin:18px 0}}
.card{{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:16px}}
.card-header{{display:flex;align-items:center;gap:8px;margin-bottom:8px}}
.card-title{{font-weight:600}}
.derivation{{background:#fff;border:1px solid #ddd6fe;border-left:4px solid #7c3aed;border-radius:8px;padding:20px;margin:16px 0}}
.derivation-header{{display:flex;align-items:center;gap:10px;margin-bottom:12px}}
.derivation-icon{{display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;background:#7c3aed;color:#fff;border-radius:50%;font-weight:700}}
.gap-marker{{background:#fffbeb;border:1px solid #fde68a;border-left:4px solid #d97706;border-radius:6px;padding:14px 18px;margin:12px 0}}
.gap-marker-label{{display:inline-block;background:#d97706;color:#fff;font-size:11px;font-weight:700;padding:1px 8px;border-radius:3px;margin-right:8px}}
.gap-table{{margin:12px 0}}
.gap-resolution{{background:#fff;border:1px solid #e5e7eb;border-radius:8px;margin:16px 0;overflow:hidden}}
.gap-resolution-header{{background:#fffbeb;border-bottom:1px solid #fde68a;padding:12px 20px;font-weight:600;color:#92400e}}
.gap-resolution-answer{{background:#f0fdf4;padding:14px 20px;color:#14532d}}
.bibliography{{margin:24px 0}}
table{{border-collapse:collapse;width:100%;margin:18px 0;background:#fff}}
th,td{{border:1px solid #d5d9df;padding:8px;vertical-align:top;text-align:left}}
th{{background:#eef1f5}}
</style>
</head>
<body><main>
{body}
</main></body></html>
"""
