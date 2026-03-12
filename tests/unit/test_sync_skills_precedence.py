"""Unit tests for tusk-sync-skills.py precedence: internal overrides public."""

import importlib.util
import os
import tempfile
from unittest.mock import patch

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_spec = importlib.util.spec_from_file_location(
    "tusk_sync_skills",
    os.path.join(REPO_ROOT, "bin", "tusk-sync-skills.py"),
)
sync_skills = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sync_skills)


def run_sync(tmp_root: str) -> None:
    """Run sync_skills.main() with get_repo_root patched to return tmp_root."""
    with patch.object(sync_skills, "get_repo_root", return_value=tmp_root):
        sync_skills.main()


def setup_skill(base_dir: str, name: str) -> str:
    """Create a minimal skill directory under base_dir/<name>/ and return its path."""
    skill_dir = os.path.join(base_dir, name)
    os.makedirs(skill_dir, exist_ok=True)
    with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
        f.write(f"# {name}\n")
    return skill_dir


class TestInternalOverridesPublic:
    def test_internal_wins_when_both_exist(self):
        """Symlink resolves to skills-internal/ when the same name is in both dirs."""
        with tempfile.TemporaryDirectory() as tmp:
            public_dir = os.path.join(tmp, "skills")
            internal_dir = os.path.join(tmp, "skills-internal")
            claude_skills = os.path.join(tmp, ".claude", "skills")
            os.makedirs(claude_skills, exist_ok=True)

            setup_skill(public_dir, "my-skill")
            setup_skill(internal_dir, "my-skill")

            run_sync(tmp)

            link = os.path.join(claude_skills, "my-skill")
            assert os.path.islink(link), "symlink should exist for my-skill"
            target = os.readlink(link)
            assert "skills-internal" in target, (
                f"Expected symlink to point into skills-internal/, got: {target}"
            )
            assert "skills/" not in target.replace("skills-internal", ""), (
                f"Symlink should NOT point to public skills/, got: {target}"
            )

    def test_public_only_skill_is_linked(self):
        """A skill that exists only in skills/ is still linked."""
        with tempfile.TemporaryDirectory() as tmp:
            public_dir = os.path.join(tmp, "skills")
            internal_dir = os.path.join(tmp, "skills-internal")
            claude_skills = os.path.join(tmp, ".claude", "skills")
            os.makedirs(claude_skills, exist_ok=True)

            setup_skill(public_dir, "public-only")
            setup_skill(internal_dir, "other-internal")

            run_sync(tmp)

            link = os.path.join(claude_skills, "public-only")
            assert os.path.islink(link)
            assert "skills/" in os.readlink(link)

    def test_internal_only_skill_is_linked(self):
        """A skill that exists only in skills-internal/ is linked."""
        with tempfile.TemporaryDirectory() as tmp:
            internal_dir = os.path.join(tmp, "skills-internal")
            claude_skills = os.path.join(tmp, ".claude", "skills")
            os.makedirs(claude_skills, exist_ok=True)

            setup_skill(internal_dir, "internal-only")

            run_sync(tmp)

            link = os.path.join(claude_skills, "internal-only")
            assert os.path.islink(link)
            assert "skills-internal" in os.readlink(link)

    def test_only_one_symlink_created_for_overlapping_name(self):
        """Exactly one symlink is created when a skill name exists in both dirs."""
        with tempfile.TemporaryDirectory() as tmp:
            public_dir = os.path.join(tmp, "skills")
            internal_dir = os.path.join(tmp, "skills-internal")
            claude_skills = os.path.join(tmp, ".claude", "skills")
            os.makedirs(claude_skills, exist_ok=True)

            setup_skill(public_dir, "shared-skill")
            setup_skill(internal_dir, "shared-skill")

            run_sync(tmp)

            entries = os.listdir(claude_skills)
            assert entries.count("shared-skill") == 1
