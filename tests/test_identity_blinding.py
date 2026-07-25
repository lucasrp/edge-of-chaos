"""Identity-blinding gate (#21) — agent.yaml is the SOLE identity source.

Install literals must NEVER be baked into the genotype: a fleet host with its own
agent.yaml must write its Cortex into ITS OWN graph group and render ITS OWN wiki —
never edge-next's. The dangerous one is the cross-tenant `EDGE_GROUP` default of
"edge-next" (sweep/grill_lint/wiki_render): with EDGE_GROUP unset a host would mix
tenants. This gate scans tools/ + skills/ and FAILS if any of these literals appear:

    edge-next            (group/wiki identity leak — cross-tenant bug)
    lucasrp/edge-of-chaos (the domain repo hardcoded)
    ~/edge-next/         (path default leak)
    edgepassword123      (the hardcoded Neo4j password — CONTRACT C4)

Identity is derived from agent.yaml: name/codename → group, edge_home → paths,
a generated per-host password → Neo4j (no literal default; missing → degrade at
runtime like briefing.py, fail-loud at install).
"""
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCAN_DIRS = [REPO / "tools", REPO / "skills"]

# The install literals that must never appear in the genotype's code.
# "vboxuser" (ADR-0015): the dev host's store path baked into sweep's default sent roberto
# scanning a nonexistent dir — "nothing new" over a 294-session backlog, silently.
FORBIDDEN = ["edge-next", "lucasrp/edge-of-chaos", "~/edge-next/", "edgepassword123",
             "vboxuser"]


def _scan_files():
    """Every readable text file under tools/ and skills/ (skip caches/binaries)."""
    files = []
    for d in SCAN_DIRS:
        if not d.exists():
            continue
        for p in sorted(d.rglob("*")):
            if not p.is_file() or "__pycache__" in p.parts:
                continue
            try:
                yield p, p.read_text()
            except (UnicodeDecodeError, OSError):
                continue
    return files


class IdentityBlindingGate(unittest.TestCase):
    def test_no_install_literals_in_genotype(self):
        hits = []
        for path, text in _scan_files():
            for lineno, line in enumerate(text.splitlines(), 1):
                for lit in FORBIDDEN:
                    if lit in line:
                        rel = path.relative_to(REPO)
                        hits.append(f"{rel}:{lineno}: {lit!r} → {line.strip()}")
        self.assertEqual(
            hits, [],
            "install literals leaked into the genotype (agent.yaml is the sole "
            "identity source):\n" + "\n".join(hits),
        )


class _env:
    """Set env vars for the block (None = unset), restore after."""

    def __init__(self, **kv):
        self.kv, self.saved = kv, {}

    def __enter__(self):
        import os
        for k, v in self.kv.items():
            self.saved[k] = os.environ.get(k)
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)

    def __exit__(self, *a):
        import os
        for k, v in self.saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


class IdentityResolvesAtOneSeam(unittest.TestCase):
    """ADR-0015 — identity (who am I AND where I read) resolves through _identity ALONE:
    callers make one call; none re-implements the env precedence or caches it at import time."""

    def test_no_edge_group_env_read_outside_identity(self):
        # the EDGE_GROUP precedence lives in _identity.group(); an inline
        # `os.environ.get("EDGE_GROUP")` elsewhere is a re-implementation of the seam
        hits = []
        for p in sorted((REPO / "tools").glob("*.py")):
            if p.name == "_identity.py":
                continue
            for lineno, line in enumerate(p.read_text().splitlines(), 1):
                if 'environ.get("EDGE_GROUP"' in line:
                    hits.append(f"{p.name}:{lineno}: {line.strip()}")
        self.assertEqual(hits, [], "EDGE_GROUP resolved outside _identity (ADR-0015):\n"
                         + "\n".join(hits))

    def test_sweep_has_no_import_time_identity_cache(self):
        import sys
        sys.path.insert(0, str(REPO / "tools"))
        import sweep
        self.assertIsNone(getattr(sweep, "GROUP", None),
                          "sweep caches the group at import time (stale-copy risk, ADR-0015)")
        self.assertIsNone(getattr(sweep, "PROJECT_DIR", None),
                          "sweep caches the store path at import time (ADR-0015)")

    def test_wiki_identity_fails_loud_never_defaults(self):
        # a wiki rendered under a fallback name is a silent wrong-author render (ADR-0015)
        import sys
        from unittest import mock
        sys.path.insert(0, str(REPO / "tools"))
        import wiki_render
        import _identity
        with mock.patch.object(_identity, "group", return_value=None):
            with self.assertRaises(RuntimeError):
                wiki_render.identity_name()


class ProjectDirIsFailLoud(unittest.TestCase):
    """ADR-0015 — the transcript store joins the identity seam: EDGE_PROJECT_DIR env → derived
    from the running $HOME per the Claude convention (/home/x → ~/.claude/projects/-home-x).
    A store directory that does not exist RAISES — 'nothing new' is reserved for a real store."""

    def setUp(self):
        import sys
        sys.path.insert(0, str(REPO / "tools"))

    def test_env_override_wins_when_dir_exists(self):
        import tempfile
        import _identity
        with tempfile.TemporaryDirectory() as tmp:
            with _env(EDGE_PROJECT_DIR=tmp):
                self.assertEqual(_identity.project_dir(), Path(tmp))

    def test_derives_from_home_per_claude_convention(self):
        import tempfile
        import _identity
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home" / "roberto"
            store = home / ".claude" / "projects" / str(home).replace("/", "-")
            store.mkdir(parents=True)
            with _env(EDGE_PROJECT_DIR=None, HOME=str(home)):
                self.assertEqual(_identity.project_dir(), store)

    def test_home_with_trailing_slash_resolves_the_same_store(self):
        # a derivation that read $HOME raw would double-dash the slug and silently scan a
        # nonexistent store — the roberto-amnesia class this seam exists to kill
        import tempfile
        import _identity
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home" / "roberto"
            store = home / ".claude" / "projects" / str(home).replace("/", "-")
            store.mkdir(parents=True)
            with _env(EDGE_PROJECT_DIR=None, HOME=str(home) + "/"):
                self.assertEqual(_identity.project_dir(), store)

    def test_missing_store_raises_never_nothing_new(self):
        import tempfile
        import _identity
        with tempfile.TemporaryDirectory() as tmp:
            with _env(EDGE_PROJECT_DIR=str(Path(tmp) / "absent")):
                with self.assertRaises(RuntimeError) as ctx:
                    _identity.project_dir()
        self.assertIn("EDGE_PROJECT_DIR", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
