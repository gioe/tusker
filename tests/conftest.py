"""Shared pytest fixtures for tusk tests.

All Python scripts under bin/ accept:
    sys.argv[1] — db_path
    sys.argv[2] — config_path
    sys.argv[3:] — command-specific flags

Use these fixtures as the foundation for all unit and integration tests.
"""

import os
import subprocess

import pytest

# Repo root is the parent of the tests/ directory.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TUSK_BIN = os.path.join(REPO_ROOT, "bin", "tusk")


@pytest.fixture()
def config_path():
    """Return the path to config.default.json."""
    return os.path.join(REPO_ROOT, "config.default.json")


@pytest.fixture()
def db_path(tmp_path, config_path):
    """Initialise a fresh tusk SQLite DB in tmp_path via `bin/tusk init`.

    Uses the TUSK_DB env-var override so the live tusk/tasks.db is never
    touched.  Returns the resolved Path to the initialised database file.
    """
    db_file = tmp_path / "tasks.db"
    env = {
        **os.environ,
        "TUSK_DB": str(db_file),
    }
    result = subprocess.run(
        [TUSK_BIN, "init", "--force", "--skip-gitignore"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"tusk init failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
    assert db_file.exists(), f"Expected DB at {db_file} after tusk init"
    return db_file
