#!/usr/bin/env bash
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== runtime gitignore Smoke Test ==="

if git -C "$EDGE_DIR" check-ignore -q state/events/log.jsonl; then
  echo "PASS: state/events/log.jsonl is ignored"
else
  echo "FAIL: state/events/log.jsonl is not ignored"
  exit 1
fi
