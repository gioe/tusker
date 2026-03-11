"""Unit tests for rule3_hardcoded_db_path in tusk-lint.py.

Covers comment filtering, docstring state machine (open/content/close lines),
actual violations, and mixed-delimiter edge cases.
"""

import importlib.util
import os
import tempfile

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_spec = importlib.util.spec_from_file_location(
    "tusk_lint",
    os.path.join(REPO_ROOT, "bin", "tusk-lint.py"),
)
lint = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lint)


def run_rule3(source: str) -> list[str]:
    """Write *source* to a temporary skills/check.py and run rule3 on the temp root."""
    with tempfile.TemporaryDirectory() as root:
        skills_dir = os.path.join(root, "skills")
        os.makedirs(skills_dir)
        py_file = os.path.join(skills_dir, "check.py")
        with open(py_file, "w", encoding="utf-8") as f:
            f.write(source)
        return lint.rule3_hardcoded_db_path(root)


# ── Comment lines ──────────────────────────────────────────────────────


class TestCommentLines:
    def test_comment_line_no_violation(self):
        source = "# db_path = 'tusk/tasks.db'\n"
        assert run_rule3(source) == []

    def test_indented_comment_no_violation(self):
        source = "    # db = 'tusk/tasks.db'\n"
        assert run_rule3(source) == []

    def test_inline_comment_after_code_still_flags(self):
        # The path appears in the code portion, not just a trailing comment
        source = "db = 'tusk/tasks.db'  # set path\n"
        violations = run_rule3(source)
        assert len(violations) == 1

    def test_bare_comment_keyword_only_no_violation(self):
        # Line is a comment even though it contains the path string
        source = "# See tusk/tasks.db for schema\n"
        assert run_rule3(source) == []


# ── Docstring state machine ────────────────────────────────────────────


class TestDocstringLines:
    def test_opening_docstring_line_skipped(self):
        # The triple-quote opens AND the path appears on the same line
        source = '"""tusk/tasks.db is the database path\n"""\n'
        assert run_rule3(source) == []

    def test_content_line_inside_docstring_skipped(self):
        source = '"""\ntusk/tasks.db is documented here\n"""\n'
        assert run_rule3(source) == []

    def test_closing_docstring_line_skipped(self):
        source = '"""\nSome docstring\ntusk/tasks.db"""\n'
        assert run_rule3(source) == []

    def test_code_after_docstring_flagged(self):
        source = '"""\nA docstring.\n"""\ndb = "tusk/tasks.db"\n'
        violations = run_rule3(source)
        assert len(violations) == 1

    def test_single_quoted_docstring_open_skipped(self):
        source = "'''tusk/tasks.db path info\n'''\n"
        assert run_rule3(source) == []

    def test_single_quoted_docstring_content_skipped(self):
        source = "'''\ntusk/tasks.db\n'''\n"
        assert run_rule3(source) == []

    def test_multiple_docstrings_code_between_flagged(self):
        # Path between two docstrings — should fire
        source = '"""\nfirst docstring\n"""\ndb = "tusk/tasks.db"\n"""\nsecond\n"""\n'
        violations = run_rule3(source)
        assert len(violations) == 1

    def test_path_only_inside_docstring_no_violation(self):
        source = '"""\nThis function writes to tusk/tasks.db.\n"""\ndef foo(): pass\n'
        assert run_rule3(source) == []


# ── Actual violations ──────────────────────────────────────────────────


class TestActualViolations:
    def test_plain_assignment_flagged(self):
        source = 'db_path = "tusk/tasks.db"\n'
        violations = run_rule3(source)
        assert len(violations) == 1

    def test_single_quoted_assignment_flagged(self):
        source = "db = 'tusk/tasks.db'\n"
        violations = run_rule3(source)
        assert len(violations) == 1

    def test_multiple_violations_all_reported(self):
        source = 'a = "tusk/tasks.db"\nb = "tusk/tasks.db"\n'
        violations = run_rule3(source)
        assert len(violations) == 2

    def test_violation_includes_filename_and_line(self):
        source = 'x = "tusk/tasks.db"\n'
        violations = run_rule3(source)
        assert len(violations) == 1
        assert "check.py" in violations[0]
        assert "tusk/tasks.db" in violations[0]


# ── Mixed-delimiter edge cases ─────────────────────────────────────────


class TestMixedDelimiters:
    def test_closing_double_does_not_open_single_docstring(self):
        # Closing """ should not toggle ''' state; code after should still fire.
        source = '"""\ndoc\n"""\ndb = "tusk/tasks.db"\n'
        violations = run_rule3(source)
        assert len(violations) == 1

    def test_closing_single_does_not_open_double_docstring(self):
        source = "'''\ndoc\n'''\ndb = 'tusk/tasks.db'\n"
        violations = run_rule3(source)
        assert len(violations) == 1

    def test_double_quotes_inside_single_quoted_docstring_skipped(self):
        # """ appearing inside a '''-delimited docstring is content, not a new docstring
        source = "'''\nSome \"\"\" text tusk/tasks.db\n'''\n"
        assert run_rule3(source) == []

    def test_single_quotes_inside_double_quoted_docstring_skipped(self):
        source = "\"\"\"\nSome ''' text tusk/tasks.db\n\"\"\"\n"
        assert run_rule3(source) == []
