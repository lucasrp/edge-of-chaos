#!/bin/bash
# blog-publish — Publicação atômica de blog entries
# Uso: blog-publish <path-to-entry.md>
#
# Faz TUDO que "publicar no blog" requer, numa única chamada:
# 1. Valida que o arquivo existe e tem frontmatter válido
# 2. Indexa no SQLite (edge-index)
# 2.5. Busca related posts
# 3. Atualiza changelog
# 4. Verifica que a entry está visível
#
# Exit codes: 0 = sucesso, 1 = erro

set -euo pipefail

# --- Load shared paths (branding, memory, blog config) ---
# shellcheck source=../config/paths.sh
REAL_SCRIPT="$(readlink -f "$0")"
source "$(dirname "$REAL_SCRIPT")/../config/paths.sh"
CHANGELOG="$BLOG_DIR/changelog.md"
API_URL="$BLOG_URL"
ENTRY_PATH="${1:-}"

if [[ -z "$ENTRY_PATH" ]]; then
    echo "ERROR: Usage: blog-publish <path-to-entry.md>"
    exit 1
fi

# Resolve to absolute path
if [[ ! "$ENTRY_PATH" = /* ]]; then
    ENTRY_PATH="$(pwd)/$ENTRY_PATH"
fi

if [[ ! -f "$ENTRY_PATH" ]]; then
    echo "ERROR: File not found: $ENTRY_PATH"
    exit 1
fi

FILENAME=$(basename "$ENTRY_PATH")
SLUG="${FILENAME%.md}"

# Guardrail: BLOCK direct calls — everything must go through consolidate-state
if [[ -z "${CALLED_FROM_CONSOLIDAR_ESTADO:-}" && -z "${CALLED_FROM_FULL_PUBLISH:-}" ]]; then
    echo "ERROR: blog-publish.sh cannot be called directly."
    echo "       Use: consolidate-state <entry.md> [report.yaml]"
    echo "       Reason: every publication requires meta-report + state audit."
    exit 1
fi

echo "=== blog-publish: $SLUG ==="

# --- Step 1: Validate frontmatter ---
echo "[1/6] Validating frontmatter..."
FRONTMATTER=$(python3 -c "
import yaml, sys
raw = open('$ENTRY_PATH').read()
parts = raw.split('---', 2)
if len(parts) < 3:
    print('ERROR: No valid YAML frontmatter')
    sys.exit(1)
fm = yaml.safe_load(parts[1])
if not fm:
    print('ERROR: Empty frontmatter')
    sys.exit(1)
errors = []
if not fm.get('title'):
    errors.append('Missing field: title')
if not fm.get('date'):
    errors.append('Missing field: date')
tags = fm.get('tags', [])
if not tags or (isinstance(tags, list) and len(tags) == 0):
    if not fm.get('tag'):
        errors.append('Missing field: tags — add tags: [tag1, tag2, ...]')
claims = fm.get('claims', [])
if not claims or (isinstance(claims, list) and len(claims) == 0):
    errors.append('Missing field: claims — add claims: with at least 1 verified claim')
threads = fm.get('threads', [])
if not threads or (isinstance(threads, list) and len(threads) == 0):
    errors.append('Missing field: threads — add threads: [related-thread]')
keywords = fm.get('keywords', [])
if not keywords or (isinstance(keywords, list) and len(keywords) == 0):
    errors.append('Missing field: keywords — add keywords: [kw1, kw2, ...] for retrieval')
body = parts[2].strip()
if len(body) < 50:
    errors.append(f'Body too short ({len(body)} chars, minimum 50)')
if errors:
    for e in errors:
        print(f'ERROR: {e}')
    sys.exit(1)
# Extract title for comment
print(fm.get('title', '$SLUG'))
" 2>&1) || true

if echo "$FRONTMATTER" | grep -q '^ERROR:'; then
    echo "$FRONTMATTER"
    exit 1
fi
TITLE="$FRONTMATTER"
echo "  OK: '$TITLE'"

# --- Step 2: Index in SQLite ---
echo "[2/6] Indexing in SQLite (edge-index)..."
if command -v edge-index &>/dev/null; then
    edge-index "$ENTRY_PATH" 2>/dev/null || echo "  WARN: edge-index returned error (non-fatal)"
else
    echo "  WARN: edge-index not found in PATH"
fi

# --- Step 2.5: Find related posts ---
echo "[2.5/6] Finding related posts..."
SEARCH_PYTHON="$EDGE_DIR/search/.venv/bin/python3"
[ -x "$SEARCH_PYTHON" ] || SEARCH_PYTHON="python3"
RELATED_OUTPUT=$($SEARCH_PYTHON "$EDGE_DIR/search/related.py" "$ENTRY_PATH" 5 2>&1) || true
if echo "$RELATED_OUTPUT" | grep -q "^Related"; then
    echo "  $RELATED_OUTPUT" | head -6
else
    echo "  SKIP: $RELATED_OUTPUT"
fi

# --- Step 3: Update changelog ---
echo "[3/5] Updating changelog..."
TIMESTAMP=$(date +"%Y-%m-%d ~%H:%M")
CHANGELOG_ENTRY="## $TIMESTAMP — $TITLE

**Blog:** $FILENAME (created)
**Report:** $(python3 -c "
import yaml
raw = open('$ENTRY_PATH').read()
parts = raw.split('---', 2)
fm = yaml.safe_load(parts[1])
print(fm.get('report', 'none'))
")
"

if [[ -f "$CHANGELOG" ]]; then
    # Prepend to changelog (after first line if it's a header)
    FIRST_LINE=$(head -1 "$CHANGELOG")
    if [[ "$FIRST_LINE" == "#"* ]]; then
        {
            echo "$FIRST_LINE"
            echo ""
            echo "$CHANGELOG_ENTRY"
            tail -n +2 "$CHANGELOG"
        } > "${CHANGELOG}.tmp" && mv "${CHANGELOG}.tmp" "$CHANGELOG"
    else
        {
            echo "$CHANGELOG_ENTRY"
            cat "$CHANGELOG"
        } > "${CHANGELOG}.tmp" && mv "${CHANGELOG}.tmp" "$CHANGELOG"
    fi
else
    echo "# Blog Changelog" > "$CHANGELOG"
    echo "" >> "$CHANGELOG"
    echo "$CHANGELOG_ENTRY" >> "$CHANGELOG"
fi
echo "  OK: Changelog updated"

# --- Step 4: Verify ---
echo "[4/5] Verifying..."
VERIFY_OK=true

# Check SQLite
python3 -c "
import sys, os
sys.path.insert(0, os.path.join(os.environ.get('EDGE_DIR', os.path.expanduser('~/edge')), 'search'))
try:
    from db import ensure_db
    conn = ensure_db()
    r = conn.execute(\"SELECT length(content) FROM documents WHERE path=?\", ('$ENTRY_PATH',)).fetchone()
    if r and r[0] > 0:
        print(f'  SQLite: OK ({r[0]} chars)')
    else:
        print('  SQLite: MISSING or empty')
        sys.exit(1)
    conn.close()
except Exception as e:
    print(f'  SQLite: WARN - {e}')
" 2>&1 || VERIFY_OK=false

# Check API visibility (use slug endpoint to avoid loading all entries)
VISIBLE=$(curl -s -m 10 "$API_URL/blog/entries/" 2>/dev/null | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    found = any(e.get('slug') == '$SLUG' for e in data)
    print('OK' if found else 'NOT FOUND')
except:
    print('SERVER ERROR')
" 2>&1 || echo "SERVER ERROR")
echo "  API /blog/entries/: $VISIBLE"
if [[ "$VISIBLE" != "OK" ]]; then
    VERIFY_OK=false
fi

if $VERIFY_OK; then
    echo ""
    echo "=== PUBLISHED: $SLUG ==="
    exit 0
else
    echo ""
    echo "=== WARN: Published with issues (verify manually) ==="
    exit 0  # Non-fatal — entry exists, just might need attention
fi
