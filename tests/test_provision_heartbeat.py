"""Heartbeat via a systemd --user timer (#19, per ADR-0011).

edge-apply provisions the beat schedule: render edge-heartbeat.{service,timer} from agent.yaml
(OnUnitActiveSec from heartbeat_interval, Persistent=true), install them under
~/.config/systemd/user/, then `systemctl --user daemon-reload`, `enable --now` the timer,
`loginctl enable-linger`, and verify `claude -p` authenticates headless (no TTY). All tested pure —
systemctl is mocked, nothing is installed/enabled on this host.
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import _provision  # noqa: E402

CFG = {"heartbeat_interval": "3h", "edge_home": "~/edge/"}


class TemplatesExist(unittest.TestCase):
    def test_service_and_timer_templates_present(self):
        self.assertTrue((REPO / "templates" / "edge-heartbeat.service.tpl").exists())
        self.assertTrue((REPO / "templates" / "edge-heartbeat.timer.tpl").exists())
        self.assertTrue((REPO / "templates" / "edge-rationalize.service.tpl").exists())


class RenderUnits(unittest.TestCase):
    def test_timer_uses_interval_and_is_persistent(self):
        timer = _provision.render_heartbeat_timer(CFG, home=Path("/home/x/edge"))
        self.assertIn("OnUnitActiveSec=3h", timer)
        self.assertIn("Persistent=true", timer)
        self.assertIn("[Timer]", timer)
        self.assertNotIn("{{", timer)

    def test_service_runs_edge_heartbeat_with_home(self):
        svc = _provision.render_heartbeat_service(CFG, home=Path("/home/x/edge"))
        self.assertIn("[Service]", svc)
        self.assertIn("edge-heartbeat", svc)
        self.assertIn("--home", svc)
        self.assertIn("/home/x/edge", svc)
        self.assertNotIn("{{", svc)

    def test_rationalizer_is_a_bounded_static_oneshot_in_the_install_venv(self):
        svc = _provision.render_rationalize_service(CFG, home=Path("/home/x/edge"))

        self.assertIn("Type=oneshot", svc)
        self.assertIn("/home/x/edge/tools/edge-python", svc)
        self.assertIn("/home/x/edge/tools/sweep.py --rationalize-only", svc)
        self.assertIn("WorkingDirectory=/home/x/edge", svc)
        self.assertIn("TimeoutStartSec=30min", svc)
        self.assertIn("KillMode=control-group", svc)
        self.assertNotIn("[Timer]", svc)
        self.assertNotIn("{{", svc)


class InstallUnits(unittest.TestCase):
    def test_writes_unit_files_to_user_systemd_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "edge"
            unit_dir = Path(tmp) / ".config" / "systemd" / "user"
            calls = []
            _provision.install_heartbeat(
                CFG, home=home, unit_dir=unit_dir,
                run=lambda cmd: calls.append(list(cmd)) or type("R", (), {"returncode": 0})())
            self.assertTrue((unit_dir / "edge-heartbeat.service").exists())
            self.assertTrue((unit_dir / "edge-heartbeat.timer").exists())
            self.assertTrue((unit_dir / "edge-rationalize.service").exists())
            self.assertFalse((unit_dir / "edge-rationalize.timer").exists())
            self.assertIn("OnUnitActiveSec=3h", (unit_dir / "edge-heartbeat.timer").read_text())

    def test_runs_daemon_reload_enable_now_and_linger(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "edge"
            unit_dir = Path(tmp) / ".config" / "systemd" / "user"
            calls = []
            _provision.install_heartbeat(
                CFG, home=home, unit_dir=unit_dir,
                run=lambda cmd: calls.append(list(cmd)) or type("R", (), {"returncode": 0})())
            flat = [" ".join(c) for c in calls]
            self.assertTrue(any("daemon-reload" in f for f in flat))
            self.assertTrue(any("enable" in f and "--now" in f and "edge-heartbeat.timer" in f
                                for f in flat), flat)
            self.assertFalse(any("enable" in f and "edge-rationalize" in f for f in flat), flat)
            self.assertTrue(any("enable-linger" in f for f in flat),
                            "must enable linger so the timer runs while logged out")

    def test_fails_loud_when_systemctl_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "edge"
            unit_dir = Path(tmp) / ".config" / "systemd" / "user"
            rcs = iter([0, 1, 0, 0])   # daemon-reload ok, enable --now fails
            with self.assertRaises(RuntimeError):
                _provision.install_heartbeat(
                    CFG, home=home, unit_dir=unit_dir,
                    run=lambda cmd: type("R", (), {"returncode": next(rcs)})())


class HeadlessAuthCheck(unittest.TestCase):
    """The timer's `claude -p` runs with NO TTY — verify it authenticates non-interactively, or
    fail loud naming the gap."""

    def test_passes_when_claude_p_authenticates(self):
        calls = []

        def run(cmd):
            calls.append(list(cmd))
            return type("R", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()

        _provision.check_headless_auth(run=run)        # must not raise
        flat = [" ".join(c) for c in calls]
        self.assertTrue(any("-p" in c for c in calls), flat)

    def test_fails_loud_when_claude_p_cannot_authenticate(self):
        def run(cmd):
            return type("R", (), {"returncode": 1, "stdout": "",
                                  "stderr": "invalid api key / not logged in"})()

        with self.assertRaises(RuntimeError) as ctx:
            _provision.check_headless_auth(run=run)
        self.assertIn("headless", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
