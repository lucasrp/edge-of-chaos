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
FORBIDDEN = ["edge-next", "lucasrp/edge-of-chaos", "~/edge-next/", "edgepassword123"]


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
