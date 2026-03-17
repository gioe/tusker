"""Unit tests for tusk-commit.py pathspec error for files in symlinked directories (GitHub Issue #365).

Root cause: when a path component is a symlink (e.g. apps/web -> packages/web),
os.path.realpath() resolves the symlink, producing packages/web/prisma/schema.prisma.
git add then rejects this path with a pathspec error (exit 3) because git tracks the
file under the symlinked path (apps/web/prisma/schema.prisma), not the target path.
Manual `git add apps/web/prisma/schema.prisma` succeeds because it uses the original path.

The fix: use _make_relative(abs_path, repo_root) rather than _make_relative(real_abs, real_repo_root)
for the resolved path stored in resolved_files. realpath is kept only for the _escapes_root check.
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


class TestSymlinkPathResolution:
    """Unit tests for _make_relative with symlinked directory components."""

    @pytest.mark.skipif(sys.platform == "win32", reason="symlinks behave differently on Windows")
    def test_make_relative_does_not_resolve_symlinks(self, tmp_path):
        """_make_relative(abs_path, repo_root) preserves symlink names in the result."""
        mod = _load_module()

        # Create target directory and file
        target_dir = tmp_path / "packages" / "web" / "prisma"
        target_dir.mkdir(parents=True)
        (target_dir / "schema.prisma").write_text("// prisma schema")

        # Create symlink: apps/web -> packages/web
        apps_dir = tmp_path / "apps"
        apps_dir.mkdir()
        (apps_dir / "web").symlink_to(tmp_path / "packages" / "web")

        repo_root = str(tmp_path)
        # abs_path uses the symlinked path (as the user would type it)
        abs_path = os.path.normpath(os.path.join(repo_root, "apps", "web", "prisma", "schema.prisma"))

        result = mod._make_relative(abs_path, repo_root)

        # Must preserve the symlink name 'apps/web', not resolve to 'packages/web'
        assert result == os.path.join("apps", "web", "prisma", "schema.prisma"), (
            f"Expected symlinked path but got: {result!r}\n"
            "git add must receive the symlinked path, not the resolved target path."
        )
        assert "packages" not in result, (
            f"Symlink was resolved — git add would fail with pathspec error: {result!r}"
        )


class TestSymlinkPathspecRegression:
    """Regression for GitHub Issue #365: tusk commit exits code 3 (pathspec error)
    for files in symlinked directories (e.g. .prisma files in apps/web -> packages/web)."""

    @pytest.mark.skipif(sys.platform == "win32", reason="symlinks behave differently on Windows")
    def test_commit_succeeds_for_file_in_symlinked_directory(self, tmp_path, capsys):
        """tusk commit exits 0 and passes the symlinked path to git add.

        Exact Issue #365 scenario:
          - apps/web is a symlink to packages/web
          - user runs: tusk commit <id> "<msg>" apps/web/prisma/schema.prisma
          - previously: realpath resolved symlink -> git add got packages/web/... -> exit 3
          - after fix:  git add receives apps/web/prisma/schema.prisma -> exit 0
        """
        mod = _load_module()

        # Create target and file
        target_dir = tmp_path / "packages" / "web" / "prisma"
        target_dir.mkdir(parents=True)
        (target_dir / "schema.prisma").write_text("// prisma schema")

        # Create symlink: apps/web -> packages/web
        apps_dir = tmp_path / "apps"
        apps_dir.mkdir()
        (apps_dir / "web").symlink_to(tmp_path / "packages" / "web")

        repo_root = str(tmp_path)
        config = tmp_path / "config.json"
        config.write_text("{}")

        argv = [repo_root, str(config), "365", "update prisma schema",
                "apps/web/prisma/schema.prisma"]

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
             patch("os.getcwd", return_value=repo_root):
            rc = mod.main(argv)

        assert rc == 0, capsys.readouterr().err
        assert captured_add_args[0] == "--"
        git_add_path = captured_add_args[1]
        # Must use the symlinked path, not the resolved target path
        assert "packages" not in git_add_path, (
            f"Symlink was resolved in path passed to git add: {git_add_path!r}\n"
            "git add would fail with pathspec error (Issue #365)."
        )
        assert git_add_path == os.path.join("apps", "web", "prisma", "schema.prisma"), (
            f"Expected symlinked path but got: {git_add_path!r}"
        )

    @pytest.mark.skipif(sys.platform == "win32", reason="symlinks behave differently on Windows")
    def test_escape_check_still_rejects_symlinks_pointing_outside_repo(self, tmp_path, capsys):
        """Files whose symlink target escapes the repo root are still rejected."""
        mod = _load_module()

        # Create a file outside the repo root
        outside = tmp_path.parent / "outside_repo" / "secret.txt"
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_text("secret")

        # Create a symlink inside the repo pointing outside
        repo_root = tmp_path / "myrepo"
        repo_root.mkdir()
        (repo_root / "escape_link.txt").symlink_to(outside)

        config = repo_root / "config.json"
        config.write_text("{}")

        argv = [str(repo_root), str(config), "365", "escape attempt", "escape_link.txt"]

        with patch("subprocess.run", return_value=_make_completed(0)), \
             patch("os.getcwd", return_value=str(repo_root)):
            rc = mod.main(argv)

        # Should fail with exit 3 — the symlink target escapes the repo root
        assert rc == 3, (
            "Expected exit 3 (escape check) for a symlink pointing outside the repo root"
        )
