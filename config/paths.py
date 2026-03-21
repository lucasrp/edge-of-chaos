"""Shared path resolution — single source of truth for all tools.

All Python tools import paths from here instead of hardcoding.
Resolves edge_dir and memory_project_dir from branding.yaml with auto-detect fallback.
"""

import os
import sys
from pathlib import Path

# Ensure config/ is importable
_CONFIG_DIR = Path(__file__).parent
if str(_CONFIG_DIR) not in sys.path:
    sys.path.insert(0, str(_CONFIG_DIR))

from branding import load_branding

_branding = load_branding()
HOME = Path.home()

# --- EDGE_DIR: where the agent repo lives ---
_edge_dir_cfg = _branding.get("edge_dir", "")
if _edge_dir_cfg:
    EDGE_DIR = Path(os.path.expanduser(_edge_dir_cfg))
elif os.environ.get("EDGE_DIR"):
    EDGE_DIR = Path(os.environ["EDGE_DIR"])
else:
    # Auto-detect: config/ is inside the repo root
    EDGE_DIR = _CONFIG_DIR.parent

# --- MEMORY_PROJECT_DIR: Claude Code project directory name ---
_memory_project = _branding.get("memory_project_dir", "")
if not _memory_project:
    _memory_project = os.environ.get("MEMORY_PROJECT_DIR", "")
if not _memory_project:
    # Auto-detect: first project dir in ~/.claude/projects/
    _proj_base = HOME / ".claude" / "projects"
    _candidates = sorted(
        [d.name for d in _proj_base.iterdir() if d.is_dir()]
    ) if _proj_base.exists() else []
    _memory_project = _candidates[0] if _candidates else ""

MEMORY_PROJECT_DIR = _memory_project

# --- Derived paths ---
MEMORY_DIR = HOME / ".claude" / "projects" / MEMORY_PROJECT_DIR / "memory" if MEMORY_PROJECT_DIR else HOME / ".claude" / "memory"
TOPICS_DIR = MEMORY_DIR / "topics"

# Edge subdirectories
BLOG_DIR = EDGE_DIR / "blog"
ENTRIES_DIR = BLOG_DIR / "entries"
REPORTS_DIR = EDGE_DIR / "reports"
NOTES_DIR = EDGE_DIR / "notes"
TOOLS_DIR = EDGE_DIR / "tools"
LOGS_DIR = EDGE_DIR / "logs"
THREADS_DIR = EDGE_DIR / "threads"
SECRETS_DIR = EDGE_DIR / "secrets"
META_DIR = EDGE_DIR / "meta-reports"
SNAPSHOT_DIR = EDGE_DIR / "state-snapshots"
SCRATCHPADS_DIR = EDGE_DIR / "scratchpads"
STATE_DIR = EDGE_DIR / "state"
AUTONOMY_DIR = EDGE_DIR / "autonomy"
CONFIG_DIR = EDGE_DIR / "config"
SEARCH_DIR = EDGE_DIR / "search"

# Specific files
EVENTS_FILE = LOGS_DIR / "events.jsonl"
LEDGER_FILE = LOGS_DIR / "execution-ledger.jsonl"
BRIEFING_FILE = EDGE_DIR / "briefing.md"
DEBUGGING_FILE = MEMORY_DIR / "debugging.md"
INSIGHTS_FILE = MEMORY_DIR / "insights.md"
BREAKS_ACTIVE = MEMORY_DIR / "breaks-active.md"
FRONTIER_FILE = AUTONOMY_DIR / "frontier.md"
OPS_HOTSPOTS = STATE_DIR / "ops-hotspots.json"

# Skills
SKILLS_DIR = HOME / ".claude" / "skills"
RUBRIC_PATH = SKILLS_DIR / "_shared" / "report-template.md"

# Secrets
OPENAI_ENV = SECRETS_DIR / "openai.env"
XAI_ENV = SECRETS_DIR / "xai.env"

# Claude projects base (for session discovery)
PROJECTS_BASE = HOME / ".claude" / "projects"
PROJECT_DIR = PROJECTS_BASE / MEMORY_PROJECT_DIR if MEMORY_PROJECT_DIR else PROJECTS_BASE
