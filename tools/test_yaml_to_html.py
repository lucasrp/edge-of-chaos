#!/usr/bin/env python3
"""Tests for yaml_to_html.py — block renderers + schema validation.

60 tests:
- 25 block types x ~2 tests (basic render + edge case)
- 5 schema completeness tests
- 5 validation mechanism tests
"""

import re
import sys
import pytest

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from tools.yaml_to_html import (
    BLOCK_SCHEMAS,
    RENDERERS,
    _is_empty_render,
    _validate_block,
    render_block,
    render_section,
    render_text,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def assert_renders(block: dict, *substrings: str) -> str:
    """Verify block renders non-empty HTML containing all substrings."""
    result = render_block(block)
    assert result, f"render_block returned empty for {block.get('type')}"
    # Should NOT contain error div for valid blocks
    assert "ERRO bloco" not in result, f"Unexpected validation error in: {result[:200]}"
    for s in substrings:
        assert s in result, f"Expected '{s}' in rendered HTML for {block.get('type')}"
    return result


def assert_validates_clean(block: dict) -> None:
    """Verify block produces zero validation warnings."""
    block_type = block.get("type", "paragraph")
    warnings = _validate_block(block_type, block)
    assert warnings == [], f"Expected zero warnings for {block_type}, got: {warnings}"


def assert_has_error(block: dict, *substrings: str) -> str:
    """Verify block renders with an error div containing substrings."""
    result = render_block(block)
    assert "ERRO bloco" in result, f"Expected error div in: {result[:200]}"
    for s in substrings:
        assert s in result, f"Expected '{s}' in error HTML"
    return result


# ===========================================================================
# Schema completeness tests
# ===========================================================================

class TestSchemaCompleteness:
    """Every renderer must have a schema and vice-versa."""

    def test_every_renderer_has_schema(self):
        missing = set(RENDERERS) - set(BLOCK_SCHEMAS)
        assert not missing, f"Renderers without schema: {missing}"

    def test_every_schema_has_renderer(self):
        extra = set(BLOCK_SCHEMAS) - set(RENDERERS)
        assert not extra, f"Schemas without renderer: {extra}"

    def test_schema_count_matches_renderer_count(self):
        assert len(BLOCK_SCHEMAS) == len(RENDERERS)

    def test_all_schemas_have_required_keys(self):
        for bt, schema in BLOCK_SCHEMAS.items():
            for key in ("required", "optional", "container_field"):
                assert key in schema, f"Schema '{bt}' missing key '{key}'"

    def test_container_fields_are_in_optional_or_required(self):
        """Container fields must be declared in required or optional."""
        for bt, schema in BLOCK_SCHEMAS.items():
            cf = schema.get("container_field")
            if cf is None:
                continue
            known = set(schema["required"]) | set(schema["optional"])
            for f in cf:
                assert f in known, (
                    f"Schema '{bt}': container_field '{f}' not in required/optional"
                )


# ===========================================================================
# Validation mechanism tests
# ===========================================================================

class TestValidationMechanism:
    """Test _validate_block and error injection in render_block."""

    def test_unknown_field_detected(self):
        warnings = _validate_block("paragraph", {"type": "paragraph", "text": "ok", "bogus": 1})
        assert any("desconhecido" in w for w in warnings)

    def test_missing_required_detected(self):
        warnings = _validate_block("paragraph", {"type": "paragraph"})
        assert any("obrigatorio" in w for w in warnings)

    def test_empty_container_detected(self):
        warnings = _validate_block("list", {"type": "list"})
        assert any("Container vazio" in w for w in warnings)

    def test_error_div_injected_in_html(self):
        """Wrong field name should produce visible error in rendered HTML."""
        html = render_block({"type": "numbered-card", "entries": [{"title": "X", "text": "Y"}]})
        assert "ERRO bloco" in html
        assert "entries" in html

    def test_valid_block_no_error_div(self):
        html = render_block({"type": "paragraph", "text": "Hello"})
        assert "ERRO bloco" not in html
        assert "Hello" in html


# ===========================================================================
# Block renderer tests — one per block type, basic + edge case
# ===========================================================================

class TestParagraph:
    def test_basic(self):
        assert_renders({"type": "paragraph", "text": "Hello world"}, "Hello world")

    def test_with_style(self):
        html = assert_renders(
            {"type": "paragraph", "text": "styled", "style": "color:red;"},
            "styled", "color:red",
        )
        assert_validates_clean({"type": "paragraph", "text": "styled", "style": "color:red;"})

    def test_markdown_bold(self):
        html = assert_renders({"type": "paragraph", "text": "**bold**"}, "<strong>bold</strong>")


class TestSubsection:
    def test_basic(self):
        assert_renders({"type": "subsection", "title": "My Title"}, "My Title", "<h3")

    def test_missing_title_warns(self):
        warnings = _validate_block("subsection", {"type": "subsection"})
        assert any("obrigatorio" in w for w in warnings)


class TestConceptGrid:
    def test_with_items(self):
        block = {
            "type": "concept-grid",
            "items": [
                {"name": "Concept A", "text": "Description A"},
                {"name": "Concept B", "text": "Description B"},
            ],
        }
        assert_renders(block, "Concept A", "Description A", "Concept B")
        assert_validates_clean(block)

    def test_with_concepts_synonym(self):
        block = {
            "type": "concept-grid",
            "concepts": [{"name": "X", "text": "Y"}],
        }
        assert_renders(block, "X", "Y")
        assert_validates_clean(block)

    def test_empty_container_warns(self):
        warnings = _validate_block("concept-grid", {"type": "concept-grid"})
        assert any("Container vazio" in w for w in warnings)


class TestCallout:
    def test_basic(self):
        assert_renders(
            {"type": "callout", "text": "Important note"},
            "Important note", "callout",
        )

    def test_with_variant(self):
        block = {"type": "callout", "text": "Warning", "variant": "warning"}
        html = assert_renders(block, "callout-warning")
        assert_validates_clean(block)


class TestCard:
    def test_basic(self):
        assert_renders(
            {"type": "card", "title": "Card Title", "text": "Card body"},
            "Card Title", "Card body",
        )

    def test_minimal_card(self):
        # Card with no fields is valid (all optional)
        block = {"type": "card"}
        html = render_block(block)
        assert "ERRO bloco" not in html
        assert_validates_clean(block)

    def test_with_badge(self):
        block = {"type": "card", "title": "T", "badge": "NEW", "badge_class": "success"}
        assert_renders(block, "NEW", "badge-success")


class TestNumberedCard:
    def test_multi_items(self):
        block = {
            "type": "numbered-card",
            "items": [
                {"title": "Step 1", "text": "Do this"},
                {"title": "Step 2", "text": "Do that"},
            ],
        }
        assert_renders(block, "Step 1", "Step 2", "Do this")
        assert_validates_clean(block)

    def test_single_card(self):
        block = {"type": "numbered-card", "title": "Solo", "number": "1", "text": "Desc"}
        assert_renders(block, "Solo", "Desc")
        assert_validates_clean(block)

    def test_wrong_field_name_detected(self):
        """The exact bug class: 'entries' instead of 'items'."""
        block = {"type": "numbered-card", "entries": [{"title": "X", "text": "Y"}]}
        assert_has_error(block, "entries")


class TestFlowExample:
    def test_basic(self):
        block = {
            "type": "flow-example",
            "input": "raw text",
            "output": "processed text",
            "label": "Example",
        }
        assert_renders(block, "raw text", "processed text", "Example")
        assert_validates_clean(block)

    def test_with_code(self):
        block = {
            "type": "flow-example",
            "input": "in",
            "output": "out",
            "code": "print('hello')",
        }
        assert_renders(block, "print(", "in", "out")

    def test_missing_required_warns(self):
        warnings = _validate_block("flow-example", {"type": "flow-example", "input": "x"})
        assert any("output" in w for w in warnings)


class TestComparison:
    def test_basic(self):
        block = {
            "type": "comparison",
            "before": {"title": "Before", "text": "Old way"},
            "after": {"title": "After", "text": "New way"},
        }
        assert_renders(block, "Before", "After", "Old way", "New way")
        assert_validates_clean(block)

    def test_with_bullets(self):
        block = {
            "type": "comparison",
            "before": {"title": "B", "bullets": ["item1", "item2"]},
            "after": {"title": "A", "pre": "code here"},
        }
        assert_renders(block, "item1", "item2", "code here")

    def test_missing_required_warns(self):
        warnings = _validate_block("comparison", {"type": "comparison", "before": {}})
        assert any("after" in w for w in warnings)


class TestTable:
    def test_basic(self):
        block = {
            "type": "table",
            "headers": ["Name", "Value"],
            "rows": [["Alpha", "100"], ["Beta", "200"]],
        }
        assert_renders(block, "Name", "Value", "Alpha", "100")
        assert_validates_clean(block)

    def test_with_highlight(self):
        block = {
            "type": "table",
            "headers": ["H"],
            "rows": [["r1"], ["r2"]],
            "highlight_rows": [1],
        }
        html = assert_renders(block, "r1", "r2")
        assert "DEF7EC" in html  # highlight color

    def test_empty_rows_warns(self):
        warnings = _validate_block("table", {"type": "table", "headers": ["H"], "rows": []})
        assert any("Container vazio" in w for w in warnings)


class TestComparisonTable:
    def test_basic(self):
        block = {
            "type": "comparison-table",
            "headers": ["Metric", "A", "B"],
            "rows": [
                {"cells": ["Speed", "10ms", "20ms"], "classes": ["", "good", "bad"]},
            ],
        }
        assert_renders(block, "Metric", "Speed", "10ms")
        assert_validates_clean(block)

    def test_with_score_row(self):
        block = {
            "type": "comparison-table",
            "headers": ["M", "V"],
            "rows": [{"cells": ["x", "1"], "classes": []}],
            "score_row": {"cells": ["Total", "5"], "classes": []},
            "note": "Some note",
        }
        assert_renders(block, "score-row", "Total", "Some note")


class TestRiskTable:
    def test_basic(self):
        block = {
            "type": "risk-table",
            "rows": [
                {"risk": "Data loss", "probability": "alta", "mitigation": "Backups"},
            ],
        }
        assert_renders(block, "Data loss", "Backups", "badge-danger")
        assert_validates_clean(block)

    def test_low_probability(self):
        block = {
            "type": "risk-table",
            "rows": [
                {"risk": "Minor", "probability": "baixa", "mitigation": "Monitor"},
            ],
        }
        assert_renders(block, "badge-success")


class TestCodeBlock:
    def test_basic(self):
        block = {"type": "code-block", "content": "print('hello')"}
        assert_renders(block, "print(")
        assert_validates_clean(block)

    def test_with_label_and_badge(self):
        block = {
            "type": "code-block",
            "content": "x = 1",
            "label": "Python",
            "badge": "v3",
            "badge_class": "info",
        }
        assert_renders(block, "Python", "v3", "badge-info")


class TestAsciiDiagram:
    def test_basic(self):
        block = {"type": "ascii-diagram", "content": "[A] --> [B]", "title": "Flow"}
        assert_renders(block, "[A]", "Flow")
        assert_validates_clean(block)

    def test_no_title(self):
        block = {"type": "ascii-diagram", "content": "diagram"}
        assert_renders(block, "diagram")


class TestTemplateBlock:
    def test_basic(self):
        block = {
            "type": "template-block",
            "content": "template content",
            "title": "Template",
            "description": "A template",
            "note": "Note here",
        }
        assert_renders(block, "template content", "Template", "A template", "Note here")
        assert_validates_clean(block)

    def test_minimal(self):
        block = {"type": "template-block", "content": "just content"}
        assert_renders(block, "just content")


class TestNextStepsGrid:
    def test_with_steps(self):
        block = {
            "type": "next-steps-grid",
            "steps": [
                {"number": "1", "title": "First", "description": "Do first"},
                {"number": "2", "title": "Second", "text": "Do second"},
            ],
        }
        assert_renders(block, "First", "Do first", "Second")
        assert_validates_clean(block)

    def test_with_items_synonym(self):
        block = {
            "type": "next-steps-grid",
            "items": [{"title": "Only", "phase": "P1"}],
        }
        assert_renders(block, "Only", "P1")
        assert_validates_clean(block)

    def test_empty_container_warns(self):
        warnings = _validate_block("next-steps-grid", {"type": "next-steps-grid"})
        assert any("Container vazio" in w for w in warnings)


class TestMetricsGrid:
    def test_with_items(self):
        block = {
            "type": "metrics-grid",
            "items": [
                {"value": "95%", "label": "Accuracy"},
                {"value": "0.8s", "label": "Latency"},
            ],
        }
        assert_renders(block, "95%", "Accuracy", "0.8s")
        assert_validates_clean(block)

    def test_with_metrics_synonym(self):
        block = {
            "type": "metrics-grid",
            "metrics": [{"value": "42", "label": "Answer"}],
        }
        assert_renders(block, "42", "Answer")
        assert_validates_clean(block)

    def test_wrong_field_warns(self):
        """'data' is not a valid field for metrics-grid."""
        block = {"type": "metrics-grid", "data": [{"value": "1", "label": "x"}]}
        warnings = _validate_block("metrics-grid", block)
        assert any("desconhecido" in w for w in warnings)


class TestList:
    def test_unordered(self):
        block = {"type": "list", "items": ["apple", "banana", "cherry"]}
        assert_renders(block, "apple", "banana", "<ul")
        assert_validates_clean(block)

    def test_ordered(self):
        block = {"type": "list", "items": ["first", "second"], "ordered": True}
        assert_renders(block, "first", "<ol")

    def test_empty_items_warns(self):
        warnings = _validate_block("list", {"type": "list", "items": []})
        assert any("Container vazio" in w for w in warnings)


class TestDiffBlock:
    def test_basic(self):
        block = {
            "type": "diff-block",
            "header": "changes.py",
            "lines": [
                {"type": "context", "text": "unchanged"},
                {"type": "delete", "text": "old line"},
                {"type": "insert", "text": "new line"},
            ],
        }
        assert_renders(block, "changes.py", "unchanged", "old line", "new line")
        assert_validates_clean(block)

    def test_empty_lines_warns(self):
        warnings = _validate_block("diff-block", {"type": "diff-block", "header": "x"})
        assert any("Container vazio" in w for w in warnings)


class TestRawHtml:
    def test_basic(self):
        block = {"type": "raw-html", "content": "<div>Custom HTML</div>"}
        html = render_block(block)
        assert "Custom HTML" in html
        assert_validates_clean(block)

    def test_empty(self):
        block = {"type": "raw-html"}
        html = render_block(block)
        assert "ERRO bloco" not in html  # raw-html has no container_field


class TestDerivation:
    def test_basic(self):
        block = {
            "type": "derivation",
            "title": "My Derivation",
            "text": "Starting from first principles",
            "bullets": ["Point 1", "Point 2"],
        }
        assert_renders(block, "My Derivation", "first principles", "Point 1")
        assert_validates_clean(block)

    def test_with_code(self):
        block = {"type": "derivation", "code": "E = mc^2"}
        assert_renders(block, "E = mc^2")

    def test_minimal(self):
        block = {"type": "derivation"}
        html = render_block(block)
        assert "ERRO bloco" not in html  # all optional


class TestGapMarker:
    def test_basic(self):
        block = {"type": "gap-marker", "text": "Missing data source", "id": "3"}
        assert_renders(block, "Missing data source", "GAP", "#3")
        assert_validates_clean(block)

    def test_missing_text_warns(self):
        warnings = _validate_block("gap-marker", {"type": "gap-marker"})
        assert any("obrigatorio" in w for w in warnings)


class TestGapTable:
    def test_with_gaps(self):
        block = {
            "type": "gap-table",
            "gaps": [
                {"id": 1, "description": "Gap one", "need": "Data", "status": "aberto"},
                {"id": 2, "description": "Gap two", "need": "Review", "status": "resolvido"},
            ],
        }
        assert_renders(block, "Gap one", "Gap two", "ABERTO", "RESOLVIDO")
        assert_validates_clean(block)

    def test_table_fallback(self):
        """gap-table with headers/rows delegates to table renderer."""
        block = {
            "type": "gap-table",
            "headers": ["#", "Gap", "Status"],
            "rows": [["1", "Something", "Open"]],
        }
        assert_renders(block, "Something", "Open")
        assert_validates_clean(block)


class TestGapResolution:
    def test_basic(self):
        block = {
            "type": "gap-resolution",
            "gap_id": "1",
            "gap": "What is X?",
            "text": "Investigation showed...",
            "answer": "X is Y.",
        }
        assert_renders(block, "What is X?", "Investigation showed", "X is Y.")
        assert_validates_clean(block)

    def test_minimal(self):
        block = {"type": "gap-resolution"}
        html = render_block(block)
        assert "ERRO bloco" not in html


class TestBibliography:
    def test_with_string_refs(self):
        block = {
            "type": "bibliography",
            "title": "References",
            "references": ["Ref 1", "Ref 2"],
        }
        assert_renders(block, "References", "Ref 1", "Ref 2")
        assert_validates_clean(block)

    def test_with_structured_refs(self):
        block = {
            "type": "bibliography",
            "references": [
                {"text": "Paper A", "url": "https://example.com", "source": "arxiv"},
            ],
        }
        assert_renders(block, "Paper A", "example.com", "arxiv")

    def test_empty_warns(self):
        warnings = _validate_block("bibliography", {"type": "bibliography"})
        assert any("Container vazio" in w for w in warnings)


class TestGlossary:
    def test_basic(self):
        block = {
            "type": "glossary",
            "context": "Key terms used in this report.",
            "terms": [
                {"term": "TEVV", "definition": "Test, Evaluation, Verification, Validation"},
            ],
        }
        assert_renders(block, "Key terms", "TEVV", "Verification")
        assert_validates_clean(block)

    def test_empty_terms_warns(self):
        warnings = _validate_block("glossary", {"type": "glossary"})
        assert any("Container vazio" in w for w in warnings)


# ===========================================================================
# Post-render catch-all tests
# ===========================================================================

class TestPostRenderCatchAll:
    def test_is_empty_render_detects_empty_list(self):
        """A list block with empty items renders a container div with no text."""
        # This simulates a rendered list that has the <ul> tags but no <li>s
        assert _is_empty_render("list", "<ul></ul>")

    def test_is_empty_render_false_for_content(self):
        assert not _is_empty_render("list", "<ul><li>item</li></ul>")

    def test_is_empty_render_ignores_non_container(self):
        """Non-container blocks always return False."""
        assert not _is_empty_render("paragraph", "")


# ===========================================================================
# render_text helper tests
# ===========================================================================

class TestRenderText:
    def test_bold(self):
        assert "<strong>bold</strong>" in render_text("**bold**")

    def test_italic(self):
        assert "<em>italic</em>" in render_text("*italic*")

    def test_code(self):
        assert "<code>code</code>" in render_text("`code`")

    def test_link(self):
        result = render_text("[click](https://example.com)")
        assert 'href="https://example.com"' in result
        assert "click" in result

    def test_html_escape(self):
        result = render_text("<script>alert('xss')</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result
