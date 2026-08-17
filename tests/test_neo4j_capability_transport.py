"""Hermetic Unix transport and Cortex adapter tests; no live graph or service."""
import json
import os
from pathlib import Path
import socket
import stat
import sys
import tempfile
import threading
import unittest


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

from neo4j_capability_backend import CortexReadBackend  # noqa: E402
from neo4j_capability_auth import AuthorizedBroker, CapabilityAuthority  # noqa: E402
from neo4j_capability_broker import CapabilityBroker  # noqa: E402
from neo4j_capability_protocol import PROTOCOL_VERSION  # noqa: E402
import neo4j_capability_transport as transport  # noqa: E402


def request(operation="health", arguments=None):
    return {
        "version": PROTOCOL_VERSION,
        "request_id": "dispatch-2:call-1",
        "operation": operation,
        "arguments": arguments or {},
    }


class FixtureBackend:
    def health(self, *, group):
        return group == "example-group"

    def recall(self, *, group):
        return {"group_seen_by_fixture": group, "nodes": [{"slug": "safe"}]}

    def surf(self, *, group, seeds, hops):
        return {"group": group, "nodes": [{"slug": seeds[0], "hops": hops}]}

    def node(self, *, group, ref):
        return {"group": group, "node": {"ref": ref}, "neighbors": []}

    def search(self, *, group, query, limit):
        return {"group": group, "results": [{"title": query}][:limit]}


class UnixTransport(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.runtime = Path(self.temp.name) / "runtime"
        self.runtime.mkdir(mode=0o700)
        os.chmod(self.runtime, 0o700)
        self.path = self.runtime / "broker.sock"
        self.core = CapabilityBroker(group="example-group", backend=FixtureBackend())

    def tearDown(self):
        self.temp.cleanup()

    def _roundtrip(self, raw=None):
        with transport.UnixBrokerServer(self.path, self.core.handle, timeout=1.0) as server:
            worker = threading.Thread(target=server.serve_once)
            worker.start()
            response = transport.call_unix(self.path, raw or request(), timeout=1.0)
            worker.join(2)
            self.assertFalse(worker.is_alive())
            return response, stat.S_IMODE(self.path.stat().st_mode)

    def test_private_unix_roundtrip_and_socket_mode(self):
        response, mode = self._roundtrip(request("recall"))
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["group_seen_by_fixture"], "example-group")
        self.assertEqual(mode, 0o600)

    def test_context_cleanup_removes_socket(self):
        with transport.UnixBrokerServer(self.path, self.core.handle, timeout=0.1):
            self.assertTrue(self.path.is_socket())
        self.assertFalse(self.path.exists())

    def test_group_or_other_access_on_runtime_directory_is_rejected(self):
        os.chmod(self.runtime, 0o750)
        with self.assertRaises(transport.TransportError):
            transport.UnixBrokerServer(self.path, self.core.handle).bind()

    def test_symlink_socket_directory_and_existing_path_are_rejected(self):
        link = Path(self.temp.name) / "linked-runtime"
        link.symlink_to(self.runtime, target_is_directory=True)
        with self.assertRaises(transport.TransportError):
            transport.UnixBrokerServer(link / "broker.sock", self.core.handle).bind()
        self.path.write_text("do not replace")
        with self.assertRaises(transport.TransportError):
            transport.UnixBrokerServer(self.path, self.core.handle).bind()
        self.assertEqual(self.path.read_text(), "do not replace")

    def test_outage_fails_without_fallback(self):
        with self.assertRaises(transport.TransportError):
            transport.call_unix(self.path, request(), timeout=0.05)

    def test_oversized_client_frame_is_rejected_before_connect(self):
        huge = request("search", {"query": "x" * transport.MAX_FRAME_BYTES, "limit": 1})
        with self.assertRaises(transport.TransportError):
            transport.call_unix(self.path, huge)

    def test_malformed_frame_returns_generic_error(self):
        with transport.UnixBrokerServer(self.path, self.core.handle, timeout=1.0) as server:
            worker = threading.Thread(target=server.serve_once)
            worker.start()
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.connect(str(self.path))
            client.sendall(b"{EDGE_NEO4J_PASSWORD=canary}\n")
            response = json.loads(client.makefile("rb").readline())
            client.close()
            worker.join(2)
        self.assertEqual(response["error"]["code"], "invalid_frame")
        self.assertNotIn("canary", json.dumps(response))

    def test_transport_source_has_no_tcp_or_secret_dependency(self):
        source = (REPO / "tools" / "neo4j_capability_transport.py").read_text()
        self.assertIn("socket.AF_UNIX", source)
        for forbidden in ("AF_INET", "import neo4j", "import _identity", "import _secrets"):
            self.assertNotIn(forbidden, source)

    def test_authorized_envelope_roundtrip_over_temporary_socket(self):
        authority = CapabilityAuthority(token_factory=lambda: "t" * 48)
        token = authority.issue(
            dispatch_id="dispatch-2", operations={"recall"}, ttl_seconds=30,
            call_budget=1, byte_budget=4096,
        )
        authorized = AuthorizedBroker(self.core, authority)
        envelope = {
            "capability": token,
            "dispatch_id": "dispatch-2",
            "request": request("recall"),
        }
        with transport.UnixBrokerServer(self.path, authorized.handle, timeout=1.0) as server:
            worker = threading.Thread(target=server.serve_once)
            worker.start()
            response = transport.call_unix(self.path, envelope, timeout=1.0)
            worker.join(2)
        self.assertTrue(response["ok"])
        self.assertNotIn(token, json.dumps(response))


class ExistingReadAdapter(unittest.TestCase):
    def setUp(self):
        self.groups = []
        self.fold = {
            "nodes": [
                {"id": "a1", "ref": "a1", "slug": "safe", "label": "Artefato", "title": "Safe memory"},
                {"id": "a2", "ref": "a2", "label": "Entity", "title": "Neighbor"},
            ],
            "edges": [{"source": "a1", "target": "a2", "type": "RELATES_TO"}],
        }
        self.backend = CortexReadBackend(
            health_fn=self._health,
            recall_fn=self._recall,
            surf_fn=self._surf,
            fold_fn=self._fold,
        )

    def _health(self, group):
        self.groups.append(group)
        return True

    def _recall(self, group):
        self.groups.append(group)
        return {"objective": "understand"}

    def _surf(self, seeds, group):
        self.groups.append(group)
        return [{"slug": seeds[0], "hops": 1}, {"slug": "too-far", "hops": 2}]

    def _fold(self, group):
        self.groups.append(group)
        return self.fold

    def test_every_adapter_read_receives_the_broker_group(self):
        core = CapabilityBroker(group="example-group", backend=self.backend)
        calls = (
            request("health"),
            request("recall"),
            request("surf", {"seeds": ["safe"], "hops": 1}),
            request("node", {"ref": "safe"}),
            request("search", {"query": "safe", "limit": 5}),
        )
        for raw in calls:
            self.assertTrue(core.handle(raw)["ok"])
        self.assertEqual(self.groups, ["example-group"] * len(calls))

    def test_surf_hop_limit_node_neighbors_and_search_limit(self):
        surf = self.backend.surf(group="example-group", seeds=["safe"], hops=1)
        self.assertEqual([row["slug"] for row in surf["nodes"]], ["safe"])
        node = self.backend.node(group="example-group", ref="safe")
        self.assertEqual(node["node"]["id"], "a1")
        self.assertEqual([row["id"] for row in node["neighbors"]], ["a2"])
        search = self.backend.search(group="example-group", query="safe", limit=1)
        self.assertEqual(len(search["results"]), 1)

    def test_importing_adapter_does_not_import_live_graph_or_secret_modules(self):
        source = (REPO / "tools" / "neo4j_capability_backend.py").read_text()
        prefix = source.split("def build_existing_cortex_backend", 1)[0]
        for forbidden in ("import recall", "import neo4j", "import _identity", "import _secrets"):
            self.assertNotIn(forbidden, prefix)


if __name__ == "__main__":
    unittest.main()
