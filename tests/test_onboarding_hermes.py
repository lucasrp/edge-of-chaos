"""Hermes na cadeia do onboarding — 4ª CLI padrão (operador 2026-07-25).

(1) Estimador: sessões do hermes vivem em SQLite (HERMES_HOME/state.db, sessions.started_at)
— o backfill_estimate conta lá, não em glob de jsonl. (2) Adversarial: `--adversarial hermes`
vira rota review_hermes provider=hermes, SEM modelo hardcoded (o default de modelo é do
`hermes setup` de cada usuário — genérico por construção). (3) Primário hermes é legal.
"""
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import onboarding  # noqa: E402
import _hermes_provision  # noqa: E402


def _mk_hermes_db(home, started_days_ago):
    hh = Path(home) / ".hermes"
    hh.mkdir(parents=True, exist_ok=True)
    db = hh / "state.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT, started_at REAL)")
    now = time.time()
    for i, d in enumerate(started_days_ago):
        conn.execute("INSERT INTO sessions VALUES (?, ?)", (f"s{i}", now - d * 86400))
    conn.commit()
    conn.close()


class HermesEstimate(unittest.TestCase):
    def test_counts_recent_hermes_sessions_from_sqlite(self):
        with tempfile.TemporaryDirectory() as tmp:
            _mk_hermes_db(tmp, [1, 5, 40])
            est = onboarding.backfill_estimate(30, home=Path(tmp), env={})
            self.assertEqual(est["surfaces"]["hermes"]["files"], 2)

    def test_hermes_absent_stays_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            est = onboarding.backfill_estimate(30, home=Path(tmp), env={})
            self.assertNotIn("hermes", est["surfaces"])

    def test_hermes_home_without_db_is_zero_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".hermes").mkdir()
            est = onboarding.backfill_estimate(30, home=Path(tmp), env={})
            self.assertEqual(est["surfaces"]["hermes"]["files"], 0)


class HermesAdversarialAndRouters(unittest.TestCase):
    def test_hermes_member_maps_to_review_hermes_route_without_model(self):
        cast = onboarding.resolve_adversarial_cast(["hermes"], primary="claude")
        adv = onboarding._adversarials_for_cfg(cast, "claude")
        self.assertEqual(adv["hermes"]["route"], "review_hermes")
        self.assertEqual(adv["hermes"]["auth"], "subscription")
        self.assertNotIn("model", {k: v for k, v in adv["hermes"].items() if v})
        routers = onboarding._routers_for_cfg(cast, "claude", None)
        self.assertEqual(routers["review_hermes"]["provider"], "hermes")
        self.assertIsNone(routers["review_hermes"].get("model"))

    def test_hermes_primary_routes_chat_to_hermes(self):
        cast = onboarding.resolve_adversarial_cast([], primary="hermes")
        routers = onboarding._routers_for_cfg(cast, "hermes", None)
        self.assertEqual(routers["chat"]["provider"], "hermes")


class HermesOnboardingGroup(unittest.TestCase):
    def test_default_is_origin_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertTrue(_hermes_provision.configure_hermes_group(root, ""))
            cfg = __import__("yaml").safe_load((root / "config.yaml").read_text())
            self.assertEqual(cfg["edge_group"], "")


if __name__ == "__main__":
    unittest.main()
