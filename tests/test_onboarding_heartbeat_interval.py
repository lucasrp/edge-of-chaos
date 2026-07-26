"""O intervalo do heartbeat vem da ENTREVISTA (operador 2026-07-25) — atravessa
bootstrap_cfg e emit_phenotype até o agent.yaml; default 8h quando não perguntado.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import onboarding  # noqa: E402
import runtime_policy  # noqa: E402


def _cfg(**kw):
    return onboarding.bootstrap_cfg(
        home=kw.pop("home"), name="t", backfill_days=3,
        adversarials={"mode": "self", "members": ["self"], "primary": "hermes"},
        embedding=None, **kw)


class HeartbeatInterval(unittest.TestCase):
    def test_cfg_default_is_8h(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(_cfg(home=tmp)["heartbeat_interval"], "8h")

    def test_interviewed_interval_reaches_cfg(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(_cfg(home=tmp, heartbeat_interval="3h")["heartbeat_interval"], "3h")

    def test_finish_rejects_heartbeat_before_emit_or_systemd(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            phenotype = Path(tmp) / "agent.yaml"
            phenotype.write_text("{}")
            fake_grill = SimpleNamespace(assert_grill_complete=lambda **kw: calls.append("grill"))
            fake_eventlog = SimpleNamespace(LOG=Path(tmp) / "events.jsonl")
            fake_provision = SimpleNamespace(
                install_heartbeat=lambda *a, **kw: calls.append("systemd")
            )
            with mock.patch.dict(
                sys.modules,
                {"grill_gate": fake_grill, "eventlog": fake_eventlog, "_provision": fake_provision},
            ), mock.patch.object(
                onboarding, "emit_phenotype", side_effect=lambda *a, **kw: calls.append("emit") or phenotype
            ):
                with self.assertRaises(runtime_policy.RuntimePolicyError):
                    onboarding.finish_onboarding(tmp, enable_heartbeat=True)
            self.assertEqual(calls, [])

    def test_emit_carries_the_interval_into_agent_yaml(self):
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            onboarding.run_bootstrap(home=tmp, name="t", backfill_days=3,
                                     provision_skills=False)
            path = onboarding.emit_phenotype(tmp, heartbeat_interval="12h")
            cfg = yaml.safe_load(Path(path).read_text())
            self.assertEqual(cfg["heartbeat_interval"], "12h")


if __name__ == "__main__":
    unittest.main()
