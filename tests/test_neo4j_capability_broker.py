"""Hermetic contract tests: no Neo4j, sockets, services, secrets, LLMs, or network."""
import json
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import neo4j_capability_broker as broker  # noqa: E402
import neo4j_capability_protocol as protocol  # noqa: E402


class FixtureBackend:
    def __init__(self):
        self.calls = []
        self.payload = {"nodes": [{"slug": "safe", "title": "A safe memory"}]}

    def _call(self, name, group, **arguments):
        self.calls.append((name, group, arguments))
        return self.payload

    def health(self, *, group):
        self.calls.append(("health", group, {}))
        return True

    def recall(self, *, group):
        return self._call("recall", group)

    def surf(self, *, group, seeds, hops):
        return self._call("surf", group, seeds=seeds, hops=hops)

    def node(self, *, group, ref):
        return self._call("node", group, ref=ref)

    def search(self, *, group, query, limit):
        return self._call("search", group, query=query, limit=limit)


def request(operation, arguments=None, **extra):
    value = {
        "version": protocol.PROTOCOL_VERSION,
        "request_id": "dispatch-1:call-1",
        "operation": operation,
        "arguments": arguments or {},
    }
    value.update(extra)
    return value


class ClosedProtocol(unittest.TestCase):
    def test_exact_operation_allowlist(self):
        self.assertEqual(
            protocol.operation_names(), {"health", "recall", "surf", "node", "search"}
        )

    def test_cypher_mutation_group_path_and_command_fields_are_rejected(self):
        for field, value in (
            ("cypher", "MATCH (n) DETACH DELETE n"),
            ("group", "another-tenant"),
            ("path", "/home/operator/edge-install/secrets/neo4j.env"),
            ("command", "id"),
            ("write", True),
        ):
            with self.subTest(field=field):
                raw = request("recall", {field: value})
                with self.assertRaises(protocol.ProtocolError):
                    protocol.validate_request(raw)

    def test_unknown_top_level_fields_and_operations_are_rejected(self):
        with self.assertRaises(protocol.ProtocolError):
            protocol.validate_request(request("recall", token="not-authorized-yet"))
        with self.assertRaises(protocol.ProtocolError):
            protocol.validate_request(request("delete", {}))

    def test_unknown_secret_shaped_field_is_not_reflected_in_error(self):
        raw = request("recall", {"EDGE_NEO4J_PASSWORD=canary": True})
        with self.assertRaises(protocol.ProtocolError) as caught:
            protocol.validate_request(raw)
        self.assertNotIn("canary", str(caught.exception))

    def test_surf_and_search_are_strictly_bounded(self):
        invalid = (
            request("surf", {"seeds": [], "hops": 1}),
            request("surf", {"seeds": ["x"] * (protocol.MAX_SEEDS + 1), "hops": 1}),
            request("surf", {"seeds": ["x"], "hops": 3}),
            request("search", {"query": "", "limit": 1}),
            request("search", {"query": "x", "limit": protocol.MAX_SEARCH_RESULTS + 1}),
        )
        for raw in invalid:
            with self.subTest(raw=raw):
                with self.assertRaises(protocol.ProtocolError):
                    protocol.validate_request(raw)


class BrokerBoundary(unittest.TestCase):
    def setUp(self):
        self.backend = FixtureBackend()
        self.audit = []
        self.broker = broker.CapabilityBroker(
            group="example-group", backend=self.backend, audit=self.audit.append, clock=lambda: 10.0
        )

    def test_group_is_fixed_by_broker_not_request(self):
        out = self.broker.handle(request("search", {"query": "memory", "limit": 5}))
        self.assertTrue(out["ok"])
        self.assertEqual(
            self.backend.calls,
            [("search", "example-group", {"query": "memory", "limit": 5})],
        )

    def test_health_exposes_no_connection_or_credential_detail(self):
        out = self.broker.handle(request("health"))
        self.assertEqual(out["result"], {"ready": True, "protocol": protocol.PROTOCOL_VERSION})

    def test_sensitive_keys_values_and_private_paths_are_sanitized(self):
        self.backend.payload = {
            "safe": "visible",
            "password": "canary-password",
            "nested": {
                "api_token": "canary-token",
                "assignment": "EDGE_NEO4J_PASSWORD=canary",
                "uri": "neo4j://neo4j:canary@127.0.0.1:7687",
                "path": "/home/operator/edge-install/secrets/neo4j.env",
            },
        }
        out = self.broker.handle(request("recall"))
        encoded = json.dumps(out)
        self.assertNotIn("canary", encoded)
        self.assertNotIn("password", encoded.lower())
        self.assertNotIn("/home/operator", encoded)
        self.assertEqual(out["result"]["safe"], "visible")
        self.assertEqual(out["result"]["nested"]["assignment"], "[REDACTED]")

    def test_oversized_response_fails_closed(self):
        self.backend.payload = {"nodes": ["x" * broker.MAX_STRING_LENGTH] * 100}
        out = self.broker.handle(request("recall"))
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"]["code"], "bounded_failure")
        self.assertNotIn("nodes", out)

    def test_backend_exception_fails_dark_without_detail(self):
        def fail(*, group):
            raise RuntimeError("EDGE_NEO4J_PASSWORD=should-not-cross")

        self.backend.recall = fail
        out = self.broker.handle(request("recall"))
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"]["code"], "backend_unavailable")
        self.assertNotIn("should-not-cross", json.dumps(out))

    def test_audit_contains_metadata_not_arguments_or_payload(self):
        self.broker.handle(request("search", {"query": "private search phrase", "limit": 3}))
        event = self.audit[-1]
        self.assertEqual(set(event), {
            "request_id", "operation", "outcome", "duration_ms", "response_bytes"
        })
        self.assertNotIn("private search phrase", json.dumps(event))

    def test_invalid_request_never_calls_backend(self):
        out = self.broker.handle(request("recall", {"cypher": "MATCH (n) RETURN n"}))
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"]["code"], "invalid_request")
        self.assertEqual(self.backend.calls, [])

    def test_audit_sink_failure_does_not_break_a_bounded_read(self):
        def broken_audit(_event):
            raise RuntimeError("audit unavailable")

        bounded = broker.CapabilityBroker(
            group="example-group", backend=self.backend, audit=broken_audit, clock=lambda: 10.0
        )
        out = bounded.handle(request("recall"))
        self.assertTrue(out["ok"])

    def test_broker_source_has_no_live_secret_or_graph_dependency(self):
        source = (REPO / "tools" / "neo4j_capability_broker.py").read_text()
        for forbidden in ("import neo4j", "import _identity", "import _secrets", "GraphDatabase"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
