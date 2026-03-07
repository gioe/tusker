"""Regression tests for tusk init CLAUDE.md injection (issue #322).

Verifies that `tusk init` appends a tusk task tool warning to CLAUDE.md,
creates CLAUDE.md when absent, and is idempotent on re-runs.
"""

import os
import subprocess

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TUSK_BIN = os.path.join(REPO_ROOT, "bin", "tusk")
SENTINEL = "<!-- tusk-task-tools -->"


def _init(tmp_path, extra_flags=None):
    """Run tusk init in tmp_path (with a real git repo so find_repo_root works)."""
    # TUSK_DB must live under tmp_path/tusk/ so that `mkdir -p "$DB_DIR"` creates
    # the tusk/ subdir before cmd_init tries to copy config.json into it.
    db_file = tmp_path / "tusk" / "tasks.db"
    env = {**os.environ, "TUSK_DB": str(db_file)}
    cmd = [TUSK_BIN, "init", "--force"] + (extra_flags or [])
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=str(tmp_path))
    assert result.returncode == 0, (
        f"tusk init failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
    return tmp_path / "CLAUDE.md"


@pytest.fixture()
def git_tmp(tmp_path):
    """A tmp_path with a bare git repo so find_repo_root resolves to it."""
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True)
    return tmp_path


def test_claude_md_created_with_warning(git_tmp):
    """tusk init creates CLAUDE.md with the sentinel when none exists."""
    claude_md = _init(git_tmp)
    assert claude_md.exists(), "CLAUDE.md should be created by tusk init"
    content = claude_md.read_text()
    assert SENTINEL in content
    assert "TaskList" in content
    assert "tusk task-list" in content


def test_claude_md_appended_when_existing(git_tmp):
    """tusk init appends the warning to an existing CLAUDE.md."""
    claude_md = git_tmp / "CLAUDE.md"
    claude_md.write_text("# My Project\n\nExisting content.\n")
    _init(git_tmp)
    content = claude_md.read_text()
    assert content.startswith("# My Project")
    assert SENTINEL in content
    assert "tusk task-list" in content


def test_claude_md_idempotent(git_tmp):
    """Re-running tusk init does not duplicate the warning."""
    _init(git_tmp)
    _init(git_tmp)
    content = (git_tmp / "CLAUDE.md").read_text()
    assert content.count(SENTINEL) == 1


def test_claude_md_skipped_with_skip_gitignore(git_tmp):
    """--skip-gitignore also skips CLAUDE.md injection (test/CI contexts)."""
    claude_md = _init(git_tmp, extra_flags=["--skip-gitignore"])
    assert not claude_md.exists(), "CLAUDE.md should not be created when --skip-gitignore is passed"
