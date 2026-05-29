#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== core identity injection Test ==="
echo ""

echo "--- Test 1: render_core_identity assembles the three domains, in order, under the IDENTITY CORE header ---"
if python3 - <<'PY' "$EDGE_DIR"
import sys, tempfile
from pathlib import Path
edge_dir = Path(sys.argv[1]); sys.path.insert(0, str(edge_dir / "tools" / "_shared"))
from core_identity import render_core_identity

d = Path(tempfile.mkdtemp())
(d / "personality.md").write_text("PERSONALITY_BODY")
(d / "method.md").write_text("METHOD_BODY")
(d / "rules-core.md").write_text("RULES_BODY")
core = render_core_identity(d)
assert "IDENTITY CORE" in core, "header missing"
assert all(x in core for x in ("PERSONALITY_BODY", "METHOD_BODY", "RULES_BODY")), "domain content missing"
assert core.index("PERSONALITY_BODY") < core.index("METHOD_BODY") < core.index("RULES_BODY"), "domains out of order"
PY
then pass "render_core_identity assembles 3 domains in order with header"; else fail "render_core_identity assembles 3 domains in order with header"; fi

echo "--- Test 2: render_core_identity skips missing files and returns empty when none exist ---"
if python3 - <<'PY' "$EDGE_DIR"
import sys, tempfile
from pathlib import Path
edge_dir = Path(sys.argv[1]); sys.path.insert(0, str(edge_dir / "tools" / "_shared"))
from core_identity import render_core_identity

# personality missing (e.g. not rendered yet): still works, includes the rest
partial_dir = Path(tempfile.mkdtemp())
(partial_dir / "method.md").write_text("METHOD_BODY")
(partial_dir / "rules-core.md").write_text("RULES_BODY")
partial = render_core_identity(partial_dir)
assert "METHOD_BODY" in partial and "RULES_BODY" in partial, "should include present files"
assert "PERSONALITY_BODY" not in partial, "should not invent missing file"

# none present: empty string, no crash
empty = render_core_identity(Path(tempfile.mkdtemp()))
assert empty == "", "empty memory dir should yield empty core"
PY
then pass "render_core_identity degrades gracefully (skip missing, empty when none)"; else fail "render_core_identity degrades gracefully (skip missing, empty when none)"; fi

echo "--- Test 3: inject_after_frontmatter preserves YAML frontmatter and inserts core after it (top if none) ---"
if python3 - <<'PY' "$EDGE_DIR"
import sys
from pathlib import Path
edge_dir = Path(sys.argv[1]); sys.path.insert(0, str(edge_dir / "tools" / "_shared"))
from core_identity import inject_after_frontmatter

skill = "---\nname: ed-loader\ndescription: x\n---\n\n# Loader\nbody"
out = inject_after_frontmatter(skill, "CORE_BLOCK")
assert out.startswith("---\nname: ed-loader\ndescription: x\n---"), "frontmatter not preserved at top"
fm, _, rest = out.partition("---\n\n") if False else (None, None, None)
# core must land after the closing --- and before the body heading
assert out.index("CORE_BLOCK") > out.index("name: ed-loader"), "core inserted inside/above frontmatter"
assert out.index("CORE_BLOCK") < out.index("# Loader"), "core not before skill body"

# no frontmatter: core goes to the very top
plain = "# Just a body\ntext"
out2 = inject_after_frontmatter(plain, "CORE_BLOCK")
assert out2.startswith("CORE_BLOCK"), "core should lead when there is no frontmatter"

# empty core: content untouched
assert inject_after_frontmatter(skill, "") == skill, "empty core must not alter content"
PY
then pass "inject_after_frontmatter keeps frontmatter intact, inserts core after it"; else fail "inject_after_frontmatter keeps frontmatter intact, inserts core after it"; fi

echo "--- Test 4: render_skill_runtime_prompt leads with the identity core, for substantive skills and heartbeat ---"
if python3 - <<'PY' "$EDGE_DIR"
import sys, tempfile
from pathlib import Path
edge_dir = Path(sys.argv[1]); sys.path.insert(0, str(edge_dir / "tools"))
import _shared.dispatch_runtime as dr

mem = Path(tempfile.mkdtemp()) / "memory"; mem.mkdir()
(mem / "personality.md").write_text("PERSONALITY_BODY")
dr.EDGE_REPO_DIR = mem.parent  # render_core_identity reads EDGE_REPO_DIR / "memory"

research = dr.render_skill_runtime_prompt("research", {"request": {"skill": "research"}})
assert research.startswith("=== IDENTITY CORE"), "substantive skill prompt must lead with identity core"
assert "PERSONALITY_BODY" in research, "core content missing from prompt"

heartbeat = dr.render_skill_runtime_prompt("heartbeat", {"request": {"heartbeat_routing": {}, "async_inbox": {}}})
assert heartbeat.startswith("=== IDENTITY CORE"), "heartbeat prompt must lead with identity core too"
PY
then pass "render_skill_runtime_prompt leads with the identity core (substantive + heartbeat)"; else fail "render_skill_runtime_prompt leads with the identity core (substantive + heartbeat)"; fi

echo ""
echo "Passed: $PASS"
echo "Failed: $FAIL"
[ "$FAIL" -eq 0 ]
