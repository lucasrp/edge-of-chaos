"""Discover Claude Code transcript files (.jsonl) on disk."""

from __future__ import annotations

from pathlib import Path


# Default location where Claude Code stores project conversations
CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"


def find_transcripts(
    search_dir: Path | None = None,
) -> list[Path]:
    """Find all .jsonl transcript files under the Claude Code projects directory.

    Searches recursively under ~/.claude/projects/*/ by default.
    Handles nested project paths (e.g. -home-user-projects-foo/).

    Returns a sorted list of Path objects (sorted by modification time, newest first).
    """
    if search_dir is None:
        search_dir = CLAUDE_PROJECTS_DIR

    if not search_dir.exists():
        return []

    transcripts: list[Path] = []

    # Walk all subdirectories looking for .jsonl files
    for jsonl_file in search_dir.rglob("*.jsonl"):
        if jsonl_file.is_file():
            transcripts.append(jsonl_file)

    # Sort by modification time, newest first
    transcripts.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    return transcripts


def group_by_project(transcripts: list[Path]) -> dict[str, list[Path]]:
    """Group transcript files by their project directory name.

    Claude Code uses directory names like `-home-user-projects-foo` as project
    identifiers. This function groups transcripts by the first-level directory
    under the search root.

    Returns a dict mapping project name -> list of transcript paths.
    """
    groups: dict[str, list[Path]] = {}

    for path in transcripts:
        # Walk up to find the project-level directory (child of "projects/")
        parts = path.parts
        project_name = "unknown"
        for i, part in enumerate(parts):
            if part == "projects" and i + 1 < len(parts):
                project_name = parts[i + 1]
                break

        groups.setdefault(project_name, []).append(path)

    return groups


def report_stats(transcripts: list[Path]) -> dict:
    """Generate discovery stats for display.

    Returns dict with:
        total_files: int
        total_size_bytes: int
        projects: dict[str, int]  (project name -> file count)
    """
    groups = group_by_project(transcripts)
    total_size = sum(p.stat().st_size for p in transcripts)

    return {
        "total_files": len(transcripts),
        "total_size_bytes": total_size,
        "projects": {name: len(files) for name, files in groups.items()},
    }
