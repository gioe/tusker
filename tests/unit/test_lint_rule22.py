"""Unit tests for rule22_issue_tasks_missing_test_criterion in tusk-lint.py.

Tests both the pass case (issue task has a test-type criterion) and the
advisory-warn case (issue task has no test-type criterion), plus the
source-repo-only guard.
"""

import importlib.util
import os
import sqlite3
import tempfile
from unittest.mock import patch

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_spec = importlib.util.spec_from_file_location(
    "tusk_lint",
    os.path.join(REPO_ROOT, "bin", "tusk-lint.py"),
)
lint = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lint)


def _make_db(tmp_dir, tasks, criteria):
    """Create a minimal SQLite DB with tasks and acceptance_criteria tables.

    tasks: list of (id, summary, task_type, status)
    criteria: list of (id, task_id, criterion_type)
    """
    db_path = os.path.join(tmp_dir, "tasks.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE tasks"
        " (id INTEGER PRIMARY KEY, summary TEXT, task_type TEXT, status TEXT)"
    )
    conn.execute(
        "CREATE TABLE acceptance_criteria"
        " (id INTEGER PRIMARY KEY, task_id INTEGER, criterion_type TEXT)"
    )
    conn.executemany("INSERT INTO tasks VALUES (?, ?, ?, ?)", tasks)
    conn.executemany("INSERT INTO acceptance_criteria VALUES (?, ?, ?)", criteria)
    conn.commit()
    conn.close()
    return db_path


def _make_guarded_root(tmp_dir):
    """Create bin/tusk stub so the source-repo guard passes."""
    bin_dir = os.path.join(tmp_dir, "bin")
    os.makedirs(bin_dir, exist_ok=True)
    tusk_stub = os.path.join(bin_dir, "tusk")
    open(tusk_stub, "w").close()
    return tmp_dir


class TestRule22NoViolations:
    def test_issue_task_with_test_criterion(self):
        """No violation when issue task has a criterion_type='test' criterion."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_guarded_root(tmp)
            db_path = _make_db(
                tmp,
                tasks=[(1, "Login crash", "issue", "In Progress")],
                criteria=[(1, 1, "test")],
            )
            with patch.object(lint, "_db_path_from_root", return_value=db_path):
                assert lint.rule22_issue_tasks_missing_test_criterion(tmp) == []

    def test_non_issue_task_without_test_criterion_not_flagged(self):
        """Rule only applies to task_type='issue'; other types are ignored."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_guarded_root(tmp)
            db_path = _make_db(
                tmp,
                tasks=[(1, "Add dark mode", "feature", "In Progress")],
                criteria=[],
            )
            with patch.object(lint, "_db_path_from_root", return_value=db_path):
                assert lint.rule22_issue_tasks_missing_test_criterion(tmp) == []

    def test_done_issue_task_not_flagged(self):
        """Closed (Done) issue tasks are excluded from the check."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_guarded_root(tmp)
            db_path = _make_db(
                tmp,
                tasks=[(1, "Old bug", "issue", "Done")],
                criteria=[],
            )
            with patch.object(lint, "_db_path_from_root", return_value=db_path):
                assert lint.rule22_issue_tasks_missing_test_criterion(tmp) == []

    def test_no_bin_tusk_returns_empty(self):
        """Returns [] in target projects where bin/tusk shell script is absent."""
        with tempfile.TemporaryDirectory() as tmp:
            # No bin/tusk created — guard should short-circuit
            assert lint.rule22_issue_tasks_missing_test_criterion(tmp) == []

    def test_db_unavailable_returns_empty(self):
        """Returns [] gracefully when the DB cannot be found."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_guarded_root(tmp)
            with patch.object(lint, "_db_path_from_root", return_value=None):
                assert lint.rule22_issue_tasks_missing_test_criterion(tmp) == []


class TestRule22Violations:
    def test_issue_task_with_no_criteria_flagged(self):
        """Issue task with zero criteria triggers an advisory violation."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_guarded_root(tmp)
            db_path = _make_db(
                tmp,
                tasks=[(42, "Auth crash on logout", "issue", "In Progress")],
                criteria=[],
            )
            with patch.object(lint, "_db_path_from_root", return_value=db_path):
                violations = lint.rule22_issue_tasks_missing_test_criterion(tmp)
        assert len(violations) == 1
        assert "TASK-42" in violations[0]
        assert "Auth crash on logout" in violations[0]

    def test_issue_task_with_only_manual_criterion_flagged(self):
        """Issue task whose only criterion is 'manual' type still triggers violation."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_guarded_root(tmp)
            db_path = _make_db(
                tmp,
                tasks=[(10, "Widget breaks", "issue", "To Do")],
                criteria=[(1, 10, "manual")],
            )
            with patch.object(lint, "_db_path_from_root", return_value=db_path):
                violations = lint.rule22_issue_tasks_missing_test_criterion(tmp)
        assert len(violations) == 1
        assert "TASK-10" in violations[0]

    def test_multiple_offending_tasks_all_flagged(self):
        """Each issue task missing a test criterion produces its own violation."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_guarded_root(tmp)
            db_path = _make_db(
                tmp,
                tasks=[
                    (1, "Bug A", "issue", "In Progress"),
                    (2, "Bug B", "issue", "To Do"),
                ],
                criteria=[],
            )
            with patch.object(lint, "_db_path_from_root", return_value=db_path):
                violations = lint.rule22_issue_tasks_missing_test_criterion(tmp)
        assert len(violations) == 2
        combined = " ".join(violations)
        assert "TASK-1" in combined
        assert "TASK-2" in combined

    def test_mixed_tasks_only_offenders_flagged(self):
        """Only the issue task without a test criterion is flagged, not compliant ones."""
        with tempfile.TemporaryDirectory() as tmp:
            _make_guarded_root(tmp)
            db_path = _make_db(
                tmp,
                tasks=[
                    (1, "Bug with test", "issue", "In Progress"),
                    (2, "Bug without test", "issue", "In Progress"),
                ],
                criteria=[(1, 1, "test")],
            )
            with patch.object(lint, "_db_path_from_root", return_value=db_path):
                violations = lint.rule22_issue_tasks_missing_test_criterion(tmp)
        assert len(violations) == 1
        assert "TASK-2" in violations[0]
        assert "TASK-1" not in violations[0]
