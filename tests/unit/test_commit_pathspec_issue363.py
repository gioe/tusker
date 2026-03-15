"""Unit tests for tusk-commit.py pathspec error for valid modified files (GitHub Issue #363).

Root cause: on macOS, when caller_cwd and repo_root share the same filesystem
location but differ in case (e.g. /Users/foo/Desktop vs /Users/foo/desktop),
os.path.relpath(abs_path_cwd, repo_root) produces '../../Desktop/...' because
it is a byte-exact string comparison.  git add then rejects this path with a
pathspec error (exit 3) even though the file is clearly modified (M in git status).

The fix is _make_relative(), which strips the repo_root prefix case-insensitively
on Darwin instead of using os.path.relpath.
"""

import importlib.util
import os
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COMMIT_SCRIPT = os.path.join(REPO_ROOT, "bin", "tusk-commit.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("tusk_commit", COMMIT_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_completed(returncode, stdout="", stderr=""):
    r = MagicMock(spec=subprocess.CompletedProcess)
    r.returncode = returncode
    r.stdout = stdout
    r.stderr = stderr
    return r


class TestMakeRelative:
    """Unit tests for the _make_relative helper."""

    def test_same_case_falls_through_to_relpath(self, tmp_path):
        """When paths share the same case, _make_relative behaves like relpath."""
        mod = _load_module()
        repo_root = str(tmp_path)
        abs_path = os.path.join(repo_root, "apps", "web", "foo.tsx")
        result = mod._make_relative(abs_path, repo_root)
        assert result == os.path.relpath(abs_path, repo_root)
        assert not result.startswith("..")

    @pytest.mark.skipif(sys.platform != "darwin", reason="tests macOS case-insensitive path logic")
    def test_case_mismatch_strips_prefix_correctly(self, tmp_path):
        """On macOS, case-differing prefix is stripped without producing '../' components."""
        mod = _load_module()
        canonical_root = str(tmp_path)
        lowercase_root = canonical_root.lower()

        abs_path = os.path.join(canonical_root, "apps", "web", "foo.tsx")
        result = mod._make_relative(abs_path, lowercase_root)

        assert not result.startswith("..")
        assert result == os.path.join("apps", "web", "foo.tsx")

    @pytest.mark.skipif(sys.platform != "darwin", reason="tests macOS case-insensitive path logic")
    def test_uppercase_cwd_prefix_lowercase_repo_root(self, tmp_path):
        """Desktop vs desktop prefix mismatch (exact Issue #363 scenario) resolves correctly."""
        mod = _load_module()
        # Simulate: canonical path has uppercase component, repo_root has lowercase
        canonical_root = str(tmp_path)
        # Uppercase the last component to simulate Desktop vs desktop
        parts = canonical_root.rsplit("/", 1)
        uppercase_root = parts[0] + "/" + parts[1].upper() if len(parts) == 2 else canonical_root.upper()

        abs_path = os.path.join(uppercase_root, "apps", "web", "ui", "YouTubeIcon.tsx")
        result = mod._make_relative(abs_path, canonical_root)

        assert not result.startswith("..")
        assert "YouTubeIcon.tsx" in result


class TestPathspecCaseMismatchRegression:
    """Regression for GitHub Issue #363: tusk commit exits code 3 (pathspec error)
    for valid modified files when caller_cwd and repo_root differ in case on macOS."""

    @pytest.mark.skipif(sys.platform != "darwin", reason="tests macOS case-insensitive FS behaviour")
    def test_commit_succeeds_when_cwd_has_different_case_than_repo_root(self, tmp_path, capsys):
        """tusk commit exits 0 when caller_cwd and repo_root differ only in case.

        Exact Issue #363 scenario:
          - repo_root stored as lowercase (as git may return it)
          - caller CWD uses canonical macOS case (e.g. Desktop vs desktop)
          - file passed is valid and modified (M status)
          - previously: git add received '../../Desktop/.../file.tsx' → exit 3
          - after fix:  git add receives 'apps/web/file.tsx' → exit 0
        """
        mod = _load_module()

        # Create the file under tmp_path (canonical case).
        target = tmp_path / "apps" / "web" / "ui" / "YouTubeIcon.tsx"
        target.parent.mkdir(parents=True)
        target.write_text("// component")

        canonical_root = str(tmp_path)
        lowercase_root = canonical_root.lower()

        # argv[0] = lowercase repo_root (as git may return); file path uses canonical case.
        config = tmp_path / "config.json"
        config.write_text("{}")
        argv = [lowercase_root, str(config), "288", "add icons",
                "apps/web/ui/YouTubeIcon.tsx"]

        captured_add_args = []

        def fake_run(args, **kwargs):
            if args[:2] == ["git", "add"]:
                captured_add_args.extend(args[2:])
                return _make_completed(0)
            if args[:2] == ["git", "rev-parse"]:
                return _make_completed(0, stdout="abc123\n")
            if args[:2] == ["git", "commit"]:
                return _make_completed(0, stdout="[main abc123] commit")
            return _make_completed(0)

        # caller_cwd uses canonical (uppercase) path — this is the bug trigger.
        with patch("subprocess.run", side_effect=fake_run), \
             patch("os.getcwd", return_value=canonical_root):
            rc = mod.main(argv)

        assert rc == 0, capsys.readouterr().err
        assert captured_add_args[0] == "--"
        # The path passed to git add must be simple and relative — no '..' components.
        git_add_path = captured_add_args[1]
        assert not git_add_path.startswith(".."), (
            f"git add received a path with '..' components: {git_add_path!r}\n"
            "This would be rejected by git as a pathspec error (Issue #363)."
        )
        assert "YouTubeIcon.tsx" in git_add_path

    @pytest.mark.skipif(sys.platform != "darwin", reason="tests macOS case-insensitive FS behaviour")
    def test_commit_succeeds_for_multiple_files_with_cwd_case_mismatch(self, tmp_path, capsys):
        """All file paths resolve correctly when multiple files are staged with CWD case mismatch."""
        mod = _load_module()

        for name in ["YouTubeIcon.tsx", "WebIcon.tsx"]:
            f = tmp_path / "apps" / "web" / "ui" / "components" / "icons" / name
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("// icon")

        canonical_root = str(tmp_path)
        lowercase_root = canonical_root.lower()

        config = tmp_path / "config.json"
        config.write_text("{}")
        argv = [
            lowercase_root, str(config), "288", "add icons",
            "apps/web/ui/components/icons/YouTubeIcon.tsx",
            "apps/web/ui/components/icons/WebIcon.tsx",
        ]

        captured_add_args = []

        def fake_run(args, **kwargs):
            if args[:2] == ["git", "add"]:
                captured_add_args.extend(args[2:])
                return _make_completed(0)
            if args[:2] == ["git", "rev-parse"]:
                return _make_completed(0, stdout="abc123\n")
            if args[:2] == ["git", "commit"]:
                return _make_completed(0, stdout="[main abc123] commit")
            return _make_completed(0)

        with patch("subprocess.run", side_effect=fake_run), \
             patch("os.getcwd", return_value=canonical_root):
            rc = mod.main(argv)

        assert rc == 0, capsys.readouterr().err
        paths_to_git = captured_add_args[1:]  # skip '--'
        for p in paths_to_git:
            assert not p.startswith(".."), f"git add received bad path: {p!r}"
