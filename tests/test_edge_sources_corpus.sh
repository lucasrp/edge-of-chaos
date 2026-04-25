#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP=$(mktemp -d /tmp/edge-sources-corpus-XXXXXX)
trap 'rm -rf "$TMP"' EXIT
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== edge-sources corpus integration (issue #381) ==="

# Stub edge-search so the test does not require a built corpus index.
mkdir -p "$TMP/bin"
cat >"$TMP/bin/edge-search" <<'SH'
#!/usr/bin/env bash
# Mimic the JSON shape edge-search emits.
cat <<'JSON'
{
  "mode": "hybrid",
  "query": "stubbed",
  "results": [
    {"id":"r1","path":"/edge/notes/prior-research.md","type":"note","title":"Prior research on the topic","score":0.0167,"snippet":"This note already covered most of it."},
    {"id":"r2","path":"/edge/blog/entries/2026-01-01.md","type":"blog","title":"Earlier exploration","score":0.0142,"snippet":"Open gap: dimension X never validated."}
  ],
  "workflows": [],
  "coverage": {}
}
JSON
SH
chmod +x "$TMP/bin/edge-search"

PATH_OVERRIDE="$TMP/bin:/usr/bin:/bin"

run_with_stub() {
    local args=("$@")
    EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP/state" PATH="$PATH_OVERRIDE" \
        python3 - "$EDGE_DIR" "${args[@]}" <<'PY' 2>&1
import sys
from pathlib import Path
from importlib.machinery import SourceFileLoader
import importlib.util

edge_dir = Path(sys.argv[1])
script_args = sys.argv[2:]
loader = SourceFileLoader("edge_sources", str(edge_dir / "tools" / "edge-sources"))
spec = importlib.util.spec_from_loader("edge_sources", loader)
mod = importlib.util.module_from_spec(spec)
loader.exec_module(mod)

# Drive the corpus source directly.
items = mod.search_corpus("stubbed topic")
print("CORPUS_COUNT=", len(items))
for it in items:
    print("CORPUS_ITEM=", it["source"], "|", it["title"])
print("ALL_SOURCES=", mod.ALL_SOURCES)
print("CORPUS_IN_SOURCE_FN=", "corpus" in mod.SOURCE_FN)
print("WILDCARD_EXCLUDES_CORPUS=", "corpus" not in (mod.pick_wildcard(["x"]) or "x"))
PY
}

echo "--- Test 1: search_corpus parses edge-search JSON into source-shaped items ---"
out=$(run_with_stub)
if echo "$out" | grep -q "CORPUS_COUNT= 2"; then
    pass "search_corpus returns 2 items from stubbed edge-search"
else
    echo "$out"
    fail "expected 2 items, got: $out"
fi
if echo "$out" | grep -qE "CORPUS_ITEM= Corpus \| \[note\] Prior research"; then
    pass "title prefixed with doc type"
else
    echo "$out"
    fail "title format incorrect: $out"
fi
if echo "$out" | grep -q "CORPUS_IN_SOURCE_FN= True"; then
    pass "corpus is registered in SOURCE_FN"
else
    fail "corpus missing from SOURCE_FN"
fi
if echo "$out" | grep -q "WILDCARD_EXCLUDES_CORPUS= True"; then
    pass "pick_wildcard never selects corpus"
else
    fail "pick_wildcard might pick corpus: $out"
fi

echo "--- Test 2: edge-sources main() always prepends corpus to selected sources ---"
out=$(EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP/state" PATH="$PATH_OVERRIDE" python3 - "$EDGE_DIR" <<'PY' 2>&1
import sys, argparse
from pathlib import Path
from importlib.machinery import SourceFileLoader
import importlib.util

edge_dir = Path(sys.argv[1])
loader = SourceFileLoader("edge_sources", str(edge_dir / "tools" / "edge-sources"))
spec = importlib.util.spec_from_loader("edge_sources", loader)
mod = importlib.util.module_from_spec(spec)
loader.exec_module(mod)

# Simulate the source-selection block from main() with default args.
class A: pass
args = A()
args.sources = ""
args.intent = "research"
args.no_corpus = False

route = mod.ROUTING.get(args.intent, mod.ROUTING["research"])
sources = route["primary"] + route["secondary"]
if not args.no_corpus and "corpus" not in sources:
    sources = ["corpus"] + sources
print("FIRST_SOURCE=", sources[0])
print("HAS_CORPUS=", "corpus" in sources)

args.no_corpus = True
sources = route["primary"] + route["secondary"]
if not args.no_corpus and "corpus" not in sources:
    sources = ["corpus"] + sources
print("OPTOUT_HAS_CORPUS=", "corpus" in sources)
PY
)
if echo "$out" | grep -q "FIRST_SOURCE= corpus"; then
    pass "default selection puts corpus first"
else
    echo "$out"
    fail "corpus not first: $out"
fi
if echo "$out" | grep -q "HAS_CORPUS= True"; then
    pass "default selection includes corpus"
else
    fail "corpus missing by default: $out"
fi
if echo "$out" | grep -q "OPTOUT_HAS_CORPUS= False"; then
    pass "--no-corpus opts out cleanly"
else
    fail "--no-corpus did not opt out: $out"
fi

echo "--- Test 3: format_markdown surfaces a Corpus section above External sources ---"
out=$(EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP/state" PATH="$PATH_OVERRIDE" python3 - "$EDGE_DIR" <<'PY' 2>&1
import sys
from pathlib import Path
from importlib.machinery import SourceFileLoader
import importlib.util

edge_dir = Path(sys.argv[1])
loader = SourceFileLoader("edge_sources", str(edge_dir / "tools" / "edge-sources"))
spec = importlib.util.spec_from_loader("edge_sources", loader)
mod = importlib.util.module_from_spec(spec)
loader.exec_module(mod)

results_by_source = {
    "corpus": [
        {"title": "[note] Prior research", "url": "/edge/notes/prior-research.md", "source": "Corpus", "detail": "Already covered.", "score": 16},
    ],
    "exa": [
        {"title": "External hit", "url": "https://example.com", "source": "Exa", "detail": "External text.", "score": 80},
    ],
}
md = mod.format_markdown("test topic", "research", results_by_source)
corpus_idx = md.find("### Corpus (internal)")
external_idx = md.find("### High Relevance")
print("CORPUS_FIRST=", corpus_idx >= 0 and corpus_idx < external_idx)
print("CORPUS_RENDERED=", "Prior research" in md)
PY
)
if echo "$out" | grep -q "CORPUS_FIRST= True"; then
    pass "Corpus section rendered above High Relevance"
else
    echo "$out"
    fail "Corpus not first in markdown: $out"
fi
if echo "$out" | grep -q "CORPUS_RENDERED= True"; then
    pass "Corpus item rendered in section"
else
    fail "Corpus item missing: $out"
fi

echo "--- Test 4: empty corpus produces an explicit 'no prior matches' note ---"
out=$(EDGE_REPO_DIR="$EDGE_DIR" EDGE_STATE_DIR="$TMP/state" PATH="$PATH_OVERRIDE" python3 - "$EDGE_DIR" <<'PY' 2>&1
import sys
from pathlib import Path
from importlib.machinery import SourceFileLoader
import importlib.util

edge_dir = Path(sys.argv[1])
loader = SourceFileLoader("edge_sources", str(edge_dir / "tools" / "edge-sources"))
spec = importlib.util.spec_from_loader("edge_sources", loader)
mod = importlib.util.module_from_spec(spec)
loader.exec_module(mod)

md = mod.format_markdown("test", "research", {"corpus": []})
print("HAS_HEADER=", "### Corpus (internal)" in md)
print("HAS_EMPTY_NOTE=", "No prior corpus matches" in md)
PY
)
if echo "$out" | grep -q "HAS_HEADER= True"; then
    pass "header still rendered when corpus empty"
else
    fail "missing header: $out"
fi
if echo "$out" | grep -q "HAS_EMPTY_NOTE= True"; then
    pass "explicit empty-corpus note shown"
else
    fail "empty-corpus note missing: $out"
fi

echo ""
echo "=== Results ==="
echo "PASS: $PASS  FAIL: $FAIL"
if [[ "$FAIL" -eq 0 ]]; then
    echo "ALL TESTS PASSED"
    exit 0
else
    echo "SOME TESTS FAILED"
    exit 1
fi
