"""Hermetic WP-B3 authorization tests; no socket, service, secret, graph, network, or LLM."""
import json
from pathlib import Path
import sys
import unittest


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

from neo4j_capability_auth import AuthorizedBroker, CapabilityAuthority  # noqa: E402
from neo4j_capability_broker import CapabilityBroker  # noqa: E402
from neo4j_capability_protocol import PROTOCOL_VERSION  # noqa: E402


class Clock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value


class Backend:
    def __init__(self):
        self.calls = []
        self.payload = {"nodes": [{"slug": "safe-memory"}]}

    def health(self, *, group):
        self.calls.append(("health", group))
        return True

    def recall(self, *, group):
        self.calls.append(("recall", group))
        return self.payload

    def surf(self, **_kw):
        raise AssertionError("not expected")

    def node(self, **_kw):
        raise AssertionError("not expected")

    def search(self, **_kw):
        raise AssertionError("not expected")


def request(operation="recall", request_id="call-1"):
    return {
        "version": PROTOCOL_VERSION,
        "request_id": request_id,
        "operation": operation,
        "arguments": {},
    }


class DispatchCapabilities(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.counter = 0

        def tokens():
            self.counter += 1
            return f"capability-{self.counter:04d}-" + "x" * 32

        self.authority = CapabilityAuthority(clock=self.clock, token_factory=tokens)
        self.backend = Backend()
        self.audit = []
        core = CapabilityBroker(group="example-group", backend=self.backend, clock=self.clock)
        self.broker = AuthorizedBroker(core, self.authority, audit=self.audit.append)
        self.token = self.authority.issue(
            dispatch_id="dispatch-1",
            operations={"health", "recall"},
            ttl_seconds=60,
            call_budget=3,
            byte_budget=4096,
        )

    def envelope(self, *, token=None, dispatch_id="dispatch-1", raw=None):
        return {
            "capability": self.token if token is None else token,
            "dispatch_id": dispatch_id,
            "request": raw or request(),
        }

    def test_valid_capability_is_bound_to_dispatch_and_operation(self):
        out = self.broker.handle(self.envelope())
        self.assertTrue(out["ok"])
        self.assertEqual(self.backend.calls, [("recall", "example-group")])
        state = self.authority.snapshot(self.token)
        self.assertEqual(state["calls_remaining"], 2)
        self.assertLess(state["bytes_remaining"], 4096)

    def test_raw_token_is_not_retained_or_returned(self):
        state_text = repr(self.authority.__dict__)
        self.assertNotIn(self.token, state_text)
        output = json.dumps(self.broker.handle(self.envelope()))
        self.assertNotIn(self.token, output)

    def test_wrong_token_dispatch_or_operation_is_denied_before_backend(self):
        attempts = (
            self.envelope(token="z" * 48),
            self.envelope(dispatch_id="dispatch-2"),
            self.envelope(raw=request("search")),
        )
        for number, envelope in enumerate(attempts, start=1):
            envelope["request"]["request_id"] = f"denied-{number}"
            with self.subTest(number=number):
                out = self.broker.handle(envelope)
                self.assertEqual(out["error"]["code"], "capability_denied")
        self.assertEqual(self.backend.calls, [])

    def test_replay_of_request_id_is_denied(self):
        self.assertTrue(self.broker.handle(self.envelope())["ok"])
        out = self.broker.handle(self.envelope())
        self.assertEqual(out["error"]["code"], "capability_denied")
        self.assertEqual(len(self.backend.calls), 1)

    def test_expiry_and_revocation_apply_to_next_call(self):
        self.clock.value = 160.0
        self.assertEqual(self.broker.handle(self.envelope())["error"]["code"], "capability_denied")
        fresh = self.authority.issue(
            dispatch_id="dispatch-1", operations={"recall"}, ttl_seconds=60,
            call_budget=1, byte_budget=1024,
        )
        self.assertTrue(self.authority.revoke(fresh))
        out = self.broker.handle(self.envelope(token=fresh, raw=request(request_id="fresh-call")))
        self.assertEqual(out["error"]["code"], "capability_denied")
        self.assertEqual(self.backend.calls, [])

    def test_call_budget_is_exhausted(self):
        token = self.authority.issue(
            dispatch_id="dispatch-1", operations={"recall"}, ttl_seconds=60,
            call_budget=1, byte_budget=4096,
        )
        self.assertTrue(self.broker.handle(
            self.envelope(token=token, raw=request(request_id="budget-1"))
        )["ok"])
        out = self.broker.handle(self.envelope(token=token, raw=request(request_id="budget-2")))
        self.assertEqual(out["error"]["code"], "capability_denied")

    def test_byte_budget_blocks_output_and_exhausts_grant(self):
        token = self.authority.issue(
            dispatch_id="dispatch-1", operations={"recall"}, ttl_seconds=60,
            call_budget=2, byte_budget=1,
        )
        out = self.broker.handle(self.envelope(token=token, raw=request(request_id="bytes-1")))
        self.assertEqual(out["error"]["code"], "capability_denied")
        self.assertNotIn("result", out)
        state = self.authority.snapshot(token)
        self.assertEqual(state["bytes_remaining"], 0)

    def test_unknown_envelope_fields_and_missing_capability_fail_closed(self):
        extra = self.envelope()
        extra["group"] = "other-tenant"
        missing = {"dispatch_id": "dispatch-1", "request": request("recall", "missing")}
        for envelope in (extra, missing):
            self.assertEqual(
                self.broker.handle(envelope)["error"]["code"], "capability_denied"
            )
        self.assertEqual(self.backend.calls, [])

    def test_audit_contains_no_token_arguments_or_payload(self):
        self.broker.handle(self.envelope())
        encoded = json.dumps(self.audit)
        self.assertNotIn(self.token, encoded)
        self.assertNotIn("safe-memory", encoded)
        self.assertEqual(set(self.audit[-1]), {
            "dispatch_id", "request_id", "operation", "outcome", "response_bytes"
        })

    def test_denied_untrusted_ids_are_not_reflected_into_audit(self):
        envelope = self.envelope(dispatch_id="EDGE_NEO4J_PASSWORD=canary")
        envelope["request"]["request_id"] = "token=second-canary"
        self.broker.handle(envelope)
        encoded = json.dumps(self.audit[-1])
        self.assertNotIn("canary", encoded)
        self.assertIsNone(self.audit[-1]["dispatch_id"])
        self.assertIsNone(self.audit[-1]["request_id"])

    def test_issue_rejects_unbounded_or_mutating_grants(self):
        bad = (
            {"operations": {"delete"}, "ttl_seconds": 1, "call_budget": 1, "byte_budget": 1},
            {"operations": {"recall"}, "ttl_seconds": 3601, "call_budget": 1, "byte_budget": 1},
            {"operations": {"recall"}, "ttl_seconds": 1, "call_budget": 101, "byte_budget": 1},
            {"operations": {"recall"}, "ttl_seconds": 1, "call_budget": 1, "byte_budget": 4194305},
        )
        for kwargs in bad:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.authority.issue(dispatch_id="dispatch-x", **kwargs)

    def test_auth_source_has_no_live_secret_graph_socket_or_service_dependency(self):
        source = (REPO / "tools" / "neo4j_capability_auth.py").read_text()
        for forbidden in (
            "import neo4j", "import _identity", "import _secrets", "import socket", "systemctl"
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
