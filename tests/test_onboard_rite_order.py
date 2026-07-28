"""The onboarding rite's ORDER is operator doctrine (2026-07-28), not an implementation
detail — it regressed twice in the field (silent install; picker battery before the
mentor). This spec pins skills/onboard/SKILL.md: the mentor opens, machine decisions
dissolve into the conversation, the wake/demo precede the mission question, sources come
after Direction, heartbeat ships off. Editing the rite means updating this spec
consciously, never by drift.
"""
import re
import unittest
from pathlib import Path

SKILL = (Path(__file__).resolve().parent.parent
         / "skills" / "onboard" / "SKILL.md").read_text(encoding="utf-8")
FLAT = " ".join(SKILL.split())   # whitespace-immune for clause pinning


class RiteOrder(unittest.TestCase):
    def test_sections_in_canonical_order(self):
        marks = [
            "## 0-pre. Host reconnaissance",        # vasculhada first, silent
            "## 0. The rite opens as the MENTOR",   # mentor voice from the first word
            "## 1. Bootstrap",
            "## 2. Runtime",
            "## 3. First wake",                     # backfill + walk-through demo
            "## 4. Emenda",                         # the grill deepens (same voice)
            "## 4b. Sources",                       # hunted AFTER Direction
            "## 5. Close",                          # phenotype born at finish
        ]
        pos = [SKILL.index(m) for m in marks]       # ValueError = section renamed/removed
        self.assertEqual(pos, sorted(pos), "rite sections out of canonical order")

    def test_mission_question_comes_after_the_demo(self):
        ask = FLAT.index('"what do you want with this edge" only lands after the walk-through')
        demo = FLAT.index("## 3. First wake")
        self.assertGreater(ask, demo)
        self.assertIn('And do NOT open with "what do you want from this edge"', FLAT)


class RiteFloor(unittest.TestCase):
    def test_one_voice_no_pickers_no_silent_install(self):
        self.assertIn("You are the **mentor, on day one**", FLAT)
        self.assertIn("never as a multiple-choice picker", FLAT)
        self.assertIn(
            "If your first question to the operator is a machine decision — name, "
            "folder, CLI — the rite has already failed", FLAT)
        self.assertIn("evidence for PROPOSALS, never an ANSWER", FLAT)

    def test_never_ask_the_deducible(self):
        self.assertIn(
            "A true open question is reserved for what no inspection can answer", FLAT)

    def test_grill_object_is_the_phenotype_person_is_the_road(self):
        self.assertIn("mutual understanding about the AGENT.YAML", FLAT)
        self.assertIn("The yaml is the destination; the person is the road.", FLAT)


class HeartbeatShipsOff(unittest.TestCase):
    def test_finish_block_has_no_ignition_and_carries_language_and_sources(self):
        m = re.search(r"```bash\n(tools/edge-python tools/edge-bootstrap finish.*?)```",
                      SKILL, re.S)
        self.assertIsNotNone(m, "finish command block missing from §5")
        block = m.group(1)
        self.assertNotIn("--enable-heartbeat", block)
        self.assertIn("--language", block)
        self.assertIn("--sources-json", block)
        self.assertIn("The heartbeat ships OFF and the rite never asks about it", FLAT)


if __name__ == "__main__":
    unittest.main()
