"""backfill_estimate — o cheque do onboarding agêntico: quanto história o lookback pega
e quanto tempo o primeiro assemble/wake deve levar. Números mecânicos; o juízo de
"absurdo" é do agente na skill, nunca um threshold no código.
"""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import onboarding  # noqa: E402


def _touch(path, age_days):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x" * (3 * 1024 * 1024))
    old = time.time() - age_days * 86400
    os.utime(path, (old, old))


class BackfillEstimate(unittest.TestCase):
    def _fake_home(self, tmp):
        home = Path(tmp)
        # claude: 2 sessões recentes (1d, 5d) + 1 velha (40d), em projetos distintos
        _touch(home / ".claude/projects/-home-a/s1.jsonl", 1)
        _touch(home / ".claude/projects/-home-b/s2.jsonl", 5)
        _touch(home / ".claude/projects/-home-a/s3.jsonl", 40)
        # codex: 1 recente aninhada por data
        _touch(home / ".codex/sessions/2026/07/s4.jsonl", 2)
        # grok: harness AUSENTE (sem ~/.grok)
        return home

    def test_counts_only_recent_files_per_installed_surface(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = self._fake_home(tmp)
            est = onboarding.backfill_estimate(30, home=home, env={})
            self.assertEqual(est["surfaces"]["claude"]["files"], 2)
            self.assertEqual(est["surfaces"]["codex"]["files"], 1)
            self.assertNotIn("grok", est["surfaces"])  # ausente = não listado
            self.assertEqual(est["files"], 3)

    def test_totals_and_minutes_scale_with_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = self._fake_home(tmp)
            small = onboarding.backfill_estimate(3, home=home, env={})
            big = onboarding.backfill_estimate(30, home=home, env={})
            self.assertLess(small["files"], big["files"])
            self.assertGreater(big["mb"], 0)
            self.assertGreater(big["est_minutes"], 0)
            self.assertGreaterEqual(big["est_minutes"], small["est_minutes"])

    def test_empty_host_is_honest_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            est = onboarding.backfill_estimate(30, home=Path(tmp), env={})
            self.assertEqual(est["files"], 0)
            self.assertEqual(est["surfaces"], {})
            self.assertEqual(est["est_minutes"], 0)


if __name__ == "__main__":
    unittest.main()
