"""exp/yaml-blocks — mechanical yaml-rite gate + YAML → HTML render.

A developed report-form synthesis writes YAML blocks (choosing the block is
choosing the move). The gate is content-relative: maps/plans/terse forms owe
nothing; a short YAML with lineage + substantive comparison + gap + cites
passes (no H2, no word floor). Empty chrome fails normalize_block.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import blocks  # noqa: E402
import close  # noqa: E402
import render  # noqa: E402
import yaml_rite  # noqa: E402


def _cite():
    return {"ref": "arXiv:2507.02778", "kind": "mundo", "relevant": True,
            "snippet": "an external benchmark the synthesis actually used"}


def _lineage_block():
    return {"type": "lineage",
            "text": "The prior report named the read-budget hole; this one derives the watermark."}


def _comparison():
    return {
        "type": "comparison",
        "before": {"title": "session cursor",
                   "bullets": ["one watermark for the whole process", "collides across sessions"]},
        "after": {"title": "per-session watermark",
                  "bullets": ["each session owns its cursor", "crash recovery is local"]},
    }


def _gap():
    return {"type": "gap-marker",
            "text": "unknown: whether the watermark survives a hard crash of the store"}


def _short_yaml_art():
    """The pass case: short YAML, no H2, no word floor, all required moves."""
    return {
        "skill": "report",
        "intent": "open: budget unnamed; bet: name the per-session watermark",
        "cites": [_cite()],
        "lineage": [{"type": "builds_on", "slug": "prior-recall-report"}],
        "format": "edge-yaml/v1",
        "content": {"sections": [{"title": "", "blocks": [
            _lineage_block(), _comparison(), _gap(),
        ]}]},
    }


def _jurix_thin_html_art():
    """Name-drop: the object is only a venue; no typed comparison/derivation payload."""
    return {
        "skill": "report",
        "intent": "open: venue unnamed; bet: mention JURIX",
        "cites": [],
        "lineage": [],
        "content": {"markdown": (
            "JURIX is a conference on legal informatics.\n\n"
            "The venue gathers papers on AI and law each year.\n\n"
            "JURIX remains the object of this note.\n"
        )},
    }


def _empty_comparison_yaml_art():
    return {
        "skill": "report",
        "intent": "open: JURIX; bet: name-drop the venue",
        "cites": [_cite()],
        "lineage": [{"type": "builds_on", "slug": "prior"}],
        "format": "edge-yaml/v1",
        "content": {"sections": [{"title": "", "blocks": [
            _lineage_block(),
            {"type": "comparison", "title": "JURIX"},  # chrome only
            _gap(),
        ]}]},
    }


class YamlRiteGate(unittest.TestCase):
    def test_short_yaml_with_moves_passes_no_h2_no_word_floor(self):
        violations = yaml_rite.check_yaml_rite(_short_yaml_art())
        self.assertEqual(violations, [], violations)
        # also through check_genus: no yaml-rite:* 
        genus = [v for v in close.check_genus(_short_yaml_art()) if v.startswith("yaml-rite")]
        self.assertEqual(genus, [], genus)

    def test_jurix_thin_free_html_fails(self):
        v = yaml_rite.check_yaml_rite(_jurix_thin_html_art())
        self.assertIn("yaml-rite:typed-blocks", v, v)
        self.assertIn("yaml-rite:comparison-or-derivation", v, v)
        self.assertIn("yaml-rite:cites", v, v)

    def test_empty_comparison_yaml_fails(self):
        v = yaml_rite.check_yaml_rite(_empty_comparison_yaml_art())
        self.assertIn("yaml-rite:comparison-or-derivation", v, v)

    def test_empty_comparison_chrome_fails_normalize(self):
        self.assertIsNone(blocks.normalize_block({"type": "comparison", "title": "JURIX"}))
        self.assertIsNone(blocks.normalize_block({
            "type": "comparison",
            "before": {"title": "A"},
            "after": {"title": "B"},
        }))

    def test_title_only_derivation_fails_normalize(self):
        self.assertIsNone(blocks.normalize_block({"type": "derivation", "title": "Derivation"}))

    def test_substantive_comparison_survives_normalize(self):
        self.assertIsNotNone(blocks.normalize_block(_comparison()))

    def test_markdown_without_skill_still_owes_and_fails_typed_blocks(self):
        """The last-beat bug: omitting skill used to skip the gate and publish markdown."""
        art = {
            "intent": "open: venue unnamed; bet: mention JURIX",
            "cites": [],
            "lineage": [],
            "content": {"markdown": (
                "JURIX is a conference on legal informatics.\n\n"
                "The venue gathers papers on AI and law each year.\n\n"
                "JURIX remains the object of this note.\n"
            )},
        }
        self.assertNotIn("skill", art)
        self.assertTrue(yaml_rite.owes_yaml_rite(art))
        v = yaml_rite.check_yaml_rite(art)
        self.assertIn("yaml-rite:typed-blocks", v, v)

    def test_empty_skill_markdown_still_owes(self):
        art = _jurix_thin_html_art()
        art["skill"] = ""
        self.assertTrue(yaml_rite.owes_yaml_rite(art))
        self.assertIn("yaml-rite:typed-blocks", yaml_rite.check_yaml_rite(art))

    def test_map_owes_nothing(self):
        art = {
            "slug": "rel-map",
            "skill": "map",
            "intent": "open: relations untraced; bet: trace them",
            "cites": [],
            "content": {"sections": [{"title": "Map", "blocks": [
                {"type": "ascii-diagram", "content": "A --applies--> B"},
                {"type": "table", "headers": ["From", "Type", "To"],
                 "rows": [["A", "application", "B"], ["B", "rhyme", "C"], ["C", "parallel", "D"]]},
            ]}]},
        }
        self.assertEqual(yaml_rite.check_yaml_rite(art), [])
        rich = [v for v in close.check_genus(art) if v.startswith("yaml-rite")]
        self.assertEqual(rich, [])

    def test_terse_plan_owes_nothing(self):
        art = {
            "skill": "plan",
            "intent": "open: next step unnamed; bet: name it",
            "cites": [],
            "content": {"sections": [{"title": "", "blocks": [
                {"type": "next-steps-grid", "steps": [{"title": "ship the watermark"}]},
            ]}]},
        }
        self.assertEqual(yaml_rite.check_yaml_rite(art), [])

    def test_terse_report_below_threshold_owes_nothing(self):
        art = {
            "skill": "report",
            "intent": "open: one observation; bet: park it",
            "cites": [],
            "content": {"sections": [{"title": "", "blocks": [
                {"type": "paragraph", "text": "One terse observation, nothing more."},
            ]}]},
        }
        self.assertEqual(yaml_rite.check_yaml_rite(art), [])

    def test_first_block_must_be_lineage(self):
        art = _short_yaml_art()
        art["content"]["sections"][0]["blocks"] = [_comparison(), _lineage_block(), _gap()]
        v = yaml_rite.check_yaml_rite(art)
        self.assertIn("yaml-rite:lineage-first", v, v)

    def test_missing_gap_fails(self):
        art = _short_yaml_art()
        art["content"]["sections"][0]["blocks"] = [_lineage_block(), _comparison()]
        v = yaml_rite.check_yaml_rite(art)
        self.assertIn("yaml-rite:gap", v, v)

    def test_derivation_satisfies_comparison_or_derivation(self):
        art = _short_yaml_art()
        art["content"]["sections"][0]["blocks"] = [
            _lineage_block(),
            {"type": "derivation", "text": "A session is bounded, therefore the cursor is per-session."},
            _gap(),
        ]
        v = yaml_rite.check_yaml_rite(art)
        self.assertNotIn("yaml-rite:comparison-or-derivation", v, v)
        self.assertEqual(v, [], v)

    def test_one_sided_comparison_fails(self):
        art = _short_yaml_art()
        art["content"]["sections"][0]["blocks"] = [
            _lineage_block(),
            {"type": "comparison",
             "before": {"title": "session cursor", "bullets": ["one watermark"]},
             "after": {"title": "per-session watermark"}},
            _gap(),
        ]
        v = yaml_rite.check_yaml_rite(art)
        self.assertIn("yaml-rite:comparison-or-derivation", v, v)
        self.assertIsNone(blocks.normalize_block(
            art["content"]["sections"][0]["blocks"][1]))

    def test_cite_without_snippet_fails(self):
        art = _short_yaml_art()
        art["cites"] = [{"ref": "arXiv:2507.02778", "kind": "mundo"}]
        v = yaml_rite.check_yaml_rite(art)
        self.assertIn("yaml-rite:cites", v, v)

    def test_string_cite_fails(self):
        art = _short_yaml_art()
        art["cites"] = ["arXiv:2507.02778"]
        v = yaml_rite.check_yaml_rite(art)
        self.assertIn("yaml-rite:cites", v, v)

    def test_empty_gap_marker_fails(self):
        art = _short_yaml_art()
        art["content"]["sections"][0]["blocks"] = [
            _lineage_block(), _comparison(),
            {"type": "gap-marker", "text": ""},
        ]
        v = yaml_rite.check_yaml_rite(art)
        self.assertIn("yaml-rite:gap", v, v)
        self.assertIsNone(blocks.normalize_block({"type": "gap-marker", "text": ""}))


class YamlParseAndRender(unittest.TestCase):
    SHORT_YAML = """\
intent: "open: budget unnamed; bet: name the watermark"
cites:
  - ref: arXiv:2507.02778
    kind: mundo
    snippet: an external benchmark the synthesis actually used
lineage:
  - type: builds_on
    slug: prior-recall-report
blocks:
  - type: lineage
    text: The prior report named the read-budget hole; this one derives the watermark.
  - type: comparison
    before:
      title: session cursor
      bullets: ["one watermark for the whole process"]
    after:
      title: per-session watermark
      bullets: ["each session owns its cursor"]
  - type: gap-marker
    text: "unknown: whether the watermark survives a hard crash"
"""

    def test_parse_root_blocks(self):
        doc = yaml_rite.parse_authorial_draft(self.SHORT_YAML)
        self.assertIsInstance(doc, dict)
        self.assertEqual(len(doc["blocks"]), 3)
        art = yaml_rite.artefato_from_draft(self.SHORT_YAML, skill="report")
        self.assertEqual(yaml_rite.check_yaml_rite(art), [])

    def test_parse_fenced_yaml(self):
        fenced = "# notes\n\n```yaml\n" + self.SHORT_YAML + "```\n"
        doc = yaml_rite.parse_authorial_draft(fenced)
        self.assertIsInstance(doc, dict)
        self.assertTrue(yaml_rite.is_yaml_draft(fenced))

    def test_free_markdown_is_not_yaml(self):
        md = "# Relatorio\n\nJURIX e uma conferencia.\n\nMais um paragrafo sobre o venue.\n"
        self.assertIsNone(yaml_rite.parse_authorial_draft(md))
        self.assertFalse(yaml_rite.is_yaml_draft(md))

    def test_yaml_renders_via_spec_to_html(self):
        page = yaml_rite.page_bytes(self.SHORT_YAML).decode("utf-8")
        self.assertIn("comparison-grid", page)
        self.assertIn("gap-marker", page)
        self.assertIn("per-session watermark", page)
        self.assertEqual(yaml_rite.renderer_id_for(self.SHORT_YAML), yaml_rite.YAML_RENDERER_ID)

    def test_markdown_page_bytes_stay_pinned(self):
        md = "# Titulo\n\nParagrafo com `code`.\n"
        self.assertEqual(yaml_rite.page_bytes(md), render.markdown_page_bytes(md))
        self.assertEqual(yaml_rite.renderer_id_for(md), render.RENDERER_ID)

    def test_content_sections_shape(self):
        text = """\
intent: "open: x; bet: y"
cites:
  - ref: r
    snippet: s
lineage:
  - type: builds_on
    slug: prior
content:
  sections:
    - title: ""
      blocks:
        - type: lineage
          text: prior brought the hole
        - type: comparison
          before: {title: A, bullets: ["old"]}
          after: {title: B, bullets: ["new"]}
        - type: gap-marker
          text: still open
"""
        art = yaml_rite.artefato_from_draft(text, skill="report")
        self.assertEqual(yaml_rite.check_yaml_rite(art), [])


class ExistingGenusNonReportStillPasses(unittest.TestCase):
    """The yaml-rite must not falsely fail a diagram map or a terse plan."""

    def test_diagram_form_map_genus_has_no_yaml_rite(self):
        art = {
            "slug": "rel-map",
            "content": {"sections": [{"title": "Map", "blocks": [
                {"type": "ascii-diagram", "content": "A --applies--> B\nB --rhymes--> C"},
                {"type": "table", "headers": ["From", "Type", "To"],
                 "rows": [["A", "application", "B"], ["B", "rhyme", "C"], ["C", "parallel", "D"]]},
            ]}]},
            "cites": [], "proposes": [], "distills": [],
            "intent": "open: relations untraced; bet: trace them", "skill": "map",
        }
        self.assertEqual([v for v in close.check_genus(art) if v.startswith("yaml-rite")], [])

    def test_wellformed_terse_still_empty(self):
        # 1 paragraph, no report skill — the historic wellformed fixture shape
        art = {
            "slug": "recall-report",
            "content": {"sections": [{"title": "What I found", "blocks": [
                {"type": "paragraph", "text": "the read budget is unnamed"},
            ]}]},
            "cites": [{"ref": "github:abc123", "kind": "atividade", "relevant": True,
                       "snippet": "switched the cursor to a per-session watermark"}],
            "proposes": [{"body": "name the full-read budget", "kind": "constraint"}],
            "distills": ["cluster:recall"],
            "intent": "open: budget unnamed; bet: name it next beat",
        }
        self.assertEqual(close.check_genus(art), [])



class ReaderFacingText(unittest.TestCase):
    """Probe/review input is the mentee page, not YAML keys.

    A SHORT_YAML that yaml-rite accepts must not look like jargon just for
    being YAML. A genuinely cryptic *payload* still reaches the facing text
    so a genuinely cryptic payload still reaches the facing text.
    """

    SHORT_YAML = YamlParseAndRender.SHORT_YAML

    def test_yaml_becomes_published_html_not_source_keys(self):
        art = yaml_rite.artefato_from_draft(self.SHORT_YAML, skill="report")
        self.assertEqual(yaml_rite.check_yaml_rite(art), [])
        facing = yaml_rite.reader_facing_text(self.SHORT_YAML)
        self.assertIn("per-session watermark", facing)
        self.assertIn("comparison-grid", facing)
        self.assertIn("gap-marker", facing)
        # authoring chrome the mentee never sees
        self.assertNotIn("type: comparison", facing)
        self.assertNotIn("type: lineage", facing)
        self.assertNotIn("type: gap-marker", facing)
        self.assertNotIn("\nblocks:\n", facing)
        self.assertNotIn("kind: mundo", facing)

    def test_markdown_stays_as_is(self):
        md = "# Titulo\n\nParagrafo com `code`.\n"
        self.assertEqual(yaml_rite.reader_facing_text(md), md)
        self.assertIsNone(yaml_rite.parse_authorial_draft(md))

    def test_cryptic_payload_survives_into_facing_text(self):
        """A cryptic rendered page can still strike — we do not strip payload jargon."""
        cryptic = self.SHORT_YAML.replace(
            "per-session watermark", "grill.leveling event-type")
        facing = yaml_rite.reader_facing_text(cryptic)
        self.assertIn("grill.leveling", facing)
        self.assertNotIn("type: comparison", facing)

    def test_close_feynman_prompt_uses_rendered_html_for_yaml(self):
        art = _short_yaml_art()
        prompt = close._build_prompt(close._FEYNMAN_FOCUS, art)
        self.assertIn("per-session watermark", prompt)
        self.assertNotIn('"type": "comparison"', prompt)
        # non-YAML artefato still gets the historic JSON view
        empty = close._build_prompt(close._REGULAR_FOCUS,
                                    {"slug": "x", "content": {}, "cites": []})
        self.assertIn("metrics-grid", empty)

if __name__ == "__main__":
    unittest.main()
