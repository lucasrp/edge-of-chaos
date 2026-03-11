import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
from click.testing import CliRunner
from edge_of_chaos.cli import main


# Input for the init command: project name, domain (empty), language (default), skill prefix
INIT_INPUT = 'test-project\n\n\nen\ncx\n'


def test_init_creates_structure():
    """Test that init creates the expected directory structure."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ['init'], input=INIT_INPUT)
        assert result.exit_code == 0
        assert Path('.continuum').exists()
        assert Path('.continuum/config/continuum.toml').exists()
        assert Path('.continuum/memory/working').exists()
        assert Path('.continuum/memory/bootstrap').exists()
        assert Path('.continuum/memory/consolidated').exists()
        assert Path('.continuum/skills/core').exists()
        assert Path('.continuum/skills/local').exists()
        assert Path('.continuum/templates/CLAUDE.md').exists()


@patch('edge_of_chaos.scan.find_transcripts', return_value=[])
def test_scan_no_transcripts(mock_find):
    """Test scan handles missing transcripts gracefully."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        runner.invoke(main, ['init'], input=INIT_INPUT)
        result = runner.invoke(main, ['scan'])
        assert result.exit_code == 0  # should not crash


def test_doctor_after_init():
    """Test doctor passes after fresh init."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        runner.invoke(main, ['init'], input=INIT_INPUT)
        result = runner.invoke(main, ['doctor'])
        # Should not crash, some checks may fail (e.g. claude CLI)
        assert result.exit_code in (0, 1)


def test_status_after_init():
    """Test status works after fresh init."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        runner.invoke(main, ['init'], input=INIT_INPUT)
        result = runner.invoke(main, ['status'])
        assert result.exit_code == 0


def test_skills_list():
    """Test skills list shows available skills."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        runner.invoke(main, ['init'], input=INIT_INPUT)
        result = runner.invoke(main, ['skills', 'list'])
        assert result.exit_code == 0


def test_skills_new():
    """Test creating a new skill."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        runner.invoke(main, ['init'], input=INIT_INPUT)
        result = runner.invoke(main, ['skills', 'new', 'my-custom-skill'])
        assert result.exit_code == 0
        assert Path('.continuum/skills/local/my-custom-skill/skill.yaml').exists()
        assert Path('.continuum/skills/local/my-custom-skill/prompt.md').exists()


@patch('edge_of_chaos.scan.find_transcripts', return_value=[])
def test_scan_with_fake_transcripts(mock_find):
    """Test scan with synthetic transcript data."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        runner.invoke(main, ['init'], input=INIT_INPUT)
        # Create fake transcript
        t_dir = Path('.claude-test/projects/-test/conversations')
        # Actually this should scan ~/.claude which is the real dir
        # For now just test that scan doesn't crash
        result = runner.invoke(main, ['scan', '--dry-run'])
        assert result.exit_code == 0
