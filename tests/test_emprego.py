"""emprego — porteiro fold: accepted employment digests from sessao.racionalizada."""

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import eventlog  # noqa: E402
import emprego  # noqa: E402


def _rid(ch):
    return ch * 64


def _rationalized(
    sessao_id="s1",
    rid=None,
    activity_relevant=True,
    human_purpose="ship billing recurrence",
    edge_execution="added route and tests",
    shared_outcome="controlled recurrence flow",
    operacoes=None,
    supersedes=None,
    cenas=None,
    enderecos=None,
    presuncoes=None,
    surface="codex",
):
    rid = rid or _rid("b")
    payload = {
        "sessao_id": sessao_id,
        "surface": surface,
        "watermark": 2,
        "operacoes": operacoes or ["edge"],
        "source_hash": _rid("a"),
        "rationalization_id": rid,
        "racionalizador_version": "test-v1",
        "stitch": {
            "goal": human_purpose,
            "acao": shared_outcome,
            "entidades": [],
            "attribution": {
                "human_purpose": human_purpose,
                "human_turn_indexes": [0],
                "edge_execution": edge_execution,
                "shared_outcome": shared_outcome,
                "activity_relevant": activity_relevant,
            },
        },
        "epistemico": {"presuncoes": presuncoes or []},
        "organizacional": {"enderecos": enderecos if enderecos is not None else []},
    }
    if cenas is not None:
        payload["cenas"] = cenas
    if supersedes:
        payload["supersedes"] = supersedes
    return payload


class AcceptedEmploymentFilter(unittest.TestCase):
    def test_activity_relevant_true_only_and_body_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.append(
                "sessao.racionalizada", "sessao:s1",
                _rationalized(sessao_id="s1", rid=_rid("1")), log=log)
            eventlog.append(
                "sessao.racionalizada", "sessao:s2",
                _rationalized(
                    sessao_id="s2", rid=_rid("2"), activity_relevant=False,
                    human_purpose="chatter only"),
                log=log)
            items = emprego.accepted_employment(log=log)
            self.assertEqual(len(items), 1)
            item = items[0]
            self.assertEqual(item["session_id"], "s1")
            self.assertEqual(item["rationalization_id"], _rid("1"))
            self.assertEqual(item["surface"], "codex")
            body = item["body"]
            self.assertIn("FINALIDADE: ship billing recurrence", body)
            self.assertIn("EXECUCAO: added route and tests", body)
            self.assertIn("RESULTADO: controlled recurrence flow", body)
            self.assertIn("OPERACOES: edge", body)
            self.assertNotIn("ATIVIDADES:", body)
            self.assertNotIn("PRESSUPOSTOS:", body)
            self.assertNotIn("CENAS:", body)
            self.assertIsInstance(item["ref_time"], str)
            self.assertTrue(item["ref_time"])


class LatestWinsSupersedes(unittest.TestCase):
    def test_superseded_rid_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            first = _rid("1")
            second = _rid("2")
            eventlog.append(
                "sessao.racionalizada", "sessao:s1",
                _rationalized(
                    sessao_id="s1", rid=first,
                    human_purpose="old purpose"),
                log=log)
            eventlog.append(
                "sessao.racionalizada", "sessao:s1",
                _rationalized(
                    sessao_id="s1", rid=second, supersedes=first,
                    human_purpose="new purpose"),
                log=log)
            items = emprego.accepted_employment(log=log)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["rationalization_id"], second)
            self.assertIn("FINALIDADE: new purpose", items[0]["body"])
            self.assertNotIn("old purpose", items[0]["body"])


class CenasInDigest(unittest.TestCase):
    def test_cenas_section_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.append(
                "sessao.racionalizada", "sessao:s1",
                _rationalized(
                    cenas=[
                        {"summary": "human set recurrence goal",
                         "human_turn_indexes": [0, 2]},
                        {"summary": "edge added tests",
                         "human_turn_indexes": [4]},
                    ]),
                log=log)
            body = emprego.accepted_employment(log=log)[0]["body"]
            self.assertIn("CENAS:", body)
            self.assertIn("- human set recurrence goal", body)
            self.assertIn("- edge added tests", body)

    def test_legacy_without_cenas_omits_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            p = _rationalized()
            # legacy: no cenas key
            assert "cenas" not in p or p.pop("cenas", None) or True
            p.pop("cenas", None)
            eventlog.append("sessao.racionalizada", "sessao:s1", p, log=log)
            body = emprego.accepted_employment(log=log)[0]["body"]
            self.assertNotIn("CENAS:", body)


class AtividadeJoinAndEnderecosExcluded(unittest.TestCase):
    def test_atividades_and_no_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            rid = _rid("e")
            eventlog.append(
                "sessao.racionalizada", "sessao:s1",
                _rationalized(
                    rid=rid,
                    enderecos=[{
                        "path": "/tmp/secret/contrato.pdf",
                        "kind": "file",
                    }],
                ),
                log=log)
            eventlog.append(
                "atividade.opened", "atividade:auto",
                {
                    "ulid": "01ACTIVITYOPEN000000000000",
                    "operacao": "edge",
                    "num": "atv-001",
                    "finalidade": "controlar cobranças",
                    "novo": "placeholder",
                    "tier": "llm_judged",
                    "author": "racionalizador",
                    "origem_sessao": "s1",
                    "rationalization_id": rid,
                    "source_hash": _rid("a"),
                },
                log=log)
            eventlog.append(
                "atividade.touched", "atividade:auto",
                {
                    "ref": "01ACTIVITYOPEN000000000000",
                    "novo": "fluxo idempotente",
                    "origem_sessao": "s1",
                    "rationalization_id": rid,
                    "source_hash": _rid("a"),
                },
                log=log)
            body = emprego.accepted_employment(log=log)[0]["body"]
            self.assertIn("ATIVIDADES:", body)
            self.assertIn("- controlar cobranças — fluxo idempotente", body)
            self.assertNotIn("/tmp/secret", body)
            self.assertNotIn("contrato.pdf", body)

    def test_superseded_atividades_do_not_bleed(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            old_rid, new_rid = _rid("1"), _rid("2")
            eventlog.append(
                "sessao.racionalizada", "sessao:s1",
                _rationalized(rid=old_rid, human_purpose="old"), log=log)
            eventlog.append(
                "atividade.opened", "atividade:auto",
                {
                    "ulid": "01OLD000000000000000000000",
                    "operacao": "edge", "num": "atv-001",
                    "finalidade": "old-only activity",
                    "tier": "llm_judged", "author": "racionalizador",
                    "origem_sessao": "s1", "rationalization_id": old_rid,
                    "source_hash": _rid("a"),
                }, log=log)
            eventlog.append(
                "sessao.racionalizada", "sessao:s1",
                _rationalized(
                    rid=new_rid, supersedes=old_rid,
                    human_purpose="new purpose"),
                log=log)
            items = emprego.accepted_employment(log=log)
            self.assertEqual(len(items), 1)
            self.assertNotIn("old-only activity", items[0]["body"])
            self.assertNotIn("ATIVIDADES:", items[0]["body"])


class ProjectIdempotent(unittest.TestCase):
    def test_adds_once_then_noop_and_dark(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            rid = _rid("p")
            eventlog.append(
                "sessao.racionalizada", "sessao:s1",
                _rationalized(rid=rid), log=log)
            recorded = []

            def add_fn(name, body, ref_time):
                recorded.append((name, body, ref_time))

            first = emprego.project(
                log=log, existing_names=set(), add_fn=add_fn)
            self.assertEqual(first, {"added": 1, "total": 1})
            self.assertEqual(len(recorded), 1)
            name = emprego.episode_name(rid)
            self.assertEqual(recorded[0][0], name)
            self.assertIn("FINALIDADE:", recorded[0][1])

            second = emprego.project(
                log=log, existing_names={name}, add_fn=add_fn)
            self.assertEqual(second, {"added": 0, "total": 1})
            self.assertEqual(len(recorded), 1)

            # force dark without touching live Neo4j (group_fn raises → None)
            def _boom():
                raise RuntimeError("dark-test")
            self.assertIsNone(emprego.project(log=log, group_fn=_boom))

    def test_bypass_query_fn(self):
        self.assertEqual(
            emprego.bypass_episodes(query_fn=lambda g: ["session-abc"]),
            ["session-abc"])
        self.assertEqual(emprego.bypass_episodes(query_fn=lambda g: []), [])


class ImportStaysBare(unittest.TestCase):
    def test_no_neo4j_at_import(self):
        import ast
        src = (REPO / "tools" / "emprego.py").read_text()
        tree = ast.parse(src)
        top_imports = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                top_imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                top_imports.add(node.module.split(".")[0])
        self.assertNotIn("neo4j", top_imports)
        self.assertNotIn("graphiti_core", top_imports)
        self.assertNotIn("communities", top_imports)
        self.assertTrue(callable(emprego.accepted_employment))


if __name__ == "__main__":
    unittest.main()
