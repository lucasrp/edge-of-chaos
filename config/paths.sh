#!/usr/bin/env bash
# paths.sh — Shared path resolution for shell scripts.
# Source this from any script: source "$(dirname "$0")/../config/paths.sh"

# --- EDGE_DIR: derive from this script's location (repo root) ---
if [ -z "${EDGE_DIR:-}" ]; then
  EDGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi

# --- Load branding.yaml ---
BRANDING_FILE="$EDGE_DIR/config/branding.yaml"
if [ -f "$BRANDING_FILE" ]; then
  BLOG_PORT=$(grep '^  port:' "$BRANDING_FILE" 2>/dev/null | head -1 | awk '{print $2}')
  BLOG_AUTH_ENABLED=$(grep '^  auth_enabled:' "$BRANDING_FILE" 2>/dev/null | head -1 | awk '{print $2}')
  BLOG_AUTH_USER=$(grep '^  auth_user:' "$BRANDING_FILE" 2>/dev/null | head -1 | awk '{print $2}' | tr -d '"')
  BLOG_AUTH_PASS=$(grep '^  auth_pass:' "$BRANDING_FILE" 2>/dev/null | head -1 | awk '{print $2}' | tr -d '"')
  MEMORY_PROJECT_DIR=$(grep '^memory_project_dir:' "$BRANDING_FILE" 2>/dev/null | head -1 | awk '{print $2}' | tr -d '"')
  SKILL_PREFIX=$(grep '^skill_prefix:' "$BRANDING_FILE" 2>/dev/null | head -1 | awk '{print $2}' | tr -d '"')
else
  BLOG_PORT=8766
  BLOG_AUTH_ENABLED=false
  BLOG_AUTH_USER=""
  BLOG_AUTH_PASS=""
  MEMORY_PROJECT_DIR=""
  SKILL_PREFIX="agent"
fi

# Defaults
BLOG_PORT=${BLOG_PORT:-8766}
SKILL_PREFIX=${SKILL_PREFIX:-agent}
BLOG_URL="http://localhost:${BLOG_PORT}"

# Curl auth flag
CURL_AUTH=""
if [ "$BLOG_AUTH_ENABLED" = "true" ] && [ -n "$BLOG_AUTH_USER" ]; then
  CURL_AUTH="-u ${BLOG_AUTH_USER}:${BLOG_AUTH_PASS}"
fi

# --- Memory path ---
if [ -n "$MEMORY_PROJECT_DIR" ]; then
  MEMORY_BASE="$HOME/.claude/projects/${MEMORY_PROJECT_DIR}/memory"
  PROJECT_DIR="$HOME/.claude/projects/${MEMORY_PROJECT_DIR}"
else
  _first_proj=$(ls "$HOME/.claude/projects/" 2>/dev/null | head -1)
  MEMORY_BASE="$HOME/.claude/projects/${_first_proj}/memory"
  PROJECT_DIR="$HOME/.claude/projects/${_first_proj}"
fi

# Export key variables for embedded Python heredocs
export EDGE_DIR MEMORY_BASE MEMORY_PROJECT_DIR BLOG_URL PROJECT_DIR BLOG_AUTH_USER BLOG_AUTH_PASS BLOG_AUTH_ENABLED BLOG_PORT

# --- Derived paths ---
BLOG_DIR="$EDGE_DIR/blog"
ENTRIES_DIR="$BLOG_DIR/entries"
REPORTS_DIR="$EDGE_DIR/reports"
NOTES_DIR="$EDGE_DIR/notes"
TOOLS_DIR="$EDGE_DIR/tools"
LOGS_DIR="$EDGE_DIR/logs"
THREADS_DIR="$EDGE_DIR/threads"
SECRETS_DIR="$EDGE_DIR/secrets"
