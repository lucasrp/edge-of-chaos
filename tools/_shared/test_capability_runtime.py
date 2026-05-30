"""Characterization + unit tests for source-binding resolution.

Locks the observable output of build_source_bindings so the candidate-#1
refactor (extract pure core -> delete source.X re-projection -> rewire to read
edge-primitives directly) can be proven behaviour-preserving.
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from tools._shared import capability_runtime as cr  # noqa: E402

# --- consistent fixtures: the source.X capability rows (old path) mirror the
# primitives payload (new path), so the golden holds across the refactor. ---

FAKE_SOURCES = [
    {"name": "arxiv", "roles": ["search"], "primary": True, "status": "active", "description": "A"},
    {"name": "grafana", "roles": ["observe"], "primary": False, "status": "active", "description": "G"},
    {"name": "oldsrc", "roles": ["search"], "primary": False, "status": "", "description": "O"},
]

FAKE_PRIMITIVES = {"sources": [
    {"name": "arxiv", "effective_status": "available", "manifest_status": "active", "problems": []},
    {"name": "grafana", "effective_status": "degraded", "manifest_status": "active", "problems": ["x"]},
    {"name": "oldsrc", "effective_status": "available", "manifest_status": "suspended", "problems": []},
]}

FAKE_CAP_PAYLOAD = {"capabilities": [
    {"name": "sources.aggregate", "effective_status": "available"},
    {"name": "source.arxiv", "effective_status": "available", "manifest_status": "active", "problems": []},
    {"name": "source.grafana", "effective_status": "degraded", "manifest_status": "active", "problems": ["x"]},
    {"name": "source.oldsrc", "effective_status": "available", "manifest_status": "suspended", "problems": []},
]}


def _run_bindings():
    with mock.patch.object(cr, "_load_sources_manifest", return_value=FAKE_SOURCES), \
         mock.patch.object(cr, "build_capability_status", return_value=FAKE_CAP_PAYLOAD), \
         mock.patch.object(cr, "_load_primitives_payload", return_value=FAKE_PRIMITIVES):
        return cr.build_source_bindings()


class BuildSourceBindingsCharacterization(unittest.TestCase):
    def test_bindings_golden(self):
        out = _run_bindings()
        by_source = {b["source"]: b for b in out["bindings"]}

        # arxiv: aggregate-provider + search role + aggregate available -> bound via sources.aggregate
        self.assertEqual(by_source["arxiv"]["binding_status"], "present")
        self.assertEqual(by_source["arxiv"]["binding_mode"], "sources.aggregate")
        self.assertEqual(by_source["arxiv"]["capability"], "sources.aggregate")
        self.assertEqual(by_source["arxiv"]["evidence"]["aggregate_provider"], "arxiv")
        self.assertEqual(by_source["arxiv"]["evidence"]["primitive_status"], "available")

        # grafana: non-aggregate provider, observe-only role -> primitive branch, degraded
        self.assertEqual(by_source["grafana"]["binding_status"], "degraded")
        self.assertEqual(by_source["grafana"]["binding_mode"], "primitive")
        self.assertEqual(by_source["grafana"]["capability"], "source.grafana")
        self.assertEqual(by_source["grafana"]["problems"], ["x"])
        self.assertEqual(by_source["grafana"]["warning"], "configured_integration_binding_degraded")

        # oldsrc: manifest suspended -> suspended branch
        self.assertEqual(by_source["oldsrc"]["binding_status"], "suspended")
        self.assertEqual(by_source["oldsrc"]["binding_mode"], "suspended")
        self.assertEqual(by_source["oldsrc"]["problems"], [])

        s = out["summary"]
        self.assertEqual(s["source_total"], 3)
        self.assertEqual(s["bound_total"], 1)
        self.assertEqual(s["degraded_total"], 1)
        self.assertEqual(s["suspended_total"], 1)
        self.assertEqual(s["unbound_total"], 0)
        self.assertEqual(s["health_status"], "degraded")


class CapabilityStatusHasNoPrimitiveSpecies(unittest.TestCase):
    """Guard: the source.X primitive re-projection is gone. Capability status
    only carries external_cli rows; primitive health lives in edge-primitives."""

    def test_no_primitive_rows(self):
        with mock.patch.object(cr, "_load_static_registry", return_value=[]), \
             mock.patch.object(cr, "_collect_capability_events", return_value=({}, {})), \
             mock.patch.object(cr, "_load_primitives_payload", return_value=FAKE_PRIMITIVES):
            payload = cr.build_capability_status()
        rows = payload.get("capabilities") or []
        self.assertEqual([r for r in rows if r.get("kind") == "primitive"], [])
        self.assertFalse(any(str(r.get("name", "")).startswith("source.") for r in rows))


if __name__ == "__main__":
    unittest.main()
