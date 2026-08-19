"""Direct offline contract for publisher.project_doc (issue #130)."""

import hashlib
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import publisher  # noqa: E402
import md_to_mem  # noqa: E402


class _Result:
    def __init__(self, rows=()):
        self.rows = [dict(row) for row in rows]

    def single(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class _State:
    def __init__(self, clusters=(), communities=()):
        self.nodes = {}
        self.distills = set()
        self.clusters = list(clusters)        # Entity.curated_cluster (grill attach)
        self.communities = list(communities)  # Community.name (communities.consolidate)


class _Session:
    def __init__(self, driver):
        self.driver = driver

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def run(self, query, **params):
        self.driver.calls.append((query, dict(params)))
        state = self.driver.state
        if "MERGE (d:Doc" in query and "DISTILLS" not in query:
            node = state.nodes.setdefault((params["g"], params["slug"]), {})
            node.update({
                "group_id": params["g"], "slug": params["slug"],
                "body": params["body"], "sha256": params["sha256"],
                "threads": list(params["threads"]), "author": params["author"],
                "provenance_class": params["pc"], "projection_complete": False,
            })
            return _Result()
        if "RETURN DISTINCT e.curated_cluster AS l" in query:
            return _Result([{"l": label} for label in state.clusters])
        # the SECOND catalog the resolution reads (publisher._distill_catalog): automatic
        # Communities. communities.consolidate never stamps `curated_cluster`, so without this
        # catalog a Community-only thread could never resolve. Group-scoped, no slug param.
        if "RETURN c.name AS n" in query:
            return _Result([{"n": name} for name in state.communities])
        node = state.nodes[(params["g"], params["slug"])]
        if "RETURN d.embedding IS NOT NULL" in query:
            return _Result([{
                "e": node.get("embedding") is not None,
                "h": node.get("embedding_input_hash"),
            }])
        if "SET d.embedding=$e" in query:
            node.update({"embedding": list(params["e"]),
                         "embedding_input_hash": params["h"]})
            return _Result()
        if "[r:DISTILLS]" in query and "DELETE r" in query:
            state.distills.clear()
            return _Result()
        if "MERGE (d)-[:DISTILLS]->" in query:
            state.distills.add(params["label"])
            return _Result()
        if "SET d.pending_distills=$p" in query:
            node["pending_distills"] = list(params["p"])
            return _Result()
        if "REMOVE d.pending_distills" in query:
            node.pop("pending_distills", None)
            return _Result()
        if "SET d.projection_complete=true" in query:
            node["projection_complete"] = True
            return _Result()
        raise AssertionError(f"unexpected query: {query}")


class _Driver:
    def __init__(self, state):
        self.state = state
        self.calls = []
        self.closed = False

    def session(self):
        return _Session(self)

    def close(self):
        self.closed = True


class _Identity:
    @staticmethod
    def require_group():
        return "edge-test"

    @staticmethod
    def neo4j_conn():
        return "bolt://unused", "neo4j", "secret"


class ProjectDocContract(unittest.TestCase):
    @staticmethod
    def _payload(body="# Documento\n\nVoz curada"):
        return {
            "slug": "doc-v10", "body": body,
            "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "threads": ["cluster:alpha"], "author": "operador",
            "provenance_class": "asserted",
        }

    def test_valid_doc_merges_content_provenance_and_distills_without_network(self):
        body = "# Documento\n\nVoz curada"
        payload = self._payload(body)
        state = _State(clusters=["Alpha"])
        driver = _Driver(state)

        publisher.project_doc(
            payload, driver_factory=lambda _uri, *, auth: driver,
            identity=_Identity, embed_fn=lambda _text: [0.25, 0.75],
        )

        node = state.nodes[("edge-test", "doc-v10")]
        self.assertEqual(node["body"], body)
        self.assertEqual(node["sha256"], payload["sha256"])
        self.assertEqual(node["threads"], ["cluster:alpha"])
        self.assertEqual(node["author"], "operador")
        self.assertEqual(node["provenance_class"], "asserted")
        self.assertTrue(node["projection_complete"])
        self.assertEqual(state.distills, {"Alpha"})
        self.assertTrue(driver.closed)

    def test_reprojection_is_idempotent_and_reuses_current_embedding(self):
        payload = self._payload()
        state = _State(clusters=["Alpha"])
        drivers = []
        embed_calls = []

        def factory(_uri, *, auth):
            driver = _Driver(state)
            drivers.append(driver)
            return driver

        def embed(text):
            embed_calls.append(text)
            return [0.5]

        for _ in range(2):
            publisher.project_doc(
                payload, driver_factory=factory, identity=_Identity, embed_fn=embed,
            )

        self.assertEqual(list(state.nodes), [("edge-test", "doc-v10")])
        self.assertEqual(state.distills, {"Alpha"})
        self.assertEqual(len(embed_calls), 1)
        self.assertTrue(all(driver.closed for driver in drivers))

    def test_thread_resolves_against_an_automatic_community(self):
        # the catalog the aged double was blind to: a thread whose cluster exists only as an
        # automatic Community (never stamped `curated_cluster`) still links, and nothing pends.
        state = _State(communities=["Alpha"])
        publisher.project_doc(
            self._payload(), driver_factory=lambda _uri, *, auth: _Driver(state),
            identity=_Identity, embed_fn=lambda _text: [0.25],
        )
        self.assertEqual(state.distills, {"Alpha"})
        self.assertNotIn("pending_distills", state.nodes[("edge-test", "doc-v10")])

    def test_unresolved_thread_is_recorded_pending_never_fabricated(self):
        # no Entity, no Community: the ref is recorded for the next sweep, never invented.
        state = _State()
        publisher.project_doc(
            self._payload(), driver_factory=lambda _uri, *, auth: _Driver(state),
            identity=_Identity, embed_fn=lambda _text: [0.25],
        )
        self.assertEqual(state.distills, set())
        self.assertEqual(state.nodes[("edge-test", "doc-v10")]["pending_distills"],
                         ["cluster:alpha"])

    def test_malformed_payloads_degrade_before_opening_a_driver(self):
        valid = self._payload()
        malformed = (
            None,
            {},
            {**valid, "slug": "../escape"},
            {**valid, "body": " "},
            {**valid, "threads": "cluster:alpha"},
            {**valid, "author": "edge"},
            {**valid, "provenance_class": "curated"},
            {**valid, "sha256": "not-the-body-hash"},
        )
        for payload in malformed:
            with self.subTest(payload=payload):
                factory_calls = []

                def forbidden_factory(*args, **kwargs):
                    factory_calls.append((args, kwargs))
                    raise AssertionError("malformed input must not open a driver")

                with redirect_stdout(io.StringIO()) as output:
                    result = publisher.project_doc(
                        payload, driver_factory=forbidden_factory,
                        identity=_Identity, embed_fn=lambda _text: [1.0],
                    )

                self.assertIsNone(result)
                self.assertEqual(factory_calls, [])
                self.assertIn("malformed payload", output.getvalue())

    def test_driver_run_failure_degrades_and_always_closes_driver(self):
        class FailingSession(_Session):
            def run(self, query, **params):
                if "DELETE r" in query:
                    raise RuntimeError("graph write failed")
                return super().run(query, **params)

        class FailingDriver(_Driver):
            def session(self):
                return FailingSession(self)

        driver = FailingDriver(_State(clusters=["Alpha"]))
        with redirect_stdout(io.StringIO()) as output:
            result = publisher.project_doc(
                self._payload(),
                driver_factory=lambda _uri, *, auth: driver,
                identity=_Identity, embed_fn=lambda _text: [0.1],
            )

        self.assertIsNone(result)
        self.assertTrue(driver.closed)
        self.assertIn("doc project failed", output.getvalue())

    def test_md_to_mem_payload_derives_the_persisted_content_hash(self):
        body = "conteúdo vindo do inject"
        payload = md_to_mem.graph_episode_payload("doc-v10", body, [])
        state = _State()
        driver = _Driver(state)

        publisher.project_doc(
            payload, driver_factory=lambda _uri, *, auth: driver,
            identity=_Identity, embed_fn=lambda _text: [0.2],
        )

        node = state.nodes[("edge-test", "doc-v10")]
        self.assertEqual(
            node["sha256"], hashlib.sha256(body.encode("utf-8")).hexdigest(),
        )
        self.assertTrue(driver.closed)


if __name__ == "__main__":
    unittest.main()
