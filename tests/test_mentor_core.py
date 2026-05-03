from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from edge_core.rite import verify_rite
from edge_core.threads import primary_thread_from_review


ROOT = Path(__file__).resolve().parents[1]


class MentorCoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="edge-v2-test-"))
        for name in ["edge_core", "tools", "agent.yaml.example", "blog", "reports", "state", "config"]:
            source = ROOT / name
            target = self.tmp / name
            if source.is_dir():
                shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                shutil.copy2(source, target)
        (self.tmp / "agent.yaml").write_text(
            """
name: test
codename: tst
language: pt-BR
mission: "Mentor test"
domain: "tests"
workspaces:
  - name: fixture
    path: "."
    kind: repo
sources:
  - name: hackernews
    enabled: false
first_steps:
  - "Read context"
interests:
  - area: "Testing"
    connection: "Verify mentor core"
""",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def run_edge(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.pop("OPENAI_API_KEY", None)
        env["EDGE_DISABLE_CLAUDE_FALLBACK"] = "1"
        return subprocess.run(
            ["python3", "tools/edge", *args],
            cwd=self.tmp,
            env=env,
            text=True,
            capture_output=True,
            timeout=30,
        )

    def test_render_apply_doctor_and_report(self) -> None:
        self.assertEqual(self.run_edge("render").returncode, 0)
        self.assertEqual(self.run_edge("apply").returncode, 0)
        doctor = self.run_edge("doctor")
        self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
        report = self.run_edge("report", "testar continuidade")
        self.assertEqual(report.returncode, 0, report.stdout + report.stderr)
        self.assertTrue(list((self.tmp / "reports").glob("*.md")))
        self.assertTrue((self.tmp / "state" / "events.jsonl").exists())
        self.assertTrue(list((self.tmp / "state" / "threads").glob("*.md")))
        ledger = (self.tmp / "state" / "events.jsonl").read_text(encoding="utf-8")
        self.assertIn("DeltaPrepared", ledger)
        self.assertIn("ContextReadinessReviewed", ledger)
        self.assertIn("BroadSearchCompleted", ledger)
        self.assertIn("ReportDrafted", ledger)
        self.assertIn("ReportReviewed", ledger)
        self.assertIn("method-review", ledger)
        self.assertIn("RiteVerified", ledger)
        self.assertIn("CycleClosed", ledger)

    def test_rite_requires_method_review(self) -> None:
        events = [
            {"type": "CycleOpened"},
            {"type": "DeltaPrepared"},
            {"type": "ContextReadinessReviewed"},
            {"type": "BroadSearchCompleted", "results": 1},
            {"type": "ReportDrafted"},
            {"type": "ReportReviewed", "reviewer": "llm:adversarial"},
            {"type": "ReportReviewed", "reviewer": "llm:general-review"},
            {"type": "ReportReviewed", "reviewer": "llm:feynman-review"},
            {"type": "ReportWritten"},
            {"type": "ThreadUpdated"},
            {"type": "DigestRebuilt"},
            {"type": "BlogBuilt"},
        ]
        check = verify_rite(events)
        self.assertFalse(check.passed)
        self.assertIn("review:method-review", check.missing)

    def test_primary_thread_accepts_llm_string(self) -> None:
        primary = primary_thread_from_review({"primary_thread": "Mentoria privada persistente"}, "heartbeat")
        self.assertEqual(primary["thread_id"], "mentoria-privada-persistente")
        self.assertEqual(primary["title"], "Mentoria privada persistente")


if __name__ == "__main__":
    unittest.main()
