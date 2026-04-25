#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"

python3 - "$EDGE_DIR" <<'PY'
import sys
import types
from pathlib import Path

edge_dir = Path(sys.argv[1])
sys.path.insert(0, str(edge_dir / "tools"))
sys.path.insert(0, str(edge_dir / "tools" / "_shared"))

# edge-apply imports routines as a top-level module. In that mode,
# `from .router_client` fails and routines must fall back to the package import
# path, not to top-level `router_client` (which breaks its own relative imports).
pkg = types.ModuleType("_shared")
pkg.__path__ = [str(edge_dir / "tools" / "_shared")]
router = types.ModuleType("_shared.router_client")

def make_client(*args, **kwargs):
    raise RuntimeError("sentinel: import succeeded")

router.make_client = make_client
sys.modules["_shared"] = pkg
sys.modules["_shared.router_client"] = router

import routines

assert routines._call_openai("test", timeout=1) is None
PY

echo "PASS: routines OpenAI fallback imports package router_client under edge-apply path layout"
