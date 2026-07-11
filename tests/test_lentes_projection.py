"""S9 — projeção determinística das lentes do eventlog no GraphStore."""

import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import eventlog  # noqa: E402
import graph_store  # noqa: E402
import publisher  # noqa: E402


class _RecordingFakeGraph(graph_store.FakeGraph):
    def __init__(self):
        super().__init__()
        self.merged_labels = {}
        self.merged_props = {}

    def merge_node(self, ref, label, props=None):
        self.merged_labels[ref] = label
        self.merged_props.setdefault(ref, {}).update(dict(props or {}))
        return super().merge_node(ref, label, props)


class _CallRecordingFakeGraph(graph_store.FakeGraph):
    """Expose the port-call order without peeking into FakeGraph's topology state."""

    def __init__(self):
        super().__init__()
        self.call_refs = []

    def merge_node(self, ref, label, props=None):
        self.call_refs.append(ref)
        return super().merge_node(ref, label, props)

    def replace_edges(self, owner_ref, edge_kind, desired, as_of=None):
        self.call_refs.append(owner_ref)
        return super().replace_edges(owner_ref, edge_kind, desired, as_of=as_of)

    def merge_edge(self, src_ref, edge_kind, dst_ref, props=None):
        self.call_refs.append(src_ref)
        return super().merge_edge(src_ref, edge_kind, dst_ref, props)

    def invalidate(self, ref, as_of=None):
        self.call_refs.append(ref)
        return super().invalidate(ref, as_of=as_of)

    def neighbors(self, ref, edge_kind=None, direction="both"):
        self.call_refs.append(ref)
        return super().neighbors(ref, edge_kind=edge_kind, direction=direction)


def _unique(values):
    return tuple(dict.fromkeys(values))


class ProjectionTopologyA22(unittest.TestCase):
    def test_projection_path_imports_no_model_or_graphiti_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.open_atividade(
                operacao="edge", finalidade="projeção mecânica", tier="asserted",
                author="operador", log=log,
            )
            imported_roots = []
            original_import = __import__

            def recording_import(name, *args, **kwargs):
                imported_roots.append(name.split(".", 1)[0])
                return original_import(name, *args, **kwargs)

            with mock.patch("builtins.__import__", side_effect=recording_import):
                result = publisher.project_lentes(log, graph_store.FakeGraph())

            self.assertTrue(result.complete)
            self.assertTrue(
                {"openai", "graphiti_core", "neo4j"}.isdisjoint(imported_roots)
            )

    def test_bears_on_is_idempotent_by_topology_and_amendment_replaces_old_seq(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened = eventlog.open_atividade(
                operacao="edge",
                finalidade="provar a projeção",
                tier="asserted",
                author="operador",
                log=log,
            )
            activity_ref = f"edge/{opened['payload']['num']}"
            activity_graph_ref = f"atividade:{opened['payload']['ulid']}"
            declared = eventlog.declare_hypothesis(
                "A projeção converge",
                {"metric": "same_topology", "threshold": 1, "direction": "maior"},
                author="operador",
                log=log,
            )
            claim_ref = f"claim:{declared['payload']['ulid']}"
            first_bearing = eventlog.bears_on(
                ref=activity_ref,
                alvo=declared["payload"]["ulid"],
                valencia="supports",
                tier="asserted",
                log=log,
            )
            store = graph_store.FakeGraph()

            first = publisher.project_lentes(log, store)
            topology_once = store.neighbors(activity_graph_ref, "BEARS_ON", direction="out")
            second = publisher.project_lentes(log, store)
            topology_twice = store.neighbors(activity_graph_ref, "BEARS_ON", direction="out")

            self.assertTrue(first.complete)
            self.assertTrue(second.complete)
            self.assertEqual(topology_once, topology_twice)
            self.assertEqual(len(topology_twice), 1)
            self.assertEqual(topology_twice[0].ref, claim_ref)
            self.assertEqual(topology_twice[0].edge_props["src_seq"], first_bearing["seq"])
            self.assertEqual(topology_twice[0].edge_props["valencia"], "supports")
            self.assertEqual(topology_twice[0].edge_props["provenance_class"], "asserted")

            amended = eventlog.bears_on(
                ref=activity_ref,
                alvo=declared["payload"]["ulid"],
                valencia="refutes",
                tier="llm_judged",
                log=log,
            )
            projected = publisher.project_lentes(log, store)
            topology_amended = store.neighbors(activity_graph_ref, "BEARS_ON", direction="out")

            self.assertTrue(projected.complete)
            self.assertEqual(len(topology_amended), 1)
            self.assertEqual(topology_amended[0].edge_props["src_seq"], amended["seq"])
            self.assertEqual(topology_amended[0].edge_props["valencia"], "refutes")
            self.assertEqual(
                topology_amended[0].edge_props["provenance_class"], "llm_judged"
            )

    def test_projects_all_structured_labels_and_relationships_as_navigable_topology(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            dispatch = eventlog.test_dispatch_id()
            arc = eventlog.open_arco(
                operacao="edge", nome="S9", tier="asserted", author="operador", log=log
            )
            arc_ref = f"edge/{arc['payload']['num']}"
            activity = eventlog.open_atividade(
                operacao="edge", finalidade="projetar tudo", arco=arc_ref,
                tier="asserted", author="operador", log=log,
            )
            activity_ref = f"edge/{activity['payload']['num']}"
            eventlog.touch_atividade(
                ref=activity_ref, sessao="session-s9", novo="topologia",
                tier="llm_judged", log=log,
            )
            run = eventlog.open_run(
                atividades=[activity_ref], config={"corpus": "fixture"},
                eval={"metric": "accuracy", "predicao": "sobe"},
                tier="asserted", log=log,
            )
            fact = eventlog.observe_fato(
                atividade=activity_ref, run=f"edge/{run['payload']['num']}",
                body="accuracy=1", medida={"valor": 1, "como": "fixture"},
                tier="asserted", log=log,
            )
            old_claim = eventlog.declare_hypothesis(
                "versão antiga", {"metric": "m", "threshold": 1, "direction": "maior"},
                author="operador", log=log,
            )
            new_claim = eventlog.declare_hypothesis(
                "versão nova", {"metric": "m", "threshold": 2, "direction": "maior"},
                author="operador", log=log,
            )
            eventlog.supersede_hypothesis(
                old_claim["payload"]["ulid"], new_claim["payload"]["ulid"], log=log
            )
            eventlog.bears_on(
                ref=activity_ref, alvo=new_claim["payload"]["ulid"],
                valencia="supports", tier="asserted", log=log,
            )
            way_map = eventlog.open_map(
                operacao="edge", titulo="Mapa S9", rationale="provar",
                dispatch_id=dispatch, author="operador", log=log,
            )
            map_ref = f"edge/{way_map['payload']['num']}"
            ticket_one = eventlog.open_ticket(
                map=map_ref, titulo="Primeiro", question="Q1?", rationale="r1",
                dispatch_id=dispatch, author="operador",
                inscricao=old_claim["payload"]["ulid"], log=log,
            )
            ticket_one_ref = f"edge/{ticket_one['payload']['num']}"
            ticket_two = eventlog.open_ticket(
                map=map_ref, titulo="Segundo", question="Q2?", rationale="r2",
                dispatch_id=dispatch, author="operador", blocked_by=[ticket_one_ref], log=log,
            )
            eventlog.close_ticket(
                ref=ticket_one_ref, resolucao="feito", valencia="supports",
                bears_on=[{"alvo": activity_ref, "valencia": "supports"}],
                rationale="resolvido", dispatch_id=dispatch, author="operador", log=log,
            )
            move_ulid = "01ARZ3NDEKTSV4RRFFQ69G5FMV"
            eventlog.append(
                "move.proposed", f"move:{move_ulid}",
                {"ulid": move_ulid, "kind": "ticket.close", "move_key": "mk",
                 "author": "edge"}, log=log,
            )
            eventlog.set_marco(
                operacao="edge", ref=activity_ref, rationale="estável",
                dispatch_id=dispatch, author="operador", log=log,
            )
            store = _RecordingFakeGraph()

            result = publisher.project_lentes(log, store)

            self.assertTrue(result.complete)
            expected_labels = {
                f"atividade:{activity['payload']['ulid']}": "Atividade",
                f"run:{run['payload']['ulid']}": "Run",
                f"fato:{fact['payload']['ulid']}": "Fato",
                f"arco:{arc['payload']['ulid']}": "Arco",
                f"map:{way_map['payload']['ulid']}": "Map",
                f"ticket:{ticket_one['payload']['ulid']}": "Ticket",
                f"ticket:{ticket_two['payload']['ulid']}": "Ticket",
                f"move:{move_ulid}": "Move",
                f"claim:{old_claim['payload']['ulid']}": "Claim",
                f"claim:{new_claim['payload']['ulid']}": "Claim",
            }
            for ref, label in expected_labels.items():
                self.assertEqual(store.merged_labels.get(ref), label, ref)

            activity_graph_ref = f"atividade:{activity['payload']['ulid']}"
            arc_graph_ref = f"arco:{arc['payload']['ulid']}"
            map_graph_ref = f"map:{way_map['payload']['ulid']}"
            ticket_one_graph_ref = f"ticket:{ticket_one['payload']['ulid']}"
            ticket_two_graph_ref = f"ticket:{ticket_two['payload']['ulid']}"
            old_claim_graph_ref = f"claim:{old_claim['payload']['ulid']}"
            new_claim_graph_ref = f"claim:{new_claim['payload']['ulid']}"
            self.assertEqual(store.neighbors(activity_graph_ref, "PART_OF")[0].ref, arc_graph_ref)
            self.assertEqual(store.neighbors("sessao:session-s9", "TOUCHES")[0].ref,
                             activity_graph_ref)
            self.assertEqual(store.neighbors(ticket_one_graph_ref, "PART_OF")[0].ref,
                             map_graph_ref)
            self.assertEqual(store.neighbors(ticket_two_graph_ref, "BLOCKED_BY")[0].ref,
                             ticket_one_graph_ref)
            self.assertEqual(store.neighbors(ticket_one_graph_ref, "INSCRIBES")[0].ref,
                             old_claim_graph_ref)
            self.assertEqual(store.neighbors(ticket_one_graph_ref, "BEARS_ON")[0].ref,
                             activity_graph_ref)
            self.assertEqual(store.neighbors(new_claim_graph_ref, "SUPERSEDES")[0].ref,
                             old_claim_graph_ref)
            self.assertEqual(store.neighbors(activity_graph_ref, "MARCO_OF")[0].ref,
                             "operacao:edge")

            eventlog.change_ticket_deps(
                ref=f"edge/{ticket_two['payload']['num']}", blocked_by=[],
                rationale="dependência removida", dispatch_id=dispatch,
                author="operador", log=log,
            )
            eventlog.set_marco(
                operacao="edge", ref=f"edge/{run['payload']['num']}",
                rationale="o run agora é o marco", dispatch_id=dispatch,
                author="operador", log=log,
            )

            amended = publisher.project_lentes(log, store)

            self.assertTrue(amended.complete)
            self.assertEqual(store.neighbors(ticket_two_graph_ref, "BLOCKED_BY"), [])
            self.assertEqual(store.neighbors(activity_graph_ref, "MARCO_OF"), [])
            self.assertEqual(
                store.neighbors(f"run:{run['payload']['ulid']}", "MARCO_OF")[0].ref,
                "operacao:edge",
            )

    def test_each_programmed_outage_names_the_exact_unprojected_suffix_then_converges(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            dispatch = eventlog.test_dispatch_id()
            arc = eventlog.open_arco(
                operacao="edge", nome="A33", tier="asserted", author="operador", log=log
            )
            activity = eventlog.open_atividade(
                operacao="edge", finalidade="retomar projeção",
                arco=f"edge/{arc['payload']['num']}", tier="asserted",
                author="operador", log=log,
            )
            eventlog.set_marco(
                operacao="edge", ref=f"edge/{activity['payload']['num']}",
                rationale="fixture navegável", dispatch_id=dispatch,
                author="operador", log=log,
            )
            activity_ref = f"atividade:{activity['payload']['ulid']}"
            arc_ref = f"arco:{arc['payload']['ulid']}"

            clean = _CallRecordingFakeGraph()
            self.assertTrue(publisher.project_lentes(log, clean).complete)
            clean_calls = tuple(clean.call_refs)
            clean_activity_topology = clean.neighbors(activity_ref)
            clean_arc_topology = clean.neighbors(arc_ref)

            for failure_after in range(len(clean_calls)):
                with self.subTest(failure_after=failure_after):
                    interrupted = _CallRecordingFakeGraph()
                    interrupted.fail_after(failure_after)

                    result = publisher.project_lentes(log, interrupted)

                    self.assertFalse(result.complete)
                    self.assertEqual(
                        result.incomplete_refs,
                        _unique(clean_calls[failure_after:]),
                    )
                    self.assertTrue(publisher.project_lentes(log, interrupted).complete)
                    self.assertEqual(
                        interrupted.neighbors(activity_ref), clean_activity_topology
                    )
                    self.assertEqual(interrupted.neighbors(arc_ref), clean_arc_topology)

    def test_graphiti_thread_snapshot_retargets_without_invalidating_graphiti_entity(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            dispatch = eventlog.test_dispatch_id()
            way_map = eventlog.open_map(
                operacao="edge", titulo="A34", rationale="thread estável",
                dispatch_id=dispatch, author="operador",
                thread="Nome no momento da caneta",
                resolve_thread_fn=lambda _label: [{
                    "uuid": "thread-old", "display": "Nome no momento da caneta",
                }],
                log=log,
            )
            map_ref = f"map:{way_map['payload']['ulid']}"
            store = _RecordingFakeGraph()
            store.merge_node("thread-old", "Entity", {
                "uuid": "thread-old", "name": "Nome antigo",
            })
            store.merge_node(
                "thread-canonical", "Entity", {
                    "uuid": "thread-canonical", "name": "Nome canônico",
                    "curated_name": "Nome canônico inicial",
                }
            )
            store.merge_node("semantic-peer", "Entity", {"name": "Peer"})
            store.merge_edge(
                "thread-old", "RELATES_TO", "semantic-peer", {"src_seq": 91},
            )

            first = publisher.project_lentes(log, store)

            self.assertTrue(first.complete)
            self.assertEqual(store.neighbors(map_ref, "PART_OF")[0].ref, "thread-old")
            self.assertEqual(store.merged_props[map_ref]["thread_uuid"], "thread-old")
            self.assertEqual(
                store.merged_props[map_ref]["thread_display"],
                "Nome no momento da caneta",
            )

            store.merge_node(
                "thread-old", "Entity", {"merged_into": "Nome canônico"}
            )
            store.merge_node(
                "thread-canonical", "Entity", {"curated_name": "Nome canônico renomeado"}
            )
            reprojection = publisher.project_lentes(log, store)
            canonical = store.neighbors(map_ref, "PART_OF")

            self.assertTrue(reprojection.complete)
            self.assertEqual(len(canonical), 1)
            self.assertEqual(canonical[0].ref, "thread-canonical")
            self.assertEqual(
                canonical[0].node_props["curated_name"], "Nome canônico renomeado"
            )
            preserved_semantic_edge = store.neighbors(
                "semantic-peer", "RELATES_TO", direction="in",
            )
            self.assertEqual(len(preserved_semantic_edge), 1)
            self.assertEqual(preserved_semantic_edge[0].ref, "thread-canonical")
            self.assertEqual(
                store.merged_props[map_ref]["thread_display"],
                "Nome no momento da caneta",
            )

            self.assertTrue(publisher.project_lentes(log, store).complete)
            self.assertEqual(
                store.neighbors(map_ref, "PART_OF")[0].ref, "thread-canonical"
            )


if __name__ == "__main__":
    unittest.main()
