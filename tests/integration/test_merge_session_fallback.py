"""Regression tests for tusk-merge session fallback (TASK-524 / issue #321).

When --session <id> is given but that session does not exist (or belongs to a
different task), tusk merge should emit a warning and fall back to
auto-detecting an open session for the task — rather than aborting the merge.

These tests exercise _autodetect_session() directly (no git operations needed)
and verify the DB-validation logic that drives the fallback.
"""

import importlib.util
import io
import os
import sqlite3
from contextlib import redirect_stderr

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        name,
        os.path.join(REPO_ROOT, "bin", f"{name}.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tusk_merge = _load("tusk-merge")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _insert_task(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        "INSERT INTO tasks (summary, status, task_type, priority, complexity, priority_score)"
        " VALUES ('test task', 'In Progress', 'feature', 'Medium', 'S', 50)"
    )
    conn.commit()
    return cur.lastrowid


def _insert_session(conn: sqlite3.Connection, task_id: int, *, closed: bool = False) -> int:
    if closed:
        cur = conn.execute(
            "INSERT INTO task_sessions (task_id, started_at, ended_at)"
            " VALUES (?, datetime('now', '-1 hour'), datetime('now'))",
            (task_id,),
        )
    else:
        cur = conn.execute(
            "INSERT INTO task_sessions (task_id, started_at) VALUES (?, datetime('now'))",
            (task_id,),
        )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# _autodetect_session tests
# ---------------------------------------------------------------------------

class TestAutodetectSession:

    def test_returns_open_session(self, db_path, config_path):
        """Returns the single open session for the task."""
        conn = sqlite3.connect(str(db_path))
        try:
            task_id = _insert_task(conn)
            session_id = _insert_session(conn, task_id)
        finally:
            conn.close()

        err_buf = io.StringIO()
        with redirect_stderr(err_buf):
            resolved, err_code = tusk_merge._autodetect_session(str(db_path), task_id, "tusk")

        assert err_code is None
        assert resolved == session_id
        assert "Auto-detected" in err_buf.getvalue()

    def test_falls_back_to_closed_session_when_no_open(self, db_path, config_path):
        """Falls back to the most-recent closed session with a warning."""
        conn = sqlite3.connect(str(db_path))
        try:
            task_id = _insert_task(conn)
            closed_id = _insert_session(conn, task_id, closed=True)
        finally:
            conn.close()

        err_buf = io.StringIO()
        with redirect_stderr(err_buf):
            resolved, err_code = tusk_merge._autodetect_session(str(db_path), task_id, "tusk")

        assert err_code is None
        assert resolved == closed_id
        assert "falling back to last closed session" in err_buf.getvalue()

    def test_error_when_no_sessions_and_no_branch(self, db_path, config_path):
        """Returns an error when no sessions exist and no feature branch is found."""
        conn = sqlite3.connect(str(db_path))
        try:
            task_id = _insert_task(conn)
        finally:
            conn.close()

        err_buf = io.StringIO()
        with redirect_stderr(err_buf):
            resolved, err_code = tusk_merge._autodetect_session(str(db_path), task_id, "tusk")

        assert err_code is not None
        assert resolved is None
        assert "No session found" in err_buf.getvalue()


# ---------------------------------------------------------------------------
# Session validation / fallback regression test (TASK-524 / issue #321)
# ---------------------------------------------------------------------------

class TestSessionValidationFallback:

    def _validate_session(self, db_path, task_id, session_id) -> bool:
        """Return True if session_id is open and belongs to task_id."""
        conn = tusk_merge.get_connection(str(db_path))
        try:
            row = conn.execute(
                "SELECT id FROM task_sessions WHERE id = ? AND task_id = ? AND ended_at IS NULL",
                (session_id, task_id),
            ).fetchone()
        finally:
            conn.close()
        return row is not None

    def test_bogus_session_id_not_valid(self, db_path, config_path):
        """A non-existent session ID fails validation (returns False)."""
        conn = sqlite3.connect(str(db_path))
        try:
            task_id = _insert_task(conn)
        finally:
            conn.close()

        assert not self._validate_session(db_path, task_id, 99999)

    def test_valid_session_passes_validation(self, db_path, config_path):
        """An existing open session for the task passes validation."""
        conn = sqlite3.connect(str(db_path))
        try:
            task_id = _insert_task(conn)
            session_id = _insert_session(conn, task_id)
        finally:
            conn.close()

        assert self._validate_session(db_path, task_id, session_id)

    def test_closed_session_fails_validation(self, db_path, config_path):
        """A closed session fails the open-session validation."""
        conn = sqlite3.connect(str(db_path))
        try:
            task_id = _insert_task(conn)
            session_id = _insert_session(conn, task_id, closed=True)
        finally:
            conn.close()

        assert not self._validate_session(db_path, task_id, session_id)

    def test_fallback_finds_open_session_when_explicit_id_missing(self, db_path, config_path):
        """Regression for issue #321: bogus --session ID → fallback returns real open session.

        Simulates the merge code path: explicit session_id fails validation,
        session_id is set to None, _autodetect_session() finds the real session.
        """
        conn = sqlite3.connect(str(db_path))
        try:
            task_id = _insert_task(conn)
            real_session_id = _insert_session(conn, task_id)
        finally:
            conn.close()

        bogus_session_id = 99999

        # Step 1: validation rejects the bogus session
        assert not self._validate_session(db_path, task_id, bogus_session_id)

        # Step 2: fallback to auto-detect — must find the real open session
        err_buf = io.StringIO()
        with redirect_stderr(err_buf):
            resolved, err_code = tusk_merge._autodetect_session(str(db_path), task_id, "tusk")

        assert err_code is None
        assert resolved == real_session_id

    def test_session_belonging_to_different_task_fails_validation(self, db_path, config_path):
        """A session from a different task is rejected by the task-scoped validation."""
        conn = sqlite3.connect(str(db_path))
        try:
            task_a = _insert_task(conn)
            task_b = _insert_task(conn)
            session_for_b = _insert_session(conn, task_b)
        finally:
            conn.close()

        # session_for_b does not belong to task_a
        assert not self._validate_session(db_path, task_a, session_for_b)
