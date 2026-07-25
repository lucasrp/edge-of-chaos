"""Phase 1 of the shared rich producer protocol (docs/plans/shared-rich-producer-protocol.md).

The change is a SCAFFOLD PROMPT — the type→format rule in `skills/_shared/scaffold.md` that teaches every
producer's writer to reach the full block palette and lead with its declared floor blocks. A prompt cannot be
unit-tested by running an LLM, so these tests pin the two things that CAN regress, by PARSING the scaffold
text and cross-checking it against the canonical schemas + the producer descriptors:

1. Scaffold↔palette consistency — every block type the rule names is a REAL canonical block (in
   `render.BLOCK_SCHEMAS`) or a known alias (`render._BLOCK_TYPE_ALIASES`). The rule never teaches a
   non-existent block.
2. Descriptor↔scaffold coverage — every block type any producer DESCRIPTOR's `richness.require` can be
   satisfied by is mentioned in the rule. Writers are actually taught how to satisfy their floor.
"""
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import render  # noqa: E402
import visual_recipes  # noqa: E402
import producer_descriptor as pd  # noqa: E402

SCAFFOLD = REPO / "skills" / "_shared" / "scaffold.md"

# The recipe names (line/bar/dag/force/…) are sub-names of the `chart`/`diagram` BLOCKS, not block types
# themselves. The scaffold names them, so subtract them before checking "every named token is a block type."
_RECIPE_NAMES = set(visual_recipes.CHART_RECIPES) | set(visual_recipes.DIAGRAM_RECIPES)

# The producer names (map/plan/discovery/…) — backtick-quoted in the rule's "leads with" clause as
# producer identifiers, never as blocks. Subtract them too before checking block-type validity.
_PRODUCER_NAMES = set(pd.DESCRIPTORS)

# The universe of valid block-type tokens: canonical schema keys + every forgiving alias.
_BLOCK_UNIVERSE = set(render.BLOCK_SCHEMAS) | set(render._BLOCK_TYPE_ALIASES)


def _rule_text():
    """The type→format section of the scaffold — from its heading to the next top-level heading."""
    text = SCAFFOLD.read_text(encoding="utf-8")
    m = re.search(r"^## The type→format rule.*?(?=^## )", text, re.MULTILINE | re.DOTALL)
    assert m, "the scaffold has no '## The type→format rule' section"
    return m.group(0)


def _backtick_tokens(text):
    """Every single-backtick-quoted token in the text (the scaffold quotes block/recipe names this way)."""
    return set(re.findall(r"`([^`]+)`", text))


def _descriptor_floor_block_types():
    """Every block type any producer descriptor's `richness.require` can be SATISFIED by.

    Walks the same predicate vocabulary the evaluator (producer_descriptor._eval_predicate) honors:
      - min_blocks_of  → its `types`
      - any_of         → the union over its options (recursed)
      - has_structure  → producer_descriptor._STRUCTURE_BLOCKS[id]  (e.g. framed_steps → next-steps/numbered-card)
      - contextual_framing → `callout`  (the block the evaluator checks for framing)
    """
    needed = set()

    def walk(pred):
        kind = pred["pred"]
        if kind == "min_blocks_of":
            needed.update(pred["types"])
        elif kind == "any_of":
            for opt in pred["options"]:
                walk(opt)
        elif kind == "has_structure":
            needed.update(pd._STRUCTURE_BLOCKS.get(pred["id"], set()))
        elif kind == "contextual_framing":
            needed.add("callout")
        else:
            raise AssertionError(f"unknown predicate {kind!r} — extend the coverage walk")

    for desc in pd.DESCRIPTORS.values():
        for pred in desc.get("require", []):
            walk(pred)
    return needed


class ScaffoldPaletteConsistency(unittest.TestCase):
    def test_every_named_block_token_is_a_real_block_type(self):
        tokens = _backtick_tokens(_rule_text())
        # the rule names content shapes plus block types and recipe sub-names; the block-type tokens are
        # exactly those that are not recipe names. Each of those MUST resolve to a canonical block.
        block_tokens = {t for t in tokens if t not in _RECIPE_NAMES and t not in _PRODUCER_NAMES}
        # only assert over tokens that look like single block identifiers (no spaces / slashes)
        block_tokens = {t for t in block_tokens if re.fullmatch(r"[a-z][a-z0-9-]+", t)}
        self.assertTrue(block_tokens, "the rule names no block types — it teaches nothing")
        unknown = sorted(t for t in block_tokens if t not in _BLOCK_UNIVERSE)
        self.assertFalse(
            unknown,
            f"the type→format rule names block types absent from render.BLOCK_SCHEMAS / aliases: {unknown}",
        )

    def test_recipe_names_named_are_real_recipes(self):
        # a light guard: the chart/diagram recipe sub-names the rule lists must be real recipes.
        tokens = _backtick_tokens(_rule_text())
        named_recipes = {t for t in tokens if t in _RECIPE_NAMES}
        self.assertTrue(named_recipes, "the rule lists no chart/diagram recipes")
        self.assertTrue(named_recipes.issubset(_RECIPE_NAMES))


class DescriptorScaffoldCoverage(unittest.TestCase):
    def test_every_descriptor_floor_block_is_taught_by_the_rule(self):
        rule = _rule_text()
        named = _backtick_tokens(rule)
        # canonicalize named tokens through the alias table so a rule that says `metrics` covers a floor
        # that needs `metrics-grid`, etc.
        named_canonical = {render._BLOCK_TYPE_ALIASES.get(t, t) for t in named}

        needed = _descriptor_floor_block_types()
        missing = sorted(
            t for t in needed
            if render._BLOCK_TYPE_ALIASES.get(t, t) not in named_canonical and t not in named
        )
        self.assertFalse(
            missing,
            f"a producer descriptor's floor can be satisfied by these blocks, but the type→format rule "
            f"never names them (writers aren't taught to satisfy their floor): {missing}",
        )


if __name__ == "__main__":
    unittest.main()
