"""PB-5 same-identity residual-risk proof."""
import json
import unittest

from tools import credential_boundary_probe as probe


class SameIdentityResidualRisk(unittest.TestCase):
    def test_fake_tool_reads_fake_auth_and_terminal_gate_rejects_it(self):
        receipt = probe.run_same_identity_negative_proof()
        self.assertTrue(receipt["same_identity_readable"])
        self.assertTrue(receipt["terminal_gate_rejected_tool"])
        self.assertFalse(receipt["preventive_isolation_from_same_identity"])
        self.assertFalse(receipt["content_returned"])
        self.assertFalse(receipt["real_auth_read"])
        self.assertNotIn("EDGE_SYNTHETIC_BOUNDARY_", json.dumps(receipt))


if __name__ == "__main__":
    unittest.main()
