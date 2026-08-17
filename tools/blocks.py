"""Producer-emitted block normalization — the substance predicate (D6 / plan Step 1).

Once the writer emits typed blocks (D2), the payloads come from an LLM and several rich-block
schemas do NOT validate nested shape: an empty/malformed `metrics-grid` renders empty yet a
type-only gate counts it as a visual. The cure is robust-by-construction, NOT a field list:

  1. render is fail-closed (render.py) — a malformed block degrades to a comment, never crashes.
     `normalize_block` uses that render-smoke ONLY as the no-crash / renderability check.
  2. substance is a per-type PAYLOAD predicate — a block is KEPT iff its PAYLOAD (never
     title/label/header/headers/chrome) is non-empty. "Renders non-empty HTML" is NOT the oracle:
     renderers emit visible chrome from headers/labels with no real payload.

`normalize_block(block) -> dict | None` returns the block iff it both renders (no crash) AND
carries a substantive payload; else None. `normalize_blocks(blocks)` drops the Nones. The close
gate's `_visual_substantive(block, block_type) := normalize_block(block) is not None`.
"""
from __future__ import annotations

import re

import render


def _items(block: dict, *keys) -> list:
    """The first non-empty list among the given payload keys (e.g. items / metrics)."""
    for k in keys:
        v = block.get(k)
        if isinstance(v, list) and v:
            return v
    return []


def _nonblank(v) -> bool:
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, tuple)):
        return any(_nonblank(x) for x in v)
    if isinstance(v, dict):
        return any(_nonblank(x) for x in v.values())
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return True  # a number (incl. numeric 0) is real data, not blank
    return bool(v)


def _metrics_quantitative_items(block: dict) -> list:
    """The metric items whose `value` is quantitative AND have a nonblank `label` — delegated to the
    render seam's `quantitative_metric_items` so the gate and the renderer share ONE filler rule (D-D)."""
    return render.quantitative_metric_items(_items(block, "items", "metrics"))


def metrics_grid_substantive(block: dict) -> bool:
    """A metrics-grid (and its aliases) is substantive iff >= 1 item has a QUANTITATIVE value + label
    (D-D: a nonblank-but-textual value like "pré-CSS" is filler, not a metric)."""
    return bool(_metrics_quantitative_items(block))


def _comparison_table_substantive(block: dict) -> bool:
    """>= 1 row whose `cells` is a non-empty LIST with a nonblank entry (headers alone never
    qualify; a scalar `cells` renders nothing, so it is not substantive — Codex P2)."""
    rows = block.get("rows")
    if not isinstance(rows, list):
        return False
    return any(isinstance(r, dict) and isinstance(r.get("cells"), (list, tuple))
               and any(_nonblank(c) for c in r["cells"]) for r in rows)


def _diff_block_substantive(block: dict) -> bool:
    """>= 1 line with `text` (a header alone never qualifies)."""
    lines = block.get("lines")
    if not isinstance(lines, list):
        return False
    return any(isinstance(ln, dict) and _nonblank(ln.get("text")) for ln in lines)


def _side_has_payload(side) -> bool:
    if not isinstance(side, dict):
        return False
    return (
        _nonblank(side.get("bullets")) or _nonblank(side.get("items"))
        or _nonblank(side.get("text")) or _nonblank(side.get("content"))
        or _nonblank(side.get("description")) or _nonblank(side.get("pre"))
    )


def _comparison_substantive(block: dict) -> bool:
    """BOTH sides must carry payload (titles alone never qualify)."""
    left = block.get("before") or block.get("left")
    right = block.get("after") or block.get("right")
    return _side_has_payload(left) and _side_has_payload(right)


def _next_steps_substantive(block: dict) -> bool:
    """>= 1 step with a real action/title/description (chrome — phase/priority/owner — never qualifies)."""
    steps = block.get("steps") or block.get("items")
    candidates = list(steps) if isinstance(steps, list) else []
    for phase in ("now", "next", "later"):
        v = block.get(phase)
        if isinstance(v, list):
            candidates += v
        elif isinstance(v, str):
            candidates.append(v)
    for step in candidates:
        if isinstance(step, str) and step.strip():
            return True
        if isinstance(step, dict) and (
            _nonblank(step.get("title")) or _nonblank(step.get("action"))
            or _nonblank(step.get("description")) or _nonblank(step.get("text"))
            or _nonblank(step.get("detail")) or _nonblank(step.get("content"))
        ):
            return True
    return False


def _concept_grid_substantive(block: dict) -> bool:
    """>= 1 item with name + text/definition (a name alone never qualifies)."""
    for it in _items(block, "items", "concepts"):
        if isinstance(it, dict) and (_nonblank(it.get("name")) or _nonblank(it.get("title"))) and (
            _nonblank(it.get("text")) or _nonblank(it.get("description"))
            or _nonblank(it.get("definition"))
        ):
            return True
    return False


def _flow_example_substantive(block: dict) -> bool:
    return _nonblank(block.get("input")) and _nonblank(block.get("output"))


def _ascii_diagram_substantive(block: dict) -> bool:
    return _nonblank(block.get("content"))


# Visible-but-not-substantive markup: wrapper-only chrome that renders no real payload.
# A sanitized raw-html is substantive iff it carries visible non-whitespace text content OR a
# data-bearing element with meaningful children — NOT empty/wrapper-only chrome, literal {svg},
# or a <script>-only payload (which the sanitizer strips to nothing).
def _raw_html_substantive(block: dict) -> bool:
    content = block.get("content")
    if content is None:
        content = block.get("html")
    if not isinstance(content, str) or not content.strip():
        return False
    cleaned = render.sanitize_raw_html(content)
    if not cleaned or not cleaned.strip():
        return False  # <script>-only sanitizes away
    import re
    # a literal `{svg}` (or `{chart}`) placeholder is NOT real content — drop it before the
    # visible-text check so a template stub never clears the gate.
    if re.fullmatch(r"\s*\{[a-zA-Z_-]+\}\s*", cleaned):
        return False
    # visible text content (tags stripped): real prose counts only if non-tag, non-whitespace
    # characters remain after removing tags.
    text_only = re.sub(r"<[^>]*>", "", cleaned)
    if text_only.strip():
        return True
    # no visible text — require a genuinely data-bearing element, NOT an empty leaf/wrapper
    # (<svg><g></g></svg>, <table><tr><td></td></tr></table> carry no payload). Content tables/lists
    # are already caught by the visible-text check above, so here only attribute-bearing graphics
    # count: an SVG geometry shape with attributes, or an <img>/<image>/<use> with a source.
    if re.search(r"<(rect|circle|line|path|polygon|polyline|ellipse)\b[^>]*\w+=",
                 cleaned, re.IGNORECASE):
        return True
    if re.search(r"<(img|image)\b[^>]*\b(?:src|href|xlink:href)=", cleaned, re.IGNORECASE):
        return True
    if re.search(r"<use\b[^>]*\b(?:href|xlink:href)=", cleaned, re.IGNORECASE):
        return True
    return False


# Per-type PAYLOAD predicate. chart/diagram use render's existing renderable check (which already
# validates the recipe + actually renders) — looked up on `render` at CALL time (not captured here)
# so a test that patches `render.chart_renderable`/`render.diagram_renderable` is honored. Types
# absent here have no extra payload contract — they pass the substance check on render-smoke alone.
_PAYLOAD_PREDICATES = {
    "chart": lambda b: render.chart_renderable(b),
    "diagram": lambda b: render.diagram_renderable(b),
    "metrics-grid": metrics_grid_substantive,
    "comparison-table": _comparison_table_substantive,
    "diff-block": _diff_block_substantive,
    "comparison": _comparison_substantive,
    "gap-marker": lambda b: _nonblank(b.get("text")),
    "derivation": lambda b: (_nonblank(b.get("text")) or _nonblank(b.get("bullets"))
                            or _nonblank(b.get("steps")) or _nonblank(b.get("conclusion"))
                            or _nonblank(b.get("code"))),
    "next-steps-grid": _next_steps_substantive,
    "concept-grid": _concept_grid_substantive,
    "flow-example": _flow_example_substantive,
    "ascii-diagram": _ascii_diagram_substantive,
    "raw-html": _raw_html_substantive,
    # Prose blocks: an empty placeholder (text="") is hollow — drop it so it can't masquerade as
    # delivered prose (Codex P2: an empty paragraph would otherwise suppress the writer body fallback).
    "paragraph": lambda b: _nonblank(b.get("text")),
    "callout": lambda b: _nonblank(b.get("text")),
    "list": lambda b: _nonblank(b.get("items")),
}


def normalize_block(block: dict):
    """Keep a block iff it RENDERS (render-smoke: no crash, non-empty HTML) AND carries a
    substantive PAYLOAD per its (canonical) type — else None. NEVER raises.

    The PAYLOAD predicate (never title/label/header/headers/chrome) is the substance oracle for the
    visual types; a type with no predicate passes on render-smoke alone (it is not a hollowable
    visual). Non-dict / unknown / comment-degraded blocks are dropped."""
    if not isinstance(block, dict):
        return None
    # Canonicalize EXACTLY as render does (aliases + field synonyms) so the predicate sees the same
    # fields the renderer reads — e.g. raw-html with the `text` synonym renders but reads `content`.
    block_type, canon = render.canonical_block(block)
    if block_type is None:
        return None
    # metrics-grid: ITEM-LEVEL filter (D-D) — a block-level keep/drop leaks filler in a MIXED grid
    # (render emits EVERY item). Repair the block to only quantitative-value items; drop if none remain.
    if block_type == "metrics-grid":
        items = _metrics_quantitative_items(canon)
        if not items:
            return None
        block = {k: v for k, v in block.items() if k != "metrics"}
        block["items"] = items
        block_type, canon = render.canonical_block(block)
    # Required-field gate — drop a block missing a render-required field (mirrors
    # close._check_block_schemas on the CANONICAL block, where synonyms are already resolved). This
    # keeps normalize and the genus gate in lockstep: a block that survives normalize can never trip
    # the genus "missing required field" check (e.g. a comparison-table the LLM emitted without headers).
    schema = render.BLOCK_SCHEMAS.get(block_type)
    if schema:
        for field in schema.get("required", []):
            if field not in canon:
                return None
    # render-smoke — the no-crash / renderability check (mechanism 1, NEVER the substance oracle).
    try:
        html = render.render_block(block)
    except Exception:  # noqa: BLE001 — render is fail-closed; belt-and-braces here too
        return None
    if not html or not html.strip() or html.strip().startswith("<!--"):
        return None
    predicate = _PAYLOAD_PREDICATES.get(block_type)
    if predicate is not None and not predicate(canon):  # predicate reads canonical fields
        return None
    return block


def normalize_blocks(blocks) -> list:
    """Normalize a list of producer-emitted blocks, dropping every block that fails substance.
    A non-list input yields []."""
    if not isinstance(blocks, list):
        return []
    return [b for b in (normalize_block(b) for b in blocks) if b is not None]
