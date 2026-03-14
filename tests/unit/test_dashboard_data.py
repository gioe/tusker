"""Unit tests for tusk-dashboard-data.py data-layer computations.

Imports tusk-dashboard-data.py via importlib (hyphenated filename requires it).
Builds an in-memory SQLite DB with the minimal tusk schema and seeds controlled
data to assert computed values without touching the real tusk database.
"""

import importlib.util
import os
import sqlite3

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Load module under test
# ---------------------------------------------------------------------------

def _load_dashboard_data():
    path = os.path.join(REPO_ROOT, "bin", "tusk-dashboard-data.py")
    spec = importlib.util.spec_from_file_location("tusk_dashboard_data", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dashboard_data = _load_dashboard_data()


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    summary TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'To Do',
    priority TEXT DEFAULT 'Medium',
    domain TEXT,
    assignee TEXT,
    task_type TEXT,
    priority_score INTEGER DEFAULT 0,
    expires_at TEXT,
    closed_reason TEXT,
    complexity TEXT,
    is_deferred INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    started_at TEXT,
    closed_at TEXT
);

CREATE TABLE task_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    duration_seconds INTEGER,
    cost_dollars REAL,
    tokens_in INTEGER,
    tokens_out INTEGER,
    lines_added INTEGER,
    lines_removed INTEGER,
    model TEXT,
    agent_name TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

CREATE VIEW task_metrics AS
SELECT t.*,
    COUNT(s.id) as session_count,
    SUM(s.duration_seconds) as total_duration_seconds,
    SUM(s.cost_dollars) as total_cost,
    SUM(s.tokens_in) as total_tokens_in,
    SUM(s.tokens_out) as total_tokens_out,
    SUM(s.lines_added) as total_lines_added,
    SUM(s.lines_removed) as total_lines_removed
FROM tasks t
LEFT JOIN task_sessions s ON t.id = s.task_id
GROUP BY t.id;
"""


def _make_conn():
    """Create an in-memory SQLite connection with the minimal tusk schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------


class TestModuleLoading:
    def test_module_loads_successfully(self):
        """tusk-dashboard-data.py can be imported via importlib."""
        mod = _load_dashboard_data()
        assert mod is not None

    def test_fetch_functions_are_callable(self):
        mod = _load_dashboard_data()
        assert callable(mod.fetch_task_metrics)
        assert callable(mod.fetch_kpi_data)
        assert callable(mod.fetch_complexity_metrics)


# ---------------------------------------------------------------------------
# duration_in_status_seconds: To Do branch
# ---------------------------------------------------------------------------


class TestDurationToDoStatus:
    def test_todo_task_duration_is_positive(self):
        """To Do tasks: duration = now - created_at (always > 0 for past creation)."""
        conn = _make_conn()
        conn.execute(
            "INSERT INTO tasks (summary, status, created_at) VALUES (?, ?, ?)",
            ("todo task", "To Do", "2026-01-01 00:00:00"),
        )
        conn.commit()

        rows = dashboard_data.fetch_task_metrics(conn)
        assert len(rows) == 1
        assert rows[0]["duration_in_status_seconds"] > 0

    def test_todo_task_duration_uses_created_at(self):
        """To Do: duration grows with older created_at, not started_at."""
        conn = _make_conn()
        # Two tasks with different creation times
        conn.execute(
            "INSERT INTO tasks (summary, status, created_at) VALUES (?, ?, ?)",
            ("older", "To Do", "2025-01-01 00:00:00"),
        )
        conn.execute(
            "INSERT INTO tasks (summary, status, created_at) VALUES (?, ?, ?)",
            ("newer", "To Do", "2026-01-01 00:00:00"),
        )
        conn.commit()

        rows = dashboard_data.fetch_task_metrics(conn)
        durations = {r["summary"]: r["duration_in_status_seconds"] for r in rows}
        assert durations["older"] > durations["newer"]


# ---------------------------------------------------------------------------
# duration_in_status_seconds: In Progress branch (with sessions)
# ---------------------------------------------------------------------------


class TestDurationInProgressStatus:
    def test_in_progress_with_session_uses_min_started_at(self):
        """In Progress + sessions: duration = now - MIN(session.started_at)."""
        conn = _make_conn()
        conn.execute(
            "INSERT INTO tasks (id, summary, status, created_at, started_at) VALUES (?, ?, ?, ?, ?)",
            (1, "wip task", "In Progress", "2026-01-01 00:00:00", "2026-01-15 00:00:00"),
        )
        # Two sessions with different started_at; MIN should win
        conn.execute(
            "INSERT INTO task_sessions (task_id, started_at, ended_at, duration_seconds) VALUES (?, ?, ?, ?)",
            (1, "2026-01-10 00:00:00", "2026-01-10 01:00:00", 3600),
        )
        conn.execute(
            "INSERT INTO task_sessions (task_id, started_at, ended_at, duration_seconds) VALUES (?, ?, ?, ?)",
            (1, "2026-01-20 00:00:00", None, None),
        )
        conn.commit()

        rows = dashboard_data.fetch_task_metrics(conn)
        assert len(rows) == 1
        duration = rows[0]["duration_in_status_seconds"]
        # MIN session started_at is 2026-01-10; that's earlier than started_at=2026-01-15.
        # Duration should be positive and reflect the earlier session start.
        assert duration > 0
        # Verify it's anchored to session start (2026-01-10), not task.started_at (2026-01-15).
        # Duration from 2026-01-10 must exceed duration from 2026-01-15.
        days_since_session_start = (
            conn.execute(
                "SELECT CAST((julianday('now') - julianday('2026-01-10 00:00:00')) * 86400 AS INTEGER)"
            ).fetchone()[0]
        )
        days_since_task_start = (
            conn.execute(
                "SELECT CAST((julianday('now') - julianday('2026-01-15 00:00:00')) * 86400 AS INTEGER)"
            ).fetchone()[0]
        )
        assert duration >= days_since_session_start - 5  # allow ±5 s rounding
        assert duration > days_since_task_start


# ---------------------------------------------------------------------------
# duration_in_status_seconds: Done branch (with sessions)
# ---------------------------------------------------------------------------


class TestDurationDoneStatus:
    def test_done_with_sessions_uses_max_ended_at_minus_min_started_at(self):
        """Done + sessions: duration = MAX(ended_at) - MIN(started_at)."""
        conn = _make_conn()
        conn.execute(
            "INSERT INTO tasks (id, summary, status, closed_reason) VALUES (?, ?, ?, ?)",
            (1, "done task", "Done", "completed"),
        )
        conn.execute(
            "INSERT INTO task_sessions (task_id, started_at, ended_at, duration_seconds) VALUES (?, ?, ?, ?)",
            (1, "2026-01-01 00:00:00", "2026-01-01 02:00:00", 7200),
        )
        conn.execute(
            "INSERT INTO task_sessions (task_id, started_at, ended_at, duration_seconds) VALUES (?, ?, ?, ?)",
            (1, "2026-01-02 00:00:00", "2026-01-02 01:00:00", 3600),
        )
        conn.commit()

        rows = dashboard_data.fetch_task_metrics(conn)
        assert len(rows) == 1
        duration = rows[0]["duration_in_status_seconds"]
        # MAX ended_at = 2026-01-02 01:00:00, MIN started_at = 2026-01-01 00:00:00 => 25 hours = 90000 s
        expected = 90000
        assert abs(duration - expected) < 5  # allow ±5 s for rounding


# ---------------------------------------------------------------------------
# duration_in_status_seconds: In Progress fallback (no sessions)
# ---------------------------------------------------------------------------


class TestDurationInProgressFallback:
    def test_in_progress_no_sessions_uses_started_at_not_created_at(self):
        """In Progress + no sessions: fallback is task.started_at, not created_at."""
        conn = _make_conn()
        # created_at is much earlier than started_at
        conn.execute(
            "INSERT INTO tasks (id, summary, status, created_at, started_at) VALUES (?, ?, ?, ?, ?)",
            (1, "wip no session", "In Progress",
             "2026-01-01 00:00:00",   # created_at (older)
             "2026-02-01 00:00:00"),  # started_at (newer)
        )
        conn.commit()

        rows = dashboard_data.fetch_task_metrics(conn)
        assert len(rows) == 1
        duration = rows[0]["duration_in_status_seconds"]

        # duration from started_at (2026-02-01) should be smaller than from created_at (2026-01-01)
        duration_from_created = conn.execute(
            "SELECT CAST((julianday('now') - julianday('2026-01-01 00:00:00')) * 86400 AS INTEGER)"
        ).fetchone()[0]
        duration_from_started = conn.execute(
            "SELECT CAST((julianday('now') - julianday('2026-02-01 00:00:00')) * 86400 AS INTEGER)"
        ).fetchone()[0]

        assert abs(duration - duration_from_started) < 5
        assert duration < duration_from_created


# ---------------------------------------------------------------------------
# duration_in_status_seconds: Done fallback (no sessions)
# ---------------------------------------------------------------------------


class TestDurationDoneFallback:
    def test_done_no_sessions_uses_updated_at_minus_started_at(self):
        """Done + no sessions: duration = updated_at - started_at."""
        conn = _make_conn()
        conn.execute(
            "INSERT INTO tasks (id, summary, status, closed_reason, created_at, started_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                1, "done no session", "Done", "completed",
                "2026-01-01 00:00:00",  # created_at
                "2026-01-02 00:00:00",  # started_at
                "2026-01-02 03:00:00",  # updated_at  => span = 3 hours = 10800 s
            ),
        )
        conn.commit()

        rows = dashboard_data.fetch_task_metrics(conn)
        assert len(rows) == 1
        duration = rows[0]["duration_in_status_seconds"]
        # updated_at - started_at = 3 hours = 10800 s
        assert abs(duration - 10800) < 5

    def test_done_no_sessions_no_started_at_falls_back_to_created_at(self):
        """Done + no sessions + no started_at: start anchor falls back to created_at."""
        conn = _make_conn()
        conn.execute(
            "INSERT INTO tasks (id, summary, status, closed_reason, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                1, "done fallback", "Done", "completed",
                "2026-01-01 00:00:00",  # created_at (used as start fallback)
                "2026-01-01 02:00:00",  # updated_at  => span = 2 hours = 7200 s
            ),
        )
        conn.commit()

        rows = dashboard_data.fetch_task_metrics(conn)
        assert len(rows) == 1
        assert abs(rows[0]["duration_in_status_seconds"] - 7200) < 5


# ---------------------------------------------------------------------------
# total_duration_seconds aggregation
# ---------------------------------------------------------------------------


class TestTotalDurationSeconds:
    def test_total_duration_sums_session_duration_seconds(self):
        """total_duration_seconds = SUM of session.duration_seconds."""
        conn = _make_conn()
        conn.execute(
            "INSERT INTO tasks (id, summary) VALUES (?, ?)", (1, "task with sessions")
        )
        conn.execute(
            "INSERT INTO task_sessions (task_id, started_at, ended_at, duration_seconds) VALUES (?, ?, ?, ?)",
            (1, "2026-01-01 00:00:00", "2026-01-01 01:00:00", 3600),
        )
        conn.execute(
            "INSERT INTO task_sessions (task_id, started_at, ended_at, duration_seconds) VALUES (?, ?, ?, ?)",
            (1, "2026-01-02 00:00:00", "2026-01-02 00:30:00", 1800),
        )
        conn.commit()

        rows = dashboard_data.fetch_task_metrics(conn)
        assert len(rows) == 1
        assert rows[0]["total_duration_seconds"] == 5400  # 3600 + 1800

    def test_total_duration_zero_when_no_sessions(self):
        """total_duration_seconds COALESCE'd to 0 when task has no sessions."""
        conn = _make_conn()
        conn.execute("INSERT INTO tasks (id, summary) VALUES (?, ?)", (1, "no sessions"))
        conn.commit()

        rows = dashboard_data.fetch_task_metrics(conn)
        assert len(rows) == 1
        assert rows[0]["total_duration_seconds"] == 0

    def test_total_duration_across_multiple_tasks(self):
        """total_duration_seconds is per-task, not a cross-task sum."""
        conn = _make_conn()
        conn.execute("INSERT INTO tasks (id, summary) VALUES (?, ?)", (1, "task A"))
        conn.execute("INSERT INTO tasks (id, summary) VALUES (?, ?)", (2, "task B"))
        conn.execute(
            "INSERT INTO task_sessions (task_id, started_at, duration_seconds) VALUES (?, ?, ?)",
            (1, "2026-01-01 00:00:00", 1000),
        )
        conn.execute(
            "INSERT INTO task_sessions (task_id, started_at, duration_seconds) VALUES (?, ?, ?)",
            (2, "2026-01-01 00:00:00", 2000),
        )
        conn.commit()

        rows = dashboard_data.fetch_task_metrics(conn)
        by_id = {r["id"]: r for r in rows}
        assert by_id[1]["total_duration_seconds"] == 1000
        assert by_id[2]["total_duration_seconds"] == 2000


# ---------------------------------------------------------------------------
# fetch_kpi_data()
# ---------------------------------------------------------------------------


class TestFetchKpiData:
    def test_totals_match_seeded_sessions(self):
        """fetch_kpi_data() aggregates cost and tokens across all sessions."""
        conn = _make_conn()
        conn.execute("INSERT INTO tasks (id, summary) VALUES (?, ?)", (1, "t1"))
        conn.execute("INSERT INTO tasks (id, summary) VALUES (?, ?)", (2, "t2"))
        conn.execute(
            "INSERT INTO task_sessions (task_id, started_at, cost_dollars, tokens_in, tokens_out) VALUES (?, ?, ?, ?, ?)",
            (1, "2026-01-01 00:00:00", 0.10, 1000, 500),
        )
        conn.execute(
            "INSERT INTO task_sessions (task_id, started_at, cost_dollars, tokens_in, tokens_out) VALUES (?, ?, ?, ?, ?)",
            (1, "2026-01-02 00:00:00", 0.20, 2000, 1000),
        )
        conn.execute(
            "INSERT INTO task_sessions (task_id, started_at, cost_dollars, tokens_in, tokens_out) VALUES (?, ?, ?, ?, ?)",
            (2, "2026-01-03 00:00:00", 0.05, 500, 250),
        )
        conn.commit()

        kpi = dashboard_data.fetch_kpi_data(conn)

        assert abs(kpi["total_cost"] - 0.35) < 1e-9
        assert kpi["total_tokens_in"] == 3500
        assert kpi["total_tokens_out"] == 1750
        assert kpi["total_tokens"] == 5250

    def test_tasks_completed_counts_done_tasks(self):
        """fetch_kpi_data() counts only Done tasks as completed."""
        conn = _make_conn()
        conn.execute(
            "INSERT INTO tasks (id, summary, status, closed_reason) VALUES (?, ?, ?, ?)",
            (1, "done1", "Done", "completed"),
        )
        conn.execute(
            "INSERT INTO tasks (id, summary, status, closed_reason) VALUES (?, ?, ?, ?)",
            (2, "done2", "Done", "completed"),
        )
        conn.execute("INSERT INTO tasks (id, summary, status) VALUES (?, ?, ?)", (3, "wip", "In Progress"))
        conn.commit()

        kpi = dashboard_data.fetch_kpi_data(conn)
        assert kpi["tasks_completed"] == 2
        assert kpi["tasks_total"] == 3

    def test_avg_cost_per_task_correct(self):
        """avg_cost_per_task = total_cost / tasks_completed (not tasks_total)."""
        conn = _make_conn()
        conn.execute(
            "INSERT INTO tasks (id, summary, status, closed_reason) VALUES (?, ?, ?, ?)",
            (1, "done", "Done", "completed"),
        )
        conn.execute(
            "INSERT INTO task_sessions (task_id, started_at, cost_dollars) VALUES (?, ?, ?)",
            (1, "2026-01-01 00:00:00", 0.30),
        )
        conn.commit()

        kpi = dashboard_data.fetch_kpi_data(conn)
        assert abs(kpi["avg_cost_per_task"] - 0.30) < 1e-9

    def test_avg_cost_per_task_zero_when_no_completed_tasks(self):
        """avg_cost_per_task is 0 when no tasks are Done."""
        conn = _make_conn()
        conn.execute("INSERT INTO tasks (id, summary) VALUES (?, ?)", (1, "todo"))
        conn.commit()

        kpi = dashboard_data.fetch_kpi_data(conn)
        assert kpi["avg_cost_per_task"] == 0

    def test_empty_database_returns_zeros(self):
        """fetch_kpi_data() handles an empty database gracefully."""
        conn = _make_conn()
        kpi = dashboard_data.fetch_kpi_data(conn)
        assert kpi["total_cost"] == 0
        assert kpi["total_tokens_in"] == 0
        assert kpi["total_tokens_out"] == 0
        assert kpi["total_tokens"] == 0
        assert kpi["tasks_completed"] == 0
        assert kpi["tasks_total"] == 0
        assert kpi["avg_cost_per_task"] == 0


# ---------------------------------------------------------------------------
# fetch_complexity_metrics()
# ---------------------------------------------------------------------------


class TestFetchComplexityMetrics:
    def test_groups_by_complexity(self):
        """fetch_complexity_metrics() returns one row per complexity bucket."""
        conn = _make_conn()
        for i, complexity in enumerate(["XS", "S", "M"], start=1):
            conn.execute(
                "INSERT INTO tasks (id, summary, status, closed_reason, complexity) VALUES (?, ?, ?, ?, ?)",
                (i, f"task {complexity}", "Done", "completed", complexity),
            )
        conn.commit()

        rows = dashboard_data.fetch_complexity_metrics(conn)
        complexities = [r["complexity"] for r in rows]
        assert set(complexities) == {"XS", "S", "M"}

    def test_ordered_by_complexity_size(self):
        """fetch_complexity_metrics() returns rows in XS→S→M→L→XL order."""
        conn = _make_conn()
        for i, c in enumerate(["L", "XS", "M", "S", "XL"], start=1):
            conn.execute(
                "INSERT INTO tasks (id, summary, status, closed_reason, complexity) VALUES (?, ?, ?, ?, ?)",
                (i, f"task {c}", "Done", "completed", c),
            )
        conn.commit()

        rows = dashboard_data.fetch_complexity_metrics(conn)
        complexities = [r["complexity"] for r in rows]
        assert complexities == ["XS", "S", "M", "L", "XL"]

    def test_excludes_non_done_tasks(self):
        """fetch_complexity_metrics() only includes Done tasks."""
        conn = _make_conn()
        conn.execute(
            "INSERT INTO tasks (id, summary, status, closed_reason, complexity) VALUES (?, ?, ?, ?, ?)",
            (1, "done", "Done", "completed", "S"),
        )
        conn.execute(
            "INSERT INTO tasks (id, summary, status, complexity) VALUES (?, ?, ?, ?)",
            (2, "todo", "To Do", "S"),
        )
        conn.commit()

        rows = dashboard_data.fetch_complexity_metrics(conn)
        assert len(rows) == 1
        assert rows[0]["task_count"] == 1

    def test_avg_sessions_computed_correctly(self):
        """avg_sessions is the mean session_count for tasks in each complexity bucket."""
        conn = _make_conn()
        # Two M tasks: one with 1 session, one with 3 sessions → avg = 2.0
        conn.execute(
            "INSERT INTO tasks (id, summary, status, closed_reason, complexity) VALUES (?, ?, ?, ?, ?)",
            (1, "m task 1", "Done", "completed", "M"),
        )
        conn.execute(
            "INSERT INTO tasks (id, summary, status, closed_reason, complexity) VALUES (?, ?, ?, ?, ?)",
            (2, "m task 2", "Done", "completed", "M"),
        )
        conn.execute(
            "INSERT INTO task_sessions (task_id, started_at, duration_seconds, cost_dollars) VALUES (?, ?, ?, ?)",
            (1, "2026-01-01 00:00:00", 100, 0.01),
        )
        for j in range(3):
            conn.execute(
                "INSERT INTO task_sessions (task_id, started_at, duration_seconds, cost_dollars) VALUES (?, ?, ?, ?)",
                (2, f"2026-01-0{j+1} 00:00:00", 200, 0.02),
            )
        conn.commit()

        rows = dashboard_data.fetch_complexity_metrics(conn)
        m_row = next(r for r in rows if r["complexity"] == "M")
        assert m_row["avg_sessions"] == 2.0

    def test_empty_database_returns_no_rows(self):
        """fetch_complexity_metrics() returns empty list when no Done tasks exist."""
        conn = _make_conn()
        rows = dashboard_data.fetch_complexity_metrics(conn)
        assert rows == []
