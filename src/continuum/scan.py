"""Continuum scan — full pipeline: discover → parse → heuristics → sanitize → write."""

from __future__ import annotations

from pathlib import Path

import click

from continuum.scanner.bootstrap import write_bootstrap
from continuum.scanner.discover import find_transcripts, report_stats
from continuum.scanner.heuristics import run_heuristics
from continuum.scanner.parser import parse_transcripts, report_parse_stats
from continuum.scanner.sanitize import sanitize


def run_scan(
    sanitization: str = "balanced",
    max_sessions: int = 200,
    dry_run: bool = False,
    root: Path | None = None,
) -> bool:
    """Run the full scan pipeline.

    Args:
        sanitization: Sanitization mode (strict/balanced/raw).
        max_sessions: Maximum number of sessions to process.
        dry_run: If True, show what would be extracted without writing.
        root: Project root (default: cwd).

    Returns:
        True if scan completed successfully, False if no transcripts found.
    """
    if root is None:
        root = Path.cwd()

    # --- Step 1: Discover ---
    click.echo("Scanning for Claude Code transcripts...")
    transcripts = find_transcripts()

    if not transcripts:
        click.echo()
        click.echo("No transcripts found.")
        click.echo()
        click.echo("Claude Code stores conversations in ~/.claude/projects/*/")
        click.echo("Make sure you have used Claude Code at least once to generate transcripts.")
        return False

    stats = report_stats(transcripts)
    total_size_mb = stats["total_size_bytes"] / (1024 * 1024)
    click.echo(f"Found {stats['total_files']} transcript(s) across {len(stats['projects'])} project(s) ({total_size_mb:.1f} MB)")

    # Show top projects
    sorted_projects = sorted(stats["projects"].items(), key=lambda x: x[1], reverse=True)
    for name, count in sorted_projects[:5]:
        click.echo(f"  {name}: {count} file(s)")
    if len(sorted_projects) > 5:
        click.echo(f"  ... and {len(sorted_projects) - 5} more")
    click.echo()

    # --- Step 2: Parse ---
    limit = min(max_sessions, len(transcripts))
    click.echo(f"Parsing {limit} session(s)...")
    sessions = parse_transcripts(transcripts, max_sessions=max_sessions)

    parse_stats = report_parse_stats(sessions)
    click.echo(f"  {parse_stats['total_messages']} messages ({parse_stats['total_human']} human, {parse_stats['total_assistant']} assistant)")
    if parse_stats["total_parse_errors"] > 0:
        click.echo(f"  {parse_stats['total_parse_errors']} parse error(s) skipped")
    click.echo()

    # Filter out empty sessions
    sessions = [s for s in sessions if s.message_count > 0]
    if not sessions:
        click.echo("No parseable messages found in transcripts.")
        return False

    # --- Step 3: Heuristics ---
    click.echo("Extracting preferences and patterns...")
    result = run_heuristics(sessions)
    click.echo()

    # --- Step 4: Sanitize ---
    click.echo(f"Sanitizing ({sanitization} mode)...")
    result = sanitize(result, mode=sanitization)
    click.echo()

    # --- Step 5: Print summary ---
    _print_summary(result)

    # --- Step 6: Write ---
    if dry_run:
        click.echo("Dry run — no files written.")
        click.echo("Run without --dry-run to write bootstrap memory.")
    else:
        click.echo("Writing bootstrap memory...")
        files = write_bootstrap(result, root=root, mode=sanitization)
        bootstrap_dir = root / ".continuum" / "memory" / "bootstrap"
        click.echo(f"  Wrote {len(files)} file(s) to {bootstrap_dir}/")
        for fname in sorted(files):
            click.echo(f"    {fname}")

    click.echo()
    click.echo("Done.")
    return True


def _print_summary(result) -> None:
    """Print a human-readable summary of extracted data."""
    click.echo("── Summary ──")
    click.echo()

    # Preferences
    if result.preferences:
        click.echo(f"Preferences ({len(result.preferences)}):")
        for p in result.preferences:
            click.echo(f"  [{p.category}] {p.value} (confidence: {p.confidence}, seen {p.occurrences}x)")
    else:
        click.echo("Preferences: none detected")
    click.echo()

    # Corrections
    click.echo(f"Corrections: {len(result.corrections)} detected")
    click.echo()

    # Tech stack (top 10)
    if result.tech_stack:
        top_tech = list(result.tech_stack.items())[:10]
        click.echo(f"Tech stack ({len(result.tech_stack)} items, top 10):")
        for tech, count in top_tech:
            click.echo(f"  {tech}: {count}")
    else:
        click.echo("Tech stack: none detected")
    click.echo()

    # Topics (top 10)
    if result.topics:
        top_topics = list(result.topics.items())[:10]
        click.echo(f"Topics ({len(result.topics)} items, top 10):")
        for topic, count in top_topics:
            click.echo(f"  {topic}: {count}")
    else:
        click.echo("Topics: none detected")
    click.echo()
