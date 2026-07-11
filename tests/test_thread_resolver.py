"""A34 — production label resolver at the Graphiti seam."""

import inspect
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import thread_resolver  # noqa: E402


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def data(self):
        return [dict(row) for row in self._rows]


class _Session:
    def __init__(self, driver):
        self.driver = driver

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def run(self, query, **params):
        self.driver.calls.append((query, params))
        group = params["group_id"]
        if "label" in params:
            label = params["label"]
            matches = [node for node in self.driver.nodes
                       if node["group_id"] == group
                       and label in (node.get("name"), node.get("curated_name"))]
        else:
            target = params["target"]
            matches = [node for node in self.driver.nodes
                       if node["group_id"] == group
                       and target in (node.get("ref"), node.get("uuid"),
                                      node.get("name"), node.get("curated_name"))]
        return _Rows(matches)


class _Driver:
    def __init__(self, nodes):
        self.nodes = nodes
        self.calls = []
        self.closed = False

    def session(self):
        return _Session(self)

    def close(self):
        self.closed = True


class ThreadResolverContract(unittest.TestCase):
    def test_install_helper_uses_identity_group_and_closes_driver_on_success(self):
        driver = _Driver([
            {"group_id": "edge", "uuid": "thread-uuid", "name": "V10",
             "curated_name": "V10 canônica", "merged_into": None, "archived": False},
        ])
        factory_calls = []
        identity_calls = []

        def driver_factory(uri, *, auth):
            factory_calls.append((uri, auth))
            return driver

        class Identity:
            @staticmethod
            def neo4j_conn():
                identity_calls.append("conn")
                return "bolt://graph", "neo", "secret"

            @staticmethod
            def require_group():
                identity_calls.append("group")
                return "edge"

        resolved = thread_resolver.resolve_for_install(
            "V10", driver_factory=driver_factory, identity=Identity,
        )

        self.assertEqual(
            resolved, [{"uuid": "thread-uuid", "display": "V10 canônica"}],
        )
        self.assertEqual(identity_calls, ["group", "conn"])
        self.assertEqual(factory_calls, [("bolt://graph", ("neo", "secret"))])
        self.assertTrue(driver.closed)

    def test_install_helper_closes_driver_when_resolution_refuses(self):
        driver = _Driver([])

        class Identity:
            neo4j_conn = staticmethod(lambda: ("bolt://graph", "neo", "secret"))
            require_group = staticmethod(lambda: "edge")

        with self.assertRaisesRegex(ValueError, "not found"):
            thread_resolver.resolve_for_install(
                "missing",
                driver_factory=lambda _uri, *, auth: driver,
                identity=Identity,
            )

        self.assertTrue(driver.closed)

    def test_group_scoped_label_follows_name_merges_to_one_live_terminal(self):
        driver = _Driver([
            {"group_id": "edge", "ref": "old-ref", "uuid": "old-uuid",
             "name": "V10", "curated_name": None, "merged_into": "Middle", "archived": False},
            {"group_id": "edge", "ref": "middle-ref", "uuid": "middle-uuid",
             "name": "Middle", "curated_name": None,
             "merged_into": "canonical-uuid", "archived": False},
            {"group_id": "edge", "ref": "canonical-ref", "uuid": "canonical-uuid",
             "name": "Canonical", "curated_name": "Nome canônico",
             "merged_into": None, "archived": False},
            {"group_id": "foreign", "ref": "foreign-ref", "uuid": "foreign-uuid",
             "name": "V10", "curated_name": None, "merged_into": None, "archived": False},
        ])
        resolve = thread_resolver.ThreadResolver(driver, group_id="edge")

        self.assertEqual(
            resolve("V10"),
            [{"uuid": "canonical-uuid", "display": "Nome canônico"}],
        )
        self.assertTrue(all(params["group_id"] == "edge" for _query, params in driver.calls))
        self.assertTrue(all("Entity" in query for query, _params in driver.calls))

    def test_ambiguity_archived_dangling_and_cycle_refuse_loud(self):
        cases = {
            "ambiguous": [
                {"group_id": "edge", "uuid": "a", "name": "X", "archived": False},
                {"group_id": "edge", "uuid": "b", "name": "X", "archived": False},
            ],
            "archived": [
                {"group_id": "edge", "uuid": "a", "name": "X", "archived": True},
            ],
            "dangling": [
                {"group_id": "edge", "uuid": "a", "name": "X",
                 "merged_into": "missing", "archived": False},
            ],
            "cycle": [
                {"group_id": "edge", "uuid": "a", "name": "X",
                 "merged_into": "B", "archived": False},
                {"group_id": "edge", "uuid": "b", "name": "B",
                 "merged_into": "a", "archived": False},
            ],
        }
        for case, nodes in cases.items():
            with self.subTest(case=case), self.assertRaisesRegex(ValueError, case):
                thread_resolver.ThreadResolver(_Driver(nodes), group_id="edge")("X")

    def test_adapter_is_strictly_synchronous(self):
        class AsyncDriver:
            async def session(self):
                return None

        self.assertFalse(inspect.iscoroutinefunction(thread_resolver.ThreadResolver.__call__))
        with self.assertRaisesRegex(TypeError, "sync"):
            thread_resolver.ThreadResolver(AsyncDriver(), group_id="edge")("X")


if __name__ == "__main__":
    unittest.main()
