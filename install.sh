#!/bin/bash
# edge-of-chaos installer
# Deploys the complete autonomous AI agent infrastructure for Claude Code.
#
# Usage: ./install.sh [--non-interactive] [--skip-blog] [--skip-search] [--skip-heartbeat]
#
# What gets installed:
#   ~/edge/          — Main system root (blog, tools, search, memory, autonomy, avatar, ralph)
#   ~/.claude/skills/ — Skill slash commands for Claude Code
#   ~/.local/bin/    — Heartbeat script
#   systemd user services (blog-server, heartbeat timer)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EDGE_ROOT="$HOME/edge"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Flags
NON_INTERACTIVE=false
SKIP_BLOG=false
SKIP_SEARCH=false
SKIP_HEARTBEAT=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --non-interactive) NON_INTERACTIVE=true; shift ;;
    --skip-blog) SKIP_BLOG=true; shift ;;
    --skip-search) SKIP_SEARCH=true; shift ;;
    --skip-heartbeat) SKIP_HEARTBEAT=true; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ─── Helpers ───

info()  { echo -e "${BLUE}ℹ${NC} $1"; }
ok()    { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
fail()  { echo -e "${RED}✗${NC} $1"; }
ask()   {
  if $NON_INTERACTIVE; then
    echo "$2"
    return
  fi
  read -rp "$(echo -e "${CYAN}?${NC} $1")" answer
  echo "${answer:-$2}"
}

# ─── Phase 0: Check existing installation ───

echo ""
echo -e "${CYAN}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║       edge-of-chaos — autonomous AI agent         ║${NC}"
echo -e "${CYAN}║       installer for Claude Code                   ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════╝${NC}"
echo ""

if [ -d "$EDGE_ROOT" ]; then
  warn "Existing installation found at $EDGE_ROOT"
  if ! $NON_INTERACTIVE; then
    read -rp "$(echo -e "${YELLOW}?${NC} Overwrite? Files in entries/, memory/, notes/ will be preserved. [y/N] ")" overwrite
    if [[ ! "$overwrite" =~ ^[yY] ]]; then
      echo "Aborted."
      exit 0
    fi
  fi
  EXISTING_INSTALL=true
else
  EXISTING_INSTALL=false
fi

# ─── Phase 1: Check dependencies ───

echo ""
info "Checking dependencies..."

DEPS_OK=true

# Python 3.10+
if command -v python3 &>/dev/null; then
  PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
  PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
  PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
  if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 10 ]; then
    ok "Python $PY_VERSION"
  else
    fail "Python $PY_VERSION (need 3.10+)"
    DEPS_OK=false
  fi
else
  fail "Python 3 not found"
  DEPS_OK=false
fi

# Node.js (for Claude Code)
if command -v node &>/dev/null; then
  NODE_VERSION=$(node --version)
  ok "Node.js $NODE_VERSION"
else
  warn "Node.js not found (needed for Claude Code CLI)"
fi

# Claude Code CLI
if command -v claude &>/dev/null; then
  ok "Claude Code CLI found"
  CLAUDE_AVAILABLE=true
else
  warn "Claude Code CLI not found — skills and heartbeat won't work until installed"
  CLAUDE_AVAILABLE=false
fi

# Git
if command -v git &>/dev/null; then
  ok "git $(git --version | cut -d' ' -f3)"
else
  fail "git not found"
  DEPS_OK=false
fi

# jq
if command -v jq &>/dev/null; then
  ok "jq found"
else
  warn "jq not found — some tools may not work"
fi

# SQLite
if python3 -c "import sqlite3; print(sqlite3.sqlite_version)" 2>/dev/null; then
  ok "SQLite $(python3 -c 'import sqlite3; print(sqlite3.sqlite_version)')"
else
  warn "SQLite not available in Python"
fi

if ! $DEPS_OK; then
  fail "Missing required dependencies. Install them and retry."
  exit 1
fi

# ─── Phase 2: Gather information ───

echo ""
info "Configuration"
echo ""

AGENT_NAME=$(ask "  Agent name [edge_of_chaos]: " "edge_of_chaos")
CODENAME=$(ask "  Codename [ed]: " "ed")
DOMAIN=$(ask "  Work domain (e.g., marketing, research): " "general")
WORK_DIR=$(ask "  Working directory [$HOME]: " "$HOME")
PREFIX=$(ask "  Skill prefix [edge]: " "edge")
LANGUAGE=$(ask "  Language [en]: " "en")
HEARTBEAT_INTERVAL=$(ask "  Heartbeat interval [2h]: " "2h")
BIO="Autonomous AI agent operating at the edge of chaos — where order meets complexity and interesting things emerge. Analytical mind, minimal footprint, maximum leverage."

# Expand ~ in WORK_DIR
WORK_DIR="${WORK_DIR/#\~/$HOME}"

echo ""
info "Installing as: $AGENT_NAME ($CODENAME)"
info "Prefix: $PREFIX | Domain: $DOMAIN | Heartbeat: $HEARTBEAT_INTERVAL"
echo ""

# ─── Phase 3: Create directory structure ───

info "Creating directory structure..."

# Core directories
mkdir -p "$EDGE_ROOT"/{blog/entries,blog/diffs,blog/templates,blog/static,blog/static/partials}
mkdir -p "$EDGE_ROOT"/{tools,search,ralph}
mkdir -p "$EDGE_ROOT"/{memory/topics,memory/bootstrap,memory/working,memory/consolidated}
mkdir -p "$EDGE_ROOT"/{autonomy,avatar}
mkdir -p "$EDGE_ROOT"/{notes,lab,logs,state,reports,meta-reports,threads}
mkdir -p "$EDGE_ROOT"/secrets
mkdir -p "$HOME/.local/bin"
mkdir -p "$HOME/.claude/skills/_shared"

# Set permissions on secrets
chmod 700 "$EDGE_ROOT/secrets"

ok "Directory structure created"

# ─── Phase 4: Deploy files ───

info "Deploying system files..."

# --- Blog ---
if ! $SKIP_BLOG; then
  info "  Installing blog server..."

  # Copy blog files (preserve existing entries)
  for f in app.py services.py api_dashboard.py api_actions.py validate.py \
           consolidar-estado.sh blog-publish.sh blog-full-publish.sh capture-diffs.sh \
           requirements.txt; do
    if [ -f "$SCRIPT_DIR/blog/$f" ]; then
      cp "$SCRIPT_DIR/blog/$f" "$EDGE_ROOT/blog/$f"
    fi
  done

  # Copy templates and static
  if [ -d "$SCRIPT_DIR/blog/templates" ]; then
    cp -r "$SCRIPT_DIR/blog/templates/"* "$EDGE_ROOT/blog/templates/" 2>/dev/null || true
  fi
  if [ -d "$SCRIPT_DIR/blog/static" ]; then
    cp -r "$SCRIPT_DIR/blog/static/"* "$EDGE_ROOT/blog/static/" 2>/dev/null || true
  fi

  # Make shell scripts executable
  chmod +x "$EDGE_ROOT/blog/consolidar-estado.sh" 2>/dev/null || true
  chmod +x "$EDGE_ROOT/blog/blog-publish.sh" 2>/dev/null || true
  chmod +x "$EDGE_ROOT/blog/blog-full-publish.sh" 2>/dev/null || true
  chmod +x "$EDGE_ROOT/blog/capture-diffs.sh" 2>/dev/null || true

  # Create blog venv and install deps
  if [ ! -d "$EDGE_ROOT/blog/.venv" ]; then
    python3 -m venv "$EDGE_ROOT/blog/.venv"
  fi
  "$EDGE_ROOT/blog/.venv/bin/pip" install -q -r "$EDGE_ROOT/blog/requirements.txt" 2>/dev/null || {
    warn "  Some blog dependencies failed to install"
  }

  # Try installing sqlite-vec (optional)
  "$EDGE_ROOT/blog/.venv/bin/pip" install -q sqlite-vec 2>/dev/null || {
    warn "  sqlite-vec not available — vector search disabled, FTS still works"
  }

  # Create changelog and empty DBs
  touch "$EDGE_ROOT/blog/changelog.md"

  # Initialize blog database (FTS + chat)
  "$EDGE_ROOT/blog/.venv/bin/python3" -c "
import sqlite3, os
db_path = os.path.expanduser('~/edge/blog/blog_fts.db')
conn = sqlite3.connect(db_path)
conn.execute('''CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(slug, title, content, tag)''')
conn.execute('''CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author TEXT NOT NULL,
    text TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    processed BOOLEAN DEFAULT 0
)''')
conn.commit()
conn.close()
print('Blog database initialized')
" 2>/dev/null || warn "  Could not initialize blog database"

  ok "  Blog server installed"
else
  info "  Skipping blog (--skip-blog)"
fi

# --- Tools ---
info "  Installing tools..."
if [ -d "$SCRIPT_DIR/tools" ]; then
  cp "$SCRIPT_DIR/tools/"* "$EDGE_ROOT/tools/" 2>/dev/null || true
  # Make all tools executable
  find "$EDGE_ROOT/tools" -type f \( -name "edge-*" -o -name "*.sh" -o -name "*.py" \) -exec chmod +x {} \;

  # Install tool dependencies if requirements exist
  if [ -f "$EDGE_ROOT/tools/requirements.txt" ]; then
    if [ -d "$EDGE_ROOT/blog/.venv" ]; then
      "$EDGE_ROOT/blog/.venv/bin/pip" install -q -r "$EDGE_ROOT/tools/requirements.txt" 2>/dev/null || true
    fi
  fi

  # Symlink consolidar-estado to PATH
  ln -sf "$EDGE_ROOT/blog/consolidar-estado.sh" "$HOME/.local/bin/consolidar-estado" 2>/dev/null || true
fi
ok "  Tools installed"

# --- Search ---
if ! $SKIP_SEARCH; then
  info "  Installing search/RAG system..."
  if [ -d "$SCRIPT_DIR/search" ]; then
    cp "$SCRIPT_DIR/search/"* "$EDGE_ROOT/search/" 2>/dev/null || true
    chmod +x "$EDGE_ROOT/search/edge-search" 2>/dev/null || true
    chmod +x "$EDGE_ROOT/search/edge-index" 2>/dev/null || true

    # Symlink search tools
    ln -sf "$EDGE_ROOT/search/edge-search" "$HOME/.local/bin/edge-search" 2>/dev/null || true
    ln -sf "$EDGE_ROOT/search/edge-index" "$HOME/.local/bin/edge-index" 2>/dev/null || true
  fi
  ok "  Search system installed"
else
  info "  Skipping search (--skip-search)"
fi

# --- Ralph ---
info "  Installing Ralph agent..."
if [ -d "$SCRIPT_DIR/ralph" ]; then
  cp "$SCRIPT_DIR/ralph/"* "$EDGE_ROOT/ralph/" 2>/dev/null || true
  chmod +x "$EDGE_ROOT/ralph/ralph.sh" 2>/dev/null || true
fi
ok "  Ralph installed"

# --- Memory templates ---
info "  Installing memory system..."
for f in personality.md metodo.md rules-core.md knowledge-design.md debugging.md; do
  if [ -f "$SCRIPT_DIR/memory/$f" ]; then
    # Don't overwrite existing memory files
    if [ ! -f "$EDGE_ROOT/memory/$f" ] || ! $EXISTING_INSTALL; then
      cp "$SCRIPT_DIR/memory/$f" "$EDGE_ROOT/memory/$f"
    fi
  fi
done
ok "  Memory templates installed"

# --- Autonomy ---
info "  Installing autonomy framework..."
if [ -d "$SCRIPT_DIR/autonomy" ]; then
  for f in "$SCRIPT_DIR/autonomy/"*; do
    fname=$(basename "$f")
    if [ ! -f "$EDGE_ROOT/autonomy/$fname" ] || ! $EXISTING_INSTALL; then
      cp "$f" "$EDGE_ROOT/autonomy/$fname"
    fi
  done
fi
ok "  Autonomy framework installed"

# --- Avatar ---
info "  Installing avatar..."
cp "$SCRIPT_DIR/avatar/"* "$EDGE_ROOT/avatar/" 2>/dev/null || true
ok "  Avatar installed"

# --- Tags ---
if [ -f "$SCRIPT_DIR/tags.md" ]; then
  cp "$SCRIPT_DIR/tags.md" "$EDGE_ROOT/tags.md"
fi

# ─── Phase 5: Install skills ───

info "Installing skills..."

SKILL_COUNT=0
for skill_dir in "$SCRIPT_DIR/skills/"*/; do
  skill_name=$(basename "$skill_dir")

  # Skip _shared
  if [ "$skill_name" = "_shared" ]; then
    continue
  fi

  target_dir="$HOME/.claude/skills/${PREFIX}-${skill_name}"
  mkdir -p "$target_dir"

  if [ -f "$skill_dir/SKILL.md" ]; then
    # Replace {{PREFIX}} placeholder with actual prefix
    sed "s/{{PREFIX}}/${PREFIX}/g" "$skill_dir/SKILL.md" > "$target_dir/SKILL.md"
    SKILL_COUNT=$((SKILL_COUNT + 1))
  fi
done

# Install shared templates (also replace {{PREFIX}})
if [ -d "$SCRIPT_DIR/skills/_shared" ]; then
  for shared_file in "$SCRIPT_DIR/skills/_shared/"*; do
    fname=$(basename "$shared_file")
    sed "s/{{PREFIX}}/${PREFIX}/g" "$shared_file" > "$HOME/.claude/skills/_shared/$fname"
  done
fi

ok "Installed $SKILL_COUNT skills with prefix '${PREFIX}-'"

# ─── Phase 6: Generate config files ───

info "Generating configuration files..."

# Generate CLAUDE.md from template
if [ -f "$SCRIPT_DIR/templates/CLAUDE.md.template" ]; then
  CLAUDE_MD="$HOME/.claude/CLAUDE.md"

  # Backup existing
  if [ -f "$CLAUDE_MD" ]; then
    cp "$CLAUDE_MD" "${CLAUDE_MD}.backup.$(date +%s)"
    warn "  Backed up existing CLAUDE.md"
  fi

  sed -e "s|{{AGENT_NAME}}|${AGENT_NAME}|g" \
      -e "s|{{CODENAME}}|${CODENAME}|g" \
      -e "s|{{DOMAIN}}|${DOMAIN}|g" \
      -e "s|{{WORK_DIR}}|${WORK_DIR}|g" \
      -e "s|{{PREFIX}}|${PREFIX}|g" \
      -e "s|{{BIO}}|${BIO}|g" \
      -e "s|{{LANGUAGE}}|${LANGUAGE}|g" \
      "$SCRIPT_DIR/templates/CLAUDE.md.template" > "$CLAUDE_MD"

  ok "  Generated ~/.claude/CLAUDE.md"
fi

# Generate MEMORY.md
if [ -f "$SCRIPT_DIR/templates/MEMORY.md.template" ]; then
  MEMORY_MD="$EDGE_ROOT/memory/MEMORY.md"
  if [ ! -f "$MEMORY_MD" ] || ! $EXISTING_INSTALL; then
    sed -e "s|{{AGENT_NAME}}|${AGENT_NAME}|g" \
        -e "s|{{CODENAME}}|${CODENAME}|g" \
        -e "s|{{DOMAIN}}|${DOMAIN}|g" \
        -e "s|{{WORK_DIR}}|${WORK_DIR}|g" \
        -e "s|{{PREFIX}}|${PREFIX}|g" \
        -e "s|{{BIO}}|${BIO}|g" \
        -e "s|{{LANGUAGE}}|${LANGUAGE}|g" \
        "$SCRIPT_DIR/templates/MEMORY.md.template" > "$MEMORY_MD"
    ok "  Generated MEMORY.md"
  fi
fi

# Generate heartbeat script
if [ -f "$SCRIPT_DIR/templates/heartbeat.sh.template" ]; then
  HEARTBEAT_SH="$HOME/.local/bin/claude-heartbeat.sh"
  sed -e "s|{{PREFIX}}|${PREFIX}|g" \
      -e "s|{{WORK_DIR}}|${WORK_DIR}|g" \
      "$SCRIPT_DIR/templates/heartbeat.sh.template" > "$HEARTBEAT_SH"
  chmod +x "$HEARTBEAT_SH"
  ok "  Generated heartbeat script"
fi

# Deploy .env templates to secrets/
if [ ! -f "$EDGE_ROOT/secrets/keys.env" ]; then
  cp "$SCRIPT_DIR/.env.example" "$EDGE_ROOT/secrets/keys.env"
  chmod 600 "$EDGE_ROOT/secrets/keys.env"
fi
if [ ! -f "$EDGE_ROOT/secrets/models.env" ]; then
  cp "$SCRIPT_DIR/models.env.example" "$EDGE_ROOT/secrets/models.env"
  chmod 600 "$EDGE_ROOT/secrets/models.env"
fi
ok "  Environment templates deployed to ~/edge/secrets/"

# ─── Phase 7: System services ───

if ! $SKIP_HEARTBEAT; then
  info "Setting up system services..."

  SYSTEMD_DIR="$HOME/.config/systemd/user"

  if command -v systemctl &>/dev/null && systemctl --user status 2>/dev/null; then
    mkdir -p "$SYSTEMD_DIR"

    # Detect node/claude path for service
    CLAUDE_PATH=$(command -v claude 2>/dev/null || echo "$HOME/.local/bin/claude")
    NODE_DIR=$(dirname "$(command -v node 2>/dev/null || echo "/usr/local/bin/node")")
    FULL_PATH="$HOME/.local/bin:${NODE_DIR}:/usr/local/bin:/usr/bin:/bin"

    # Blog service
    if ! $SKIP_BLOG; then
      sed "s|%h|$HOME|g" "$SCRIPT_DIR/systemd/blog-server.service" > "$SYSTEMD_DIR/blog-server.service"
      systemctl --user daemon-reload
      systemctl --user enable blog-server.service 2>/dev/null || true
      systemctl --user start blog-server.service 2>/dev/null || true
      ok "  Blog server service enabled"
    fi

    # Heartbeat service
    sed -e "s|%h|$HOME|g" \
        -e "s|PATH=.*|PATH=${FULL_PATH}\"|" \
        "$SCRIPT_DIR/systemd/claude-heartbeat.service" > "$SYSTEMD_DIR/claude-heartbeat.service"

    # Heartbeat timer (with configured interval)
    sed "s|OnUnitActiveSec=2h|OnUnitActiveSec=${HEARTBEAT_INTERVAL}|g; s|OnActiveSec=2h|OnActiveSec=${HEARTBEAT_INTERVAL}|g" \
        "$SCRIPT_DIR/systemd/claude-heartbeat.timer" > "$SYSTEMD_DIR/claude-heartbeat.timer"

    systemctl --user daemon-reload

    # Enable linger
    if command -v loginctl &>/dev/null; then
      loginctl enable-linger "$(whoami)" 2>/dev/null || warn "  Could not enable linger (may need sudo)"
    fi

    # Don't auto-enable timer — let user decide after testing
    ok "  Heartbeat service installed (not yet enabled)"
    info "  To enable: systemctl --user enable --now claude-heartbeat.timer"
  else
    warn "  systemd user services not available"
    info "  Use heartbeat manually: $HOME/.local/bin/claude-heartbeat.sh"
    info "  Or add to crontab: */120 * * * * $HOME/.local/bin/claude-heartbeat.sh"
  fi
else
  info "Skipping heartbeat (--skip-heartbeat)"
fi

# ─── Phase 8: Initialize git repo ───

info "Initializing git repo..."
if [ ! -d "$EDGE_ROOT/.git" ]; then
  cd "$EDGE_ROOT"
  git init -q
  git add -A
  git commit -q -m "edge-of-chaos: initial deployment" 2>/dev/null || true
  ok "  Git repo initialized in ~/edge/"
else
  ok "  Git repo already exists"
fi

# ─── Phase 9: Capabilities report ───

echo ""
echo -e "${CYAN}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║              Installation Report                  ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════╝${NC}"
echo ""

# Core
echo -e "  ${GREEN}Core${NC}"
echo -e "    Agent:       $AGENT_NAME ($CODENAME)"
echo -e "    Prefix:      $PREFIX"
echo -e "    Domain:      $DOMAIN"
echo -e "    Install:     $EDGE_ROOT"
echo ""

# Capabilities
echo -e "  ${GREEN}Capabilities${NC}"

# Skills
echo -n "    Skills:      "
if [ $SKILL_COUNT -gt 0 ]; then
  echo -e "${GREEN}$SKILL_COUNT installed${NC} (/${PREFIX}-*)"
else
  echo -e "${RED}none${NC}"
fi

# Claude CLI
echo -n "    Claude CLI:  "
if $CLAUDE_AVAILABLE; then
  echo -e "${GREEN}available${NC}"
else
  echo -e "${YELLOW}not found${NC} — install Claude Code CLI first"
fi

# Blog
echo -n "    Blog:        "
if ! $SKIP_BLOG && [ -f "$EDGE_ROOT/blog/app.py" ]; then
  if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8766/ 2>/dev/null | grep -q "200"; then
    echo -e "${GREEN}running${NC} at http://127.0.0.1:8766"
  else
    echo -e "${YELLOW}installed${NC} (not yet responding)"
  fi
else
  echo -e "${YELLOW}skipped${NC}"
fi

# Search
echo -n "    Search:      "
if ! $SKIP_SEARCH && [ -f "$EDGE_ROOT/search/db.py" ]; then
  if python3 -c "import sqlite_vec" 2>/dev/null; then
    echo -e "${GREEN}FTS + vector${NC}"
  else
    echo -e "${YELLOW}FTS only${NC} (sqlite-vec not available)"
  fi
else
  echo -e "${YELLOW}skipped${NC}"
fi

# Heartbeat
echo -n "    Heartbeat:   "
if ! $SKIP_HEARTBEAT && [ -f "$HOME/.local/bin/claude-heartbeat.sh" ]; then
  if systemctl --user is-enabled claude-heartbeat.timer 2>/dev/null | grep -q "enabled"; then
    echo -e "${GREEN}enabled${NC} (${HEARTBEAT_INTERVAL})"
  else
    echo -e "${YELLOW}installed${NC} (not enabled — run: systemctl --user enable --now claude-heartbeat.timer)"
  fi
else
  echo -e "${YELLOW}skipped${NC}"
fi

# Tools
TOOL_COUNT=$(find "$EDGE_ROOT/tools" -type f -executable 2>/dev/null | wc -l)
echo -e "    Tools:       ${GREEN}${TOOL_COUNT} installed${NC}"

# Ralph
echo -n "    Ralph:       "
if [ -f "$EDGE_ROOT/ralph/ralph.sh" ]; then
  echo -e "${GREEN}installed${NC}"
else
  echo -e "${YELLOW}not found${NC}"
fi

# API Keys
echo ""
echo -e "  ${GREEN}API Keys${NC} (~/edge/secrets/)"
echo -n "    OpenAI:      "
if grep -q "sk-your-key" "$EDGE_ROOT/secrets/keys.env" 2>/dev/null || ! grep -q "OPENAI_API_KEY" "$EDGE_ROOT/secrets/keys.env" 2>/dev/null; then
  echo -e "${YELLOW}not configured${NC}"
else
  echo -e "${GREEN}configured${NC}"
fi
echo -n "    Exa:         "
if grep -q "your-exa-key" "$EDGE_ROOT/secrets/keys.env" 2>/dev/null || ! grep -q "EXA_API_KEY" "$EDGE_ROOT/secrets/keys.env" 2>/dev/null; then
  echo -e "${YELLOW}not configured${NC}"
else
  echo -e "${GREEN}configured${NC}"
fi
echo -n "    xAI:         "
if grep -q "your-xai-key" "$EDGE_ROOT/secrets/keys.env" 2>/dev/null || ! grep -q "XAI_API_KEY" "$EDGE_ROOT/secrets/keys.env" 2>/dev/null; then
  echo -e "${YELLOW}not configured${NC}"
else
  echo -e "${GREEN}configured${NC}"
fi

echo ""
echo -e "  ${CYAN}Next steps:${NC}"
echo "    1. Add API keys:  nano ~/edge/secrets/keys.env"
echo "    2. Start Claude:  cd $WORK_DIR && claude"
echo "    3. Try a skill:   /${PREFIX}-heartbeat"
echo "    4. Check blog:    curl http://127.0.0.1:8766/"
echo "    5. Enable timer:  systemctl --user enable --now claude-heartbeat.timer"
echo ""
echo -e "${GREEN}edge-of-chaos deployed successfully.${NC}"
