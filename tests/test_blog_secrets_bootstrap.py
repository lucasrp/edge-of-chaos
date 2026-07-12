"""Blog process loads install secrets without a hand-exported env.

Regression: cortex went dark on fleet members when blog/server.py started without
EDGE_NEO4J_PASSWORD in the unit environment, even though secrets/neo4j.env existed.
Bootstrap must source secrets from the install (agent.yaml edge_home or <repo>/secrets)
via the genotype _secrets loader — never a host-hardcoded path.
"""
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent


def _load_server(env=None):
    saved = {}
    env = env or {}
    keys = set(env) | {
        "EDGE_NEO4J_PASSWORD", "EDGE_GROUP", "EDGE_REPO", "EDGE_CORTEX_FIXTURE",
        "EDGE_NEO4J_URI", "EDGE_NEO4J_USER",
    }
    for k in keys:
        saved[k] = os.environ.pop(k, None)
    for k, v in env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    # fresh import
    for mod in list(sys.modules):
        if mod in ("blogserver",) or mod.endswith("server") and "blog" in mod:
            sys.modules.pop(mod, None)
    tools = str(REPO / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    blog = str(REPO / "blog")
    if blog not in sys.path:
        sys.path.insert(0, blog)
    spec = importlib.util.spec_from_file_location(
        "blogserver_secrets_test", REPO / "blog" / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, saved


def _restore(saved):
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


class BlogSecretsBootstrap(unittest.TestCase):
    def test_bootstrap_loads_password_from_repo_secrets_dir(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            secrets = d / "secrets"
            secrets.mkdir()
            (secrets / "neo4j.env").write_text("EDGE_NEO4J_PASSWORD=from-disk-secret\n")
            (d / "agent.yaml").write_text(
                "name: test\ngraph_group: test-group\nedge_home: \"%s\"\n" % d.as_posix()
            )
            # Point identity at this fake install via EDGE_REPO if supported; else patch BASE.
            mod, saved = _load_server({
                "EDGE_NEO4J_PASSWORD": None,  # force disk load
                "EDGE_GROUP": None,
            })
            try:
                # Redirect bootstrap to the temp install tree
                real_base = mod.BASE
                mod.BASE = d / "blog"
                (d / "blog").mkdir(exist_ok=True)
                # tools must still resolve for _secrets — keep real tools via sys.path
                os.environ.pop("EDGE_NEO4J_PASSWORD", None)
                # agent.yaml for identity: write next to fake tools? _identity.AGENT_YAML is
                # tools/../agent.yaml of the REAL tools package. Patch _env_dir instead.
                import _identity
                import _secrets
                with mock.patch.object(_identity, "_env_dir", return_value=secrets):
                    with mock.patch.object(_identity, "AGENT_YAML", d / "agent.yaml"):
                        mod._bootstrap_install_env()
                        pw = mod._neo4j_password()
                self.assertEqual(pw, "from-disk-secret")
                self.assertEqual(os.environ.get("EDGE_NEO4J_PASSWORD"), "from-disk-secret")
            finally:
                _restore(saved)

    def test_bootstrap_function_exists_and_is_called_on_import_path(self):
        src = (REPO / "blog" / "server.py").read_text()
        self.assertIn("def _bootstrap_install_env", src)
        self.assertIn("_bootstrap_install_env()", src)
        self.assertIn("_secrets.load_env", src)


class DistillCatalogHelpers(unittest.TestCase):
    def test_helpers_exist_in_publisher(self):
        sys.path.insert(0, str(REPO / "tools"))
        import publisher
        self.assertTrue(callable(publisher._distill_catalog))
        self.assertTrue(callable(publisher._link_distill))
        src = Path(publisher.__file__).read_text()
        self.assertIn("Community", src)
        self.assertIn("pending_distills", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
