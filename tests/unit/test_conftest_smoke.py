"""Smoke tests verifying conftest fixtures are functional."""

import os
import sqlite3


def test_config_path_exists(config_path):
    assert os.path.isfile(config_path), f"config.default.json not found at {config_path}"


def test_db_path_is_valid_sqlite(db_path):
    assert db_path.exists()
    conn = sqlite3.connect(str(db_path))
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()
    # Core tables created by tusk init
    assert "tasks" in tables
    assert "acceptance_criteria" in tables
    assert "task_sessions" in tables


def test_db_path_accepts_argv_pattern(db_path, config_path):
    """Confirm the (db_path, config_path) argv pattern used by bin scripts works."""
    argv = [str(db_path), str(config_path)]
    assert os.path.isfile(argv[0])
    assert os.path.isfile(argv[1])
