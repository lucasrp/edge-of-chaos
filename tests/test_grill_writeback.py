"""grill_writeback's durable path — the grill always persists to the log (ADR-0006).

A grill that cannot reach Neo4j must still persist its decision: append_event lands the event
on the Tier-0 log via eventlog, with no graph/driver involved. The graph catches up later by
projection. This pins the stranded-grill fix (issue #9 item 3).
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog  # noqa: E402
import grill_writeback  # noqa: E402


class LevelingWritebackPersistsThePersona(unittest.TestCase):
    """The grill's persona writeback (grill-design.md, exemplar §'A persistência JÁ EXISTE em
    protótipo'): perfil/mapa/curriculo/diario land under memory/leveling/ — perfil, mapa and
    curriculo are current-state (overwrite); diario is append-only (the ordinal record). This is
    the custo-de-reconstrução→0 rail: what persists is what the next grill opens with."""

    def test_perfil_is_current_state_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            grill_writeback.leveling("perfil", "v1: gosta de papel", root=tmp, log=log)
            p = grill_writeback.leveling("perfil", "v2: matemática é o forte", root=tmp, log=log)
            text = Path(p).read_text()
            self.assertIn("matemática é o forte", text)
            self.assertNotIn("v1", text)
            self.assertEqual(Path(p), Path(tmp) / "perfil.md")

    def test_diario_appends_ordinally(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            grill_writeback.leveling("diario", "sessão 1: placar RRF", root=tmp, log=log)
            p = grill_writeback.leveling("diario", "sessão 2: mapa antes de material", root=tmp, log=log)
            text = Path(p).read_text()
            self.assertIn("sessão 1", text)
            self.assertIn("sessão 2", text)
            self.assertLess(text.index("sessão 1"), text.index("sessão 2"))

    def test_unknown_kind_is_refused_loud(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                grill_writeback.leveling("agenda", "x", root=tmp)

    def test_empty_content_is_refused_loud(self):
        # the same never-hollow rule the gate feeders follow (eventlog refuses blank bodies)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                grill_writeback.leveling("mapa", "   ", root=tmp)

    def test_leveling_mirrors_to_the_log(self):
        # ADR-0006: the log is the source of truth; the file is the readable projection.
        # A grill's persona learning must be replayable, not only a loose markdown file.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            grill_writeback.leveling("perfil", "gosta de papel", root=tmp, log=log)
            evs = eventlog.read(types=["grill.leveling"], log=log)
            self.assertEqual(evs[0]["payload"], {"kind": "perfil", "content": "gosta de papel"})

    def test_perfil_rewrite_must_preserve_dated_correction_headers(self):
        """Plan 2026-07-13 P1.4: overwrite must not drop ## Correção sections."""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            grill_writeback.leveling(
                "perfil",
                "# Perfil\n\n## Correção 2026-07-13 — persona\n- fato A\n",
                root=tmp, log=log,
            )
            with self.assertRaises(ValueError) as ctx:
                grill_writeback.leveling(
                    "perfil", "# Perfil\n\nsó o novo sem a correção\n", root=tmp, log=log)
            self.assertIn("Correção", str(ctx.exception))
            # re-author that keeps the header is allowed
            grill_writeback.leveling(
                "perfil",
                "# Perfil\n\n## Correção 2026-07-13 — persona\n- fato A\n- fato B\n",
                root=tmp, log=log,
            )
            self.assertIn("fato B", Path(tmp, "perfil.md").read_text())

class AppendEventPersistsWithoutNeo4j(unittest.TestCase):
    """append_event delegates to the log (no driver), so a grill persists even offline-from-graph."""

    def test_grill_decision_lands_on_the_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            ev = grill_writeback.append_event("direction.set", "direction", {"plan": "Z"}, log=log)
            self.assertEqual(ev["type"], "direction.set")
            self.assertEqual(eventlog.read(types=["direction.set"], log=log)[0]["payload"],
                             {"plan": "Z"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
