"""Unit tests for domain-aware test command selection in tusk-commit.py.

Verifies that load_test_command prefers domain_test_commands[domain] over the
global test_command when the task has a matching domain, and falls back correctly
when no domain is set or no matching entry exists.
"""

import importlib.util
import json
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COMMIT_SCRIPT = os.path.join(REPO_ROOT, "bin", "tusk-commit.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("tusk_commit", COMMIT_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestLoadTestCommand:
    def _write_config(self, tmp_path, data: dict) -> str:
        p = tmp_path / "config.json"
        p.write_text(json.dumps(data))
        return str(p)

    def test_domain_match_returns_domain_command(self, tmp_path):
        """When domain matches a key in domain_test_commands, return that command."""
        mod = _load_module()
        config_path = self._write_config(tmp_path, {
            "test_command": "pytest tests/",
            "domain_test_commands": {"scraper": "cd apps/scraper && python3 -m pytest"},
        })
        assert mod.load_test_command(config_path, "scraper") == "cd apps/scraper && python3 -m pytest"

    def test_no_domain_falls_back_to_global(self, tmp_path):
        """When domain is empty string, return the global test_command."""
        mod = _load_module()
        config_path = self._write_config(tmp_path, {
            "test_command": "pytest tests/",
            "domain_test_commands": {"scraper": "cd apps/scraper && python3 -m pytest"},
        })
        assert mod.load_test_command(config_path, "") == "pytest tests/"

    def test_domain_not_in_domain_test_commands_falls_back_to_global(self, tmp_path):
        """When domain has no entry in domain_test_commands, return global test_command."""
        mod = _load_module()
        config_path = self._write_config(tmp_path, {
            "test_command": "pytest tests/",
            "domain_test_commands": {"scraper": "cd apps/scraper && python3 -m pytest"},
        })
        assert mod.load_test_command(config_path, "cli") == "pytest tests/"

    def test_no_domain_test_commands_key_falls_back_to_global(self, tmp_path):
        """When domain_test_commands is absent from config, return global test_command."""
        mod = _load_module()
        config_path = self._write_config(tmp_path, {"test_command": "pytest tests/"})
        assert mod.load_test_command(config_path, "cli") == "pytest tests/"

    def test_domain_command_empty_string_falls_back_to_global(self, tmp_path):
        """When domain_test_commands[domain] is an empty string, fall back to global."""
        mod = _load_module()
        config_path = self._write_config(tmp_path, {
            "test_command": "pytest tests/",
            "domain_test_commands": {"cli": ""},
        })
        assert mod.load_test_command(config_path, "cli") == "pytest tests/"
