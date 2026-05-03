#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/blog/entries" "$TMP/reports"

today="$(date +%F)"
old_day="$(date -d '10 days ago' +%F)"

cat > "$TMP/blog/entries/${today}-valid-entry.md" <<EOF
---
title: Recent valid entry
date: ${today}
report: ${today}-valid-entry.html
---

Recent valid body.
EOF

cat > "$TMP/reports/${today}-valid-entry.html" <<'EOF'
<html><body>recent report</body></html>
EOF

cat > "$TMP/blog/entries/${old_day}-old-broken-ref.md" <<EOF
---
title: Old broken ref
date: ${old_day}
report: missing-old-report.html
---

Old broken body.
EOF

cat > "$TMP/blog/entries/${old_day}-old-wrong-format.md" <<EOF
---
title: Old wrong format
date: ${old_day}
report: reports/${old_day}-old-wrong-format.html
---

Old wrong-format body.
EOF

cat > "$TMP/reports/${old_day}-old-wrong-format.html" <<'EOF'
<html><body>old report</body></html>
EOF

cat > "$TMP/reports/spec-legacy-orphan.html" <<'EOF'
<html><body>undated legacy orphan</body></html>
EOF

if ! EDGE_REPO_DIR="$ROOT" EDGE_STATE_DIR="$TMP" python3 "$ROOT/blog/validate.py" --recent > "$TMP/recent.out"; then
  cat "$TMP/recent.out"
  echo "expected --recent to ignore historical broken refs" >&2
  exit 1
fi

if EDGE_REPO_DIR="$ROOT" EDGE_STATE_DIR="$TMP" python3 "$ROOT/blog/validate.py" > "$TMP/full.out"; then
  cat "$TMP/full.out"
  echo "expected full validation to report historical broken refs" >&2
  exit 1
fi

grep -q "ALL CLEAR" "$TMP/recent.out"
grep -q "BROKEN REFS" "$TMP/full.out"
grep -q "WRONG FORMAT" "$TMP/full.out"
grep -q "spec-legacy-orphan.html" "$TMP/full.out"

cat > "$TMP/reports/${today}-orphan-report.html" <<'EOF'
<html><body>recent orphan</body></html>
EOF

if EDGE_REPO_DIR="$ROOT" EDGE_STATE_DIR="$TMP" python3 "$ROOT/blog/validate.py" --recent > "$TMP/recent-orphan.out"; then
  cat "$TMP/recent-orphan.out"
  echo "expected --recent to report dated recent orphan reports" >&2
  exit 1
fi

grep -q "ORPHAN REPORTS" "$TMP/recent-orphan.out"
grep -q "${today}-orphan-report.html" "$TMP/recent-orphan.out"
