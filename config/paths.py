"""Shared path resolution — single source of truth for all tools.

Genotype and phenotype intentionally have different roots:

- EDGE_REPO_DIR: shared code/runtime root
- EDGE_STATE_DIR: instance-local mutable state root

During the migration, EDGE_STATE_DIR falls back to EDGE_REPO_DIR so existing
instances keep working until their runtime env is updated.
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


def _expand(value: str | None) -> Path | None:
    if not value:
        return None
    return Path(os.path.expanduser(value))


# --- Shared genotype root (repo checkout) ---
EDGE_REPO_DIR = (
    _expand(os.environ.get("EDGE_REPO_DIR"))
    or _expand(_branding.get("edge_dir", ""))
    or _expand(os.environ.get("EDGE_DIR"))
    or _CONFIG_DIR.parent
)

# Legacy alias kept during migration.
EDGE_DIR = EDGE_REPO_DIR

# --- Instance identity / mutable phenotype root ---
EDGE_INSTANCE = (
    os.environ.get("EDGE_INSTANCE")
    or os.environ.get("EDGE_CODENAME")
    or _branding.get("codename", "")
    or _branding.get("skill_prefix", "")
    or ""
)

EDGE_STATE_DIR = (
    _expand(os.environ.get("EDGE_STATE_DIR"))
    or _expand(_branding.get("edge_state_dir", ""))
    or EDGE_REPO_DIR
)

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

# Genotype subdirectories
BLOG_DIR = EDGE_REPO_DIR / "blog"
TOOLS_DIR = EDGE_REPO_DIR / "tools"
SECRETS_DIR = EDGE_REPO_DIR / "secrets"
AUTONOMY_DIR = EDGE_REPO_DIR / "autonomy"
CONFIG_DIR = EDGE_REPO_DIR / "config"
SEARCH_DIR = EDGE_REPO_DIR / "search"

# Phenotype subdirectories
BLOG_STATE_DIR = EDGE_STATE_DIR / "blog"
ENTRIES_DIR = BLOG_STATE_DIR / "entries"
BLOG_DIFFS_DIR = BLOG_STATE_DIR / "diffs"
BLOG_COMMENTS_FILE = BLOG_STATE_DIR / "comments.json"
BLOG_CHANGELOG_FILE = BLOG_STATE_DIR / "changelog.md"
COMMENTS_FILE = BLOG_COMMENTS_FILE
DIFFS_DIR = BLOG_DIFFS_DIR
REPORTS_DIR = EDGE_STATE_DIR / "reports"
NOTES_DIR = EDGE_STATE_DIR / "notes"
BUILDS_DIR = EDGE_STATE_DIR / "builds"
LOGS_DIR = EDGE_STATE_DIR / "logs"
THREADS_DIR = EDGE_STATE_DIR / "threads"
HEALTH_DIR = EDGE_STATE_DIR / "health"
META_DIR = EDGE_STATE_DIR / "meta-reports"
META_REPORTS_DIR = META_DIR
SNAPSHOT_DIR = EDGE_STATE_DIR / "state-snapshots"
SCRATCHPADS_DIR = EDGE_STATE_DIR / "scratchpads"
STATE_DIR = EDGE_STATE_DIR / "state"
STATE_EVENTS_DIR = STATE_DIR / "events"
SIGNALS_DIR = STATE_DIR / "signals"
SEARCH_STATE_DIR = EDGE_STATE_DIR / "search"
DB_DIR = EDGE_STATE_DIR / "db"
LIBEXEC_DIR = EDGE_STATE_DIR / "libexec" / (EDGE_INSTANCE or "agent")
SEARCH_DB_FILE = SEARCH_STATE_DIR / "edge-memory.db"
BLOG_FTS_DB_FILE = BLOG_STATE_DIR / "blog_fts.db"

# Specific files
EVENTS_FILE = LOGS_DIR / "events.jsonl"
STATE_EVENTS_FILE = STATE_EVENTS_DIR / "log.jsonl"
LEDGER_FILE = LOGS_DIR / "execution-ledger.jsonl"
EXECUTION_LEDGER_FILE = LEDGER_FILE
PIPELINE_FAILURES_FILE = LOGS_DIR / "pipeline-failures.jsonl"
SKILL_STEPS_FILE = LOGS_DIR / "skill-steps.jsonl"
STATE_LINT_FILE = LOGS_DIR / "state-lint.jsonl"
YAML_RENDER_FILE = LOGS_DIR / "yaml-render.jsonl"
CURRENT_BEAT_FILE = STATE_DIR / "current-beat.json"
CURRENT_DISPATCH_FILE = STATE_DIR / "current-dispatch.json"
BRIEFING_FILE = EDGE_STATE_DIR / "briefing.md"
GIT_SIGNALS_FILE = STATE_DIR / "git-signals.json"
CURADORIA_CANDIDATES_FILE = STATE_DIR / "curadoria-candidates.json"
PROPOSALS_FILE = STATE_DIR / "proposals.json"
PROCEDURE_CURATION_FILE = STATE_DIR / "procedure-curation.json"
SOURCE_USAGE_FILE = STATE_DIR / "source-usage.jsonl"
SOURCES_MANIFEST_FILE = STATE_DIR / "sources-manifest.yaml"
PRIMITIVES_STATUS_FILE = STATE_DIR / "primitives-status.json"
RENDER_INSTALL_DRIFT_FILE = STATE_DIR / "render-install-drift.json"
DEBUGGING_FILE = MEMORY_DIR / "debugging.md"
INSIGHTS_FILE = MEMORY_DIR / "insights.md"
BREAKS_ACTIVE = MEMORY_DIR / "breaks-active.md"
FRONTIER_FILE = AUTONOMY_DIR / "frontier.md"
AUTONOMY_CAPABILITIES_FILE = AUTONOMY_DIR / "capabilities.md"
OPS_HOTSPOTS = STATE_DIR / "ops-hotspots.json"
HEALTH_CURRENT_FILE = HEALTH_DIR / "current.json"
HEALTH_HISTORY_FILE = HEALTH_DIR / "history.jsonl"
HEALTH_LAST_SUCCESS_FILE = HEALTH_DIR / "last_success"

# Skills
SKILLS_DIR = HOME / ".claude" / "skills"
RUBRIC_PATH = SKILLS_DIR / "_shared" / "report-template.md"

# Secrets
OPENAI_ENV = SECRETS_DIR / "openai.env"
XAI_ENV = SECRETS_DIR / "xai.env"

# Claude projects base (for session discovery)
PROJECTS_BASE = HOME / ".claude" / "projects"
PROJECT_DIR = PROJECTS_BASE / MEMORY_PROJECT_DIR if MEMORY_PROJECT_DIR else PROJECTS_BASE
