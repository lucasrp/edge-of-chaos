"""S8 — contrato estreito do GraphStore e fake navegável (spec lentes v2)."""

import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import graph_store  # noqa: E402


class _Result:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def data(self):
        return list(self._rows)

    def single(self):
        return self._rows[0] if self._rows else {
            "merged": 1, "owners": 1, "invalidated": 1, "anchors": 1,
        }


class _Session:
    def __init__(self, owner):
        self.owner = owner
        self.calls = owner.calls
        self.rows = owner.rows
        self.error = owner.error

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def run(self, query, **params):
        if self.error:
            raise self.error
        call_index = len(self.calls)
        self.calls.append((query, params))
        rows = (self.owner.results[call_index]
                if self.owner.results is not None and call_index < len(self.owner.results)
                else self.rows)
        return _Result(rows)

    def execute_write(self, work):
        if self.error:
            raise self.error
        self.owner.write_transactions += 1
        staged = []

        class Tx:
            def run(_self, query, **params):
                if (self.owner.tx_error_at is not None
                        and len(staged) == self.owner.tx_error_at):
                    raise self.owner.tx_error
                staged.append((query, params))
                return _Result(self.rows)

        try:
            result = work(Tx())
        except Exception:
            self.owner.rollbacks += 1
            raise
        self.calls.extend(staged)
        self.owner.commits += 1
        return result


class _Driver:
    def __init__(self, rows=(), error=None, tx_error_at=None, results=None):
        self.calls = []
        self.rows = rows
        self.results = results
        self.error = error
        self.sessions = 0
        self.write_transactions = 0
        self.commits = 0
        self.rollbacks = 0
        self.tx_error_at = tx_error_at
        self.tx_error = RuntimeError("transaction failed")

    def session(self):
        self.sessions += 1
        return _Session(self)


class GraphStorePortContract(unittest.TestCase):
    def test_fake_implements_only_the_navigation_port(self):
        store = graph_store.FakeGraph()

        self.assertIsInstance(store, graph_store.GraphStore)
        for method in (
            "merge_node",
            "merge_edge",
            "replace_edges",
            "invalidate",
            "neighbors",
        ):
            self.assertTrue(callable(getattr(store, method)))
        self.assertFalse(hasattr(store, "search"))

    def test_projection_result_names_incomplete_refs_immutably(self):
        result = graph_store.ProjectionResult.incomplete(["atv:a", "map:m"])

        self.assertFalse(result.complete)
        self.assertEqual(result.incomplete_refs, ("atv:a", "map:m"))
        self.assertEqual(graph_store.ProjectionResult.success().incomplete_refs, ())

    def test_projection_result_rejects_contradictory_or_unnamed_failure(self):
        with self.assertRaises(ValueError):
            graph_store.ProjectionResult(complete=True, incomplete_refs=("atv:a",))
        with self.assertRaises(ValueError):
            graph_store.ProjectionResult(complete=False, incomplete_refs=())

    def test_both_adapters_require_positive_integer_src_seq_for_merge_and_replace(self):
        fake = graph_store.FakeGraph()
        fake.merge_node("a", "Atividade")
        fake.merge_node("b", "Claim")
        live = graph_store.Neo4jGraphStore(_Driver(), group_id="edge-test")

        for store in (fake, live):
            for bad in (None, 0, -1, True, "1"):
                props = {} if bad is None else {"src_seq": bad}
                with self.subTest(adapter=type(store).__name__, bad=bad, method="merge"):
                    with self.assertRaisesRegex(ValueError, "src_seq"):
                        store.merge_edge("a", "BEARS_ON", "b", props)
                with self.subTest(adapter=type(store).__name__, bad=bad, method="replace"):
                    with self.assertRaisesRegex(ValueError, "src_seq"):
                        store.replace_edges(
                            "a", "BEARS_ON", [graph_store.EdgeSpec("b", props)]
                        )


class Neo4jGraphStoreContract(unittest.TestCase):
    def test_merge_node_uses_group_scoped_ref_and_parameterized_props(self):
        driver = _Driver()
        store = graph_store.Neo4jGraphStore(driver, group_id="edge-test")

        store.merge_node("atv:a", "Atividade", {"num": "atv-001", "estado": "aberta"})

        self.assertIsInstance(store, graph_store.GraphStore)
        self.assertEqual(len(driver.calls), 1)
        query, params = driver.calls[0]
        self.assertIn("MERGE (n:`Atividade` {group_id:$group_id, ref:$ref})", query)
        self.assertIn("SET n += $props", query)
        self.assertEqual(params, {
            "group_id": "edge-test",
            "ref": "atv:a",
            "props": {"num": "atv-001", "estado": "aberta"},
        })

    def test_node_props_cannot_overwrite_structural_identity(self):
        driver = _Driver()
        stores = (
            graph_store.FakeGraph(),
            graph_store.Neo4jGraphStore(driver, group_id="edge-test"),
        )
        for store in stores:
            for protected in ("group_id", "ref"):
                with self.subTest(adapter=type(store).__name__, protected=protected):
                    with self.assertRaisesRegex(ValueError, protected):
                        store.merge_node("atv:a", "Atividade", {protected: "forged"})
        self.assertEqual(driver.calls, [])

    def test_merge_edge_keys_identity_by_src_seq(self):
        driver = _Driver()
        store = graph_store.Neo4jGraphStore(driver, group_id="edge-test")

        store.merge_edge(
            "atv:a", "BEARS_ON", "claim:c",
            {"src_seq": 17, "valencia": "supports", "provenance_class": "asserted"},
        )

        query, params = driver.calls[0]
        self.assertIn(
            "MERGE (src)-[r:`BEARS_ON` {src_seq:$src_seq}]->(dst)", query
        )
        self.assertEqual(params["src_seq"], 17)
        self.assertEqual(params["src_ref"], "atv:a")
        self.assertEqual(params["dst_ref"], "claim:c")
        self.assertEqual(params["props"]["valencia"], "supports")

    def test_missing_or_ambiguous_endpoints_fail_observably(self):
        for cardinality in (0, 2):
            with self.subTest(cardinality=cardinality):
                store = graph_store.Neo4jGraphStore(
                    _Driver(rows=[{"merged": cardinality}]), group_id="edge-test"
                )
                with self.assertRaisesRegex(ValueError, "exactly one.*endpoint"):
                    store.merge_edge("atv:a", "BEARS_ON", "claim:c", {"src_seq": 17})

    def test_replace_edges_requires_exactly_one_owner_and_rolls_back(self):
        driver = _Driver(rows=[{"owners": 0}])
        store = graph_store.Neo4jGraphStore(driver, group_id="edge-test")

        with self.assertRaisesRegex(ValueError, "exactly one owner"):
            store.replace_edges("atv:missing", "BEARS_ON", [])

        self.assertEqual(driver.rollbacks, 1)
        self.assertEqual(driver.commits, 0)
        self.assertEqual(driver.calls, [])

    def test_replace_edges_deletes_owned_kind_then_remerges_desired_set_in_one_session(self):
        driver = _Driver()
        store = graph_store.Neo4jGraphStore(driver, group_id="edge-test")
        desired = [
            graph_store.EdgeSpec("claim:a", {"src_seq": 31, "valencia": "supports"}),
            graph_store.EdgeSpec("claim:b", {"src_seq": 32, "valencia": "refutes"}),
        ]

        store.replace_edges(
            "atv:a", "BEARS_ON", desired, as_of="2026-07-11T12:00:00Z"
        )

        self.assertEqual(driver.sessions, 1)
        self.assertEqual(driver.write_transactions, 1)
        self.assertEqual(driver.commits, 1)
        self.assertEqual(len(driver.calls), 3)
        delete_query, delete_params = driver.calls[0]
        self.assertIn("MATCH (owner {group_id:$group_id})", delete_query)
        self.assertIn("owner.ref=$owner_ref OR owner.uuid=$owner_ref", delete_query)
        self.assertIn("(owner)-[r:`BEARS_ON`]->()", delete_query)
        self.assertIn("DELETE r", delete_query)
        self.assertEqual(delete_params["owner_ref"], "atv:a")
        self.assertEqual(
            [params["src_seq"] for _query, params in driver.calls[1:]], [31, 32]
        )
        self.assertTrue(all("MERGE (src)-[r:`BEARS_ON`" in query
                            for query, _params in driver.calls[1:]))

    def test_replace_edges_rolls_back_delete_when_a_remerge_fails(self):
        driver = _Driver(tx_error_at=1)
        store = graph_store.Neo4jGraphStore(driver, group_id="edge-test")

        with self.assertRaises(graph_store.GraphUnavailable):
            store.replace_edges(
                "atv:a",
                "BEARS_ON",
                [graph_store.EdgeSpec("claim:a", {"src_seq": 31})],
            )

        self.assertEqual(driver.write_transactions, 1)
        self.assertEqual(driver.rollbacks, 1)
        self.assertEqual(driver.commits, 0)
        self.assertEqual(driver.calls, [], "the staged DELETE must not escape rollback")

    def test_invalidate_uses_lens_props_never_graphiti_temporal_fields(self):
        driver = _Driver()
        store = graph_store.Neo4jGraphStore(driver, group_id="edge-test")

        store.invalidate("entity:old", as_of="2026-07-11T12:00:00Z")

        query, params = driver.calls[0]
        self.assertIn("SET n.archived=true, n.invalidated_at=$as_of", query)
        self.assertIn("SET r.invalidated_at=$as_of", query)
        self.assertIn("neighbor {group_id:$group_id}", query)
        self.assertNotIn("t_invalid", query)
        self.assertNotIn("DELETE n", query)
        self.assertEqual(params, {
            "group_id": "edge-test",
            "ref": "entity:old",
            "as_of": "2026-07-11T12:00:00Z",
        })

    def test_neighbors_returns_typed_hops_from_active_group_scoped_topology(self):
        neighbor_row = {
            "ref": "claim:c",
            "label": "Claim",
            "node_props": {
                "group_id": "edge-test", "ref": "claim:c", "statement": "C",
                "archived": False, "invalidated_at": None,
            },
            "edge_kind": "BEARS_ON",
            "edge_props": {"src_seq": 17, "valencia": "supports"},
            "direction": "out",
        }
        driver = _Driver(results=[[{"anchors": 1}], [neighbor_row]])
        store = graph_store.Neo4jGraphStore(driver, group_id="edge-test")

        neighbors = store.neighbors("atv:a", "BEARS_ON", direction="out")

        cardinality_query, cardinality_params = driver.calls[0]
        self.assertIn("count(anchor) AS anchors", cardinality_query)
        self.assertEqual(cardinality_params, {"group_id": "edge-test", "ref": "atv:a"})
        query, params = driver.calls[1]
        self.assertIn("(anchor)-[r:`BEARS_ON`]->(neighbor)", query)
        self.assertIn("neighbor.merged_into", query)
        self.assertIn("resolved_neighbor", query)
        self.assertIn("coalesce(resolved_neighbor.archived,false)=false", query)
        self.assertIn("resolved_neighbor.group_id=$group_id", query)
        self.assertIn("r.invalidated_at IS NULL", query)
        self.assertEqual(params, {"group_id": "edge-test", "ref": "atv:a"})
        self.assertEqual(neighbors, [graph_store.GraphNeighbor(
            ref="claim:c",
            label="Claim",
            node_props={"statement": "C"},
            edge_kind="BEARS_ON",
            edge_props={"src_seq": 17, "valencia": "supports"},
            direction="out",
        )])

    def test_live_adapter_resolves_graphiti_uuid_for_edges_navigation_and_invalidation(self):
        edge_driver = _Driver()
        store = graph_store.Neo4jGraphStore(edge_driver, group_id="edge-test")

        store.merge_edge("map:m", "PART_OF", "graphiti-uuid", {"src_seq": 9})

        edge_query, _params = edge_driver.calls[0]
        self.assertIn("src.uuid=$src_ref", edge_query)
        self.assertIn("dst.uuid=$dst_ref", edge_query)

        navigation_driver = _Driver()
        store = graph_store.Neo4jGraphStore(navigation_driver, group_id="edge-test")
        store.neighbors("graphiti-uuid", direction="out")

        cardinality_query, _params = navigation_driver.calls[0]
        neighbor_query, _params = navigation_driver.calls[1]
        self.assertIn("anchor.uuid=$ref", cardinality_query)
        self.assertIn("anchor.uuid=$ref", neighbor_query)
        self.assertIn("canonical.uuid=neighbor.merged_into", neighbor_query)
        self.assertIn(
            "coalesce(resolved_neighbor.ref, resolved_neighbor.uuid) AS ref",
            neighbor_query,
        )

        invalidate_driver = _Driver()
        store = graph_store.Neo4jGraphStore(invalidate_driver, group_id="edge-test")
        store.invalidate("graphiti-uuid")

        invalidate_query, _params = invalidate_driver.calls[0]
        self.assertIn("n.uuid=$ref", invalidate_query)

    def test_invalidate_and_neighbors_refuse_missing_or_ambiguous_anchor(self):
        for cardinality in (0, 2):
            with self.subTest(operation="invalidate", cardinality=cardinality):
                store = graph_store.Neo4jGraphStore(
                    _Driver(rows=[{"invalidated": cardinality}]), group_id="edge-test"
                )
                with self.assertRaisesRegex(ValueError, "exactly one.*anchor"):
                    store.invalidate("atv:a")
            with self.subTest(operation="neighbors", cardinality=cardinality):
                store = graph_store.Neo4jGraphStore(
                    _Driver(rows=[{"anchors": cardinality}]), group_id="edge-test"
                )
                with self.assertRaisesRegex(ValueError, "exactly one.*anchor"):
                    store.neighbors("atv:a")

    def test_all_driver_failures_cross_the_single_graph_unavailable_seam(self):
        boom = RuntimeError("driver offline")
        calls = (
            ("merge_node", lambda store: store.merge_node("a", "Atividade")),
            ("merge_edge", lambda store: store.merge_edge(
                "a", "BEARS_ON", "b", {"src_seq": 1}
            )),
            ("replace_edges", lambda store: store.replace_edges("a", "BEARS_ON", [])),
            ("invalidate", lambda store: store.invalidate("a")),
            ("neighbors", lambda store: store.neighbors("a")),
        )
        for operation, call in calls:
            with self.subTest(operation=operation):
                store = graph_store.Neo4jGraphStore(
                    _Driver(error=boom), group_id="edge-test"
                )
                with self.assertRaisesRegex(
                    graph_store.GraphUnavailable, operation
                ) as raised:
                    call(store)
                self.assertIs(raised.exception.__cause__, boom)

    def test_dynamic_labels_and_edge_kinds_refuse_cypher_injection(self):
        driver = _Driver()
        store = graph_store.Neo4jGraphStore(driver, group_id="edge-test")

        with self.assertRaises(ValueError):
            store.merge_node("a", "Atividade`) DETACH DELETE n //")
        with self.assertRaises(ValueError):
            store.merge_edge("a", "BEARS_ON]->() DELETE r //", "b", {"src_seq": 1})

        self.assertEqual(driver.calls, [])


class FakeGraphNavigation(unittest.TestCase):
    def test_merges_by_ref_and_navigates_both_directions(self):
        store = graph_store.FakeGraph()
        store.merge_node("atv:a", "Atividade", {"num": "atv-001", "state": "open"})
        store.merge_node("claim:c", "Claim", {"text": "first"})
        store.merge_node("claim:c", "Claim", {"text": "revised"})
        store.merge_edge(
            "atv:a",
            "BEARS_ON",
            "claim:c",
            {"valencia": "supports", "src_seq": 7},
        )
        # Same event/seq is a merge, not a duplicate.
        store.merge_edge(
            "atv:a",
            "BEARS_ON",
            "claim:c",
            {"valencia": "qualifies", "src_seq": 7},
        )

        outgoing = store.neighbors("atv:a", "BEARS_ON", direction="out")
        incoming = store.neighbors("claim:c", "BEARS_ON", direction="in")

        self.assertEqual(len(outgoing), 1)
        self.assertEqual(outgoing[0].ref, "claim:c")
        self.assertEqual(outgoing[0].label, "Claim")
        self.assertEqual(outgoing[0].node_props["text"], "revised")
        self.assertEqual(outgoing[0].edge_props["valencia"], "qualifies")
        self.assertEqual(outgoing[0].direction, "out")
        self.assertEqual(incoming[0].ref, "atv:a")
        self.assertEqual(incoming[0].direction, "in")

    def test_edge_identity_includes_src_seq(self):
        store = graph_store.FakeGraph()
        store.merge_node("atv:a", "Atividade")
        store.merge_node("claim:c", "Claim")
        store.merge_edge("atv:a", "BEARS_ON", "claim:c", {"src_seq": 7})
        store.merge_edge("atv:a", "BEARS_ON", "claim:c", {"src_seq": 8})

        self.assertEqual(
            {n.edge_props["src_seq"] for n in store.neighbors("atv:a")},
            {7, 8},
        )

    def test_edges_require_existing_endpoints(self):
        store = graph_store.FakeGraph()
        store.merge_node("atv:a", "Atividade")

        with self.assertRaisesRegex(ValueError, "missing graph node.*claim:c"):
            store.merge_edge("atv:a", "BEARS_ON", "claim:c")

    def test_properties_cross_the_fake_boundary_by_value(self):
        store = graph_store.FakeGraph()
        node_props = {"meta": {"state": "open"}}
        edge_props = {"src_seq": 2, "meta": {"confidence": 1}}
        store.merge_node("atv:a", "Atividade")
        store.merge_node("claim:c", "Claim", node_props)
        store.merge_edge("atv:a", "BEARS_ON", "claim:c", edge_props)
        node_props["meta"]["state"] = "caller-mutated"
        edge_props["meta"]["confidence"] = 0

        observed = store.neighbors("atv:a")[0]
        observed.node_props["meta"]["state"] = "reader-mutated"
        observed.edge_props["meta"]["confidence"] = -1
        again = store.neighbors("atv:a")[0]

        self.assertEqual(again.node_props["meta"]["state"], "open")
        self.assertEqual(again.edge_props["meta"]["confidence"], 1)

    def test_replace_edges_replaces_only_the_owned_kind_and_is_idempotent(self):
        store = graph_store.FakeGraph()
        for ref, label in (
            ("atv:a", "Atividade"),
            ("claim:old", "Claim"),
            ("claim:new", "Claim"),
            ("run:r", "Run"),
        ):
            store.merge_node(ref, label)
        store.merge_edge(
            "atv:a", "BEARS_ON", "claim:old", {"valencia": "supports", "src_seq": 3}
        )
        store.merge_edge("atv:a", "TOUCHES", "run:r", {"src_seq": 4})
        desired = [
            graph_store.EdgeSpec(
                "claim:new", {"valencia": "refutes", "src_seq": 9}
            )
        ]

        store.replace_edges("atv:a", "BEARS_ON", desired, as_of="2026-07-11T12:00:00Z")
        first = store.neighbors("atv:a")
        store.replace_edges("atv:a", "BEARS_ON", desired, as_of="2026-07-11T12:00:00Z")
        second = store.neighbors("atv:a")

        self.assertEqual(first, second)
        self.assertEqual(
            {(n.edge_kind, n.ref, n.edge_props.get("src_seq")) for n in second},
            {("BEARS_ON", "claim:new", 9), ("TOUCHES", "run:r", 4)},
        )

    def test_replace_edges_validates_entire_desired_set_before_mutating(self):
        store = graph_store.FakeGraph()
        store.merge_node("atv:a", "Atividade")
        store.merge_node("claim:old", "Claim")
        store.merge_edge("atv:a", "BEARS_ON", "claim:old", {"src_seq": 3})

        with self.assertRaisesRegex(ValueError, "missing graph node.*claim:missing"):
            store.replace_edges(
                "atv:a",
                "BEARS_ON",
                [graph_store.EdgeSpec("claim:missing", {"src_seq": 4})],
            )

        self.assertEqual(store.neighbors("atv:a")[0].ref, "claim:old")

    def test_invalidate_removes_a_node_and_incident_edges_from_navigation(self):
        store = graph_store.FakeGraph()
        store.merge_node("entity:old", "Entity")
        store.merge_node("entity:canonical", "Entity")
        store.merge_edge("entity:canonical", "SUPERSEDES", "entity:old", {"src_seq": 12})

        store.invalidate("entity:old", as_of="2026-07-11T12:00:00Z")

        self.assertEqual(store.neighbors("entity:canonical"), [])
        self.assertEqual(store.neighbors("entity:old"), [])

    def test_neighbors_retargets_merged_nodes_to_canonical_and_hides_dangling_merge(self):
        store = graph_store.FakeGraph()
        store.merge_node("atv:a", "Atividade")
        store.merge_node("entity:canonical", "Entity", {"curated_name": "Canonical"})
        store.merge_node("entity:old", "Entity", {"merged_into": "entity:canonical"})
        store.merge_node("entity:dangling", "Entity", {"merged_into": "entity:missing"})
        store.merge_edge("atv:a", "BEARS_ON", "entity:old", {"src_seq": 1})
        store.merge_edge("atv:a", "BEARS_ON", "entity:dangling", {"src_seq": 2})

        neighbors = store.neighbors("atv:a")

        self.assertEqual([neighbor.ref for neighbor in neighbors], ["entity:canonical"])
        self.assertEqual(neighbors[0].node_props["curated_name"], "Canonical")


class FakeGraphProgrammableFailure(unittest.TestCase):
    @staticmethod
    def _project(store):
        operations = (
            ("atv:a", lambda: store.merge_node("atv:a", "Atividade")),
            ("claim:c", lambda: store.merge_node("claim:c", "Claim")),
            (
                "atv:a",
                lambda: store.replace_edges(
                    "atv:a",
                    "BEARS_ON",
                    [graph_store.EdgeSpec("claim:c", {"src_seq": 21, "valencia": "supports"})],
                ),
            ),
        )
        incomplete = []
        for index, (ref, operation) in enumerate(operations):
            try:
                operation()
            except graph_store.GraphUnavailable:
                # Projection stops at the failed operation. Every ref in the untouched suffix is
                # incomplete, not merely the ref whose store call happened to raise (A33).
                incomplete.extend(row[0] for row in operations[index:])
                break
        return (
            graph_store.ProjectionResult.incomplete(incomplete)
            if incomplete
            else graph_store.ProjectionResult.success()
        )

    def test_every_port_operation_can_be_the_programmed_failure(self):
        def prepared():
            store = graph_store.FakeGraph()
            store.merge_node("a", "Atividade")
            store.merge_node("b", "Claim")
            store.merge_edge("a", "BEARS_ON", "b", {"src_seq": 1})
            return store

        calls = (
            lambda s: s.merge_node("c", "Claim"),
            lambda s: s.merge_edge("a", "BEARS_ON", "b", {"src_seq": 2}),
            lambda s: s.replace_edges("a", "BEARS_ON", []),
            lambda s: s.invalidate("b"),
            lambda s: s.neighbors("a"),
        )
        for call in calls:
            with self.subTest(call=call):
                store = prepared()
                store.fail_after(0)
                with self.assertRaises(graph_store.GraphUnavailable):
                    call(store)

    def test_failed_projection_names_ref_and_next_projection_converges(self):
        clean = graph_store.FakeGraph()
        self.assertTrue(self._project(clean).complete)
        expected = clean.neighbors("atv:a")

        expected_incomplete = {
            0: ("atv:a", "claim:c"),
            1: ("claim:c", "atv:a"),
            2: ("atv:a",),
        }
        for successful_operations, expected_refs in expected_incomplete.items():
            with self.subTest(failure_after=successful_operations):
                store = graph_store.FakeGraph()
                store.fail_after(successful_operations)

                failed = self._project(store)
                recovered = self._project(store)

                self.assertFalse(failed.complete)
                self.assertEqual(failed.incomplete_refs, expected_refs)
                self.assertTrue(recovered.complete)
                self.assertEqual(store.neighbors("atv:a"), expected)


if __name__ == "__main__":
    unittest.main()
