"""runstore — content-addressed, forgery/tamper-evident record of internal measurement runs (S3a, R8)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog  # noqa: E402
import runstore  # noqa: E402


class RunStore(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.log = Path(self._d.name) / "log.jsonl"

    def tearDown(self):
        self._d.cleanup()

    def test_record_returns_address_and_resolves(self):
        addr = runstore.record_run("run-1", {"AUC": 85.0, "exact_match": 0.167}, log=self.log)
        run = runstore.resolve(addr, log=self.log)
        self.assertIsNotNone(run)
        self.assertEqual(run["values"]["AUC"], 85.0)

    def test_attest_matching_value(self):
        addr = runstore.record_run("run-1", {"AUC": 85.0}, log=self.log)
        ok, _ = runstore.attest_value(addr, "AUC", 85.0, log=self.log)
        self.assertTrue(ok)

    def test_attest_mismatch_fails_closed(self):
        addr = runstore.record_run("run-1", {"AUC": 85.0}, log=self.log)
        ok, reason = runstore.attest_value(addr, "AUC", 99.9, log=self.log)
        self.assertFalse(ok)
        self.assertIn("mismatch", reason)

    def test_unknown_address_fails_closed(self):
        ok, _ = runstore.attest_value("deadbeef", "AUC", 1.0, log=self.log)
        self.assertFalse(ok)

    def test_missing_metric_fails_closed(self):
        addr = runstore.record_run("run-1", {"AUC": 85.0}, log=self.log)
        ok, _ = runstore.attest_value(addr, "exact_match", 0.1, log=self.log)
        self.assertFalse(ok)

    def test_tamper_edit_breaks_resolution(self):
        # editing the recorded values in the log does NOT change the cited address → the tampered record
        # no longer matches its address → unresolved (fail-closed). The eventlog is the durable truth.
        addr = runstore.record_run("run-1", {"AUC": 85.0}, log=self.log)
        lines = self.log.read_text().splitlines()
        ev = json.loads(lines[-1])
        ev["payload"]["values"]["AUC"] = 1.0
        lines[-1] = json.dumps(ev)
        self.log.write_text("\n".join(lines) + "\n")
        self.assertIsNone(runstore.resolve(addr, log=self.log))

    def test_forged_record_at_cited_address_cannot_attest(self):
        # genuine run-1 {AUC:85} at address A. An attacker appends a run.recorded with the SAME run_id,
        # different values {AUC:99}, and a forged payload `address` set to A. Because resolve recomputes
        # the content address, the forged record (whose true address is B) is skipped; A still resolves
        # only to the genuine {AUC:85}. So attesting AUC=99 at A fails; AUC=85 still passes.
        addr = runstore.record_run("run-1", {"AUC": 85.0}, log=self.log)
        eventlog.append(runstore.RUN_EVENT, "run-1",
                        {"run_id": "run-1", "values": {"AUC": 99.0}, "address": addr}, log=self.log)
        ok99, _ = runstore.attest_value(addr, "AUC", 99.0, log=self.log)
        ok85, _ = runstore.attest_value(addr, "AUC", 85.0, log=self.log)
        self.assertFalse(ok99)   # forged value rejected
        self.assertTrue(ok85)    # genuine value still attests

    def test_directly_appended_malformed_record_does_not_resolve_or_attest(self):
        # Codex S3a #2: a record appended straight to the log (bypassing record_run's write contract)
        # with a non-numeric value must NOT resolve and must NOT attest — the read side re-validates.
        for bad_values in ({"AUC": True}, {"AUC": "high"}, {"AUC": {"nested": 1}}):
            addr = runstore.content_address("run-x", bad_values)
            eventlog.append(runstore.RUN_EVENT, "run-x",
                            {"run_id": "run-x", "values": bad_values, "address": addr}, log=self.log)
            self.assertIsNone(runstore.resolve(addr, log=self.log))
            ok, _ = runstore.attest_value(addr, "AUC", 1.0, log=self.log)
            self.assertFalse(ok)

    def test_bool_cited_value_is_rejected(self):
        # Codex S3a #2: even against a genuine numeric record, a bool cited value (True == 1.0) is
        # rejected before comparison.
        addr = runstore.record_run("run-1", {"AUC": 1.0}, log=self.log)
        ok, reason = runstore.attest_value(addr, "AUC", True, log=self.log)
        self.assertFalse(ok)
        self.assertIn("finite non-bool", reason)

    def test_unhashable_or_nonstring_metric_fails_closed_not_crash(self):
        # Codex S3a #3: a malformed cited metric (unhashable list/dict, or None) must fail closed, not
        # crash the membership check.
        addr = runstore.record_run("run-1", {"AUC": 1.0}, log=self.log)
        for bad_metric in (["AUC"], {"m": 1}, None, 7):
            ok, _ = runstore.attest_value(addr, bad_metric, 1.0, log=self.log)
            self.assertFalse(ok)

    def test_record_run_rejects_malformed_input(self):
        for bad in ([("", {"AUC": 1.0})] +                       # empty run_id
                    [("r", v) for v in (["x"], {}, {"AUC": "high"}, {"AUC": True},
                                        {"AUC": float("nan")}, {"AUC": float("inf")}, {1: 2.0})]):
            with self.assertRaises(ValueError):
                runstore.record_run(bad[0], bad[1], log=self.log)


if __name__ == "__main__":
    unittest.main()
