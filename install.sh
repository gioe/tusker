#!/usr/bin/env bash
#
# Install tusker into a Claude Code project.
#
# Usage:
#   cd /path/to/your/project
#   /path/to/tusker/install.sh
#
# What it does:
#   1. Copies bin/tusk + support files → .claude/bin/
#   2. Copies skills/*                 → .claude/skills/*
#   3. Copies scripts/*                → scripts/*  (creates if needed)
#   4. Runs tusk init + migrate
#   5. Prints CLAUDE.md snippet to paste into your project

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Must be run from a git repo root
if ! git rev-parse --show-toplevel &>/dev/null; then
  echo "Error: Run this from a git repository root." >&2
  exit 1
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"

# Must have Claude Code initialized
if [[ ! -d "$REPO_ROOT/.claude" ]]; then
  echo "Error: No .claude/ directory found. Initialize Claude Code first." >&2
  exit 1
fi

echo "Installing tusker into $REPO_ROOT"

# ── 1. Copy bin + support files ──────────────────────────────────────
mkdir -p "$REPO_ROOT/.claude/bin"
cp "$SCRIPT_DIR/bin/tusk" "$REPO_ROOT/.claude/bin/tusk"
chmod +x "$REPO_ROOT/.claude/bin/tusk"
echo "  Installed .claude/bin/tusk"

# Copy Python scripts alongside binary (needed for $SCRIPT_DIR dispatch)
for pyfile in "$SCRIPT_DIR"/bin/tusk-*.py; do
  [[ -f "$pyfile" ]] || continue
  cp "$pyfile" "$REPO_ROOT/.claude/bin/"
  echo "  Installed .claude/bin/$(basename "$pyfile")"
done

# ── 2. Copy config, VERSION ─────────────────────────────────────────
cp "$SCRIPT_DIR/config.default.json" "$REPO_ROOT/.claude/bin/config.default.json"
echo "  Installed .claude/bin/config.default.json"

cp "$SCRIPT_DIR/VERSION" "$REPO_ROOT/.claude/bin/VERSION"
echo "  Installed .claude/bin/VERSION"

# ── 3. Copy skills ───────────────────────────────────────────────────
for skill_dir in "$SCRIPT_DIR"/skills/*/; do
  skill_name="$(basename "$skill_dir")"
  mkdir -p "$REPO_ROOT/.claude/skills/$skill_name"
  cp "$skill_dir"* "$REPO_ROOT/.claude/skills/$skill_name/" 2>/dev/null || true
  echo "  Installed skill: $skill_name"
done

# ── 4. Copy scripts ──────────────────────────────────────────────────
mkdir -p "$REPO_ROOT/scripts"
for script in "$SCRIPT_DIR"/scripts/*.py; do
  [[ -f "$script" ]] || continue
  script_name="$(basename "$script")"
  cp "$script" "$REPO_ROOT/scripts/$script_name"
  echo "  Installed scripts/$script_name"
done

# ── 5. Init database + migrate ───────────────────────────────────────
TUSK="$REPO_ROOT/.claude/bin/tusk"
"$TUSK" init
"$TUSK" migrate

# ── 6. Print CLAUDE.md snippet ───────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  Installation complete!"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "Next steps:"
echo ""
echo "  1. Edit tusk/config.json to set your project's domains and agents"
echo ""
echo "  2. Re-init to apply config changes:"
echo "     tusk init --force"
echo ""
echo "  3. Add this to your CLAUDE.md:"
echo ""
cat <<'SNIPPET'
## Task Queue

The project task database is managed via `tusk` (at `.claude/bin/tusk`). Use it for all task operations:

```bash
.claude/bin/tusk "SELECT ..."          # Run SQL
.claude/bin/tusk -header -column "SQL"  # With formatting flags
.claude/bin/tusk path                   # Print resolved DB path
.claude/bin/tusk config                 # Print project config
.claude/bin/tusk init                   # Bootstrap DB (new projects)
.claude/bin/tusk shell                  # Interactive sqlite3 shell
.claude/bin/tusk version                # Print installed version
.claude/bin/tusk upgrade                # Upgrade from GitHub
```

Never hardcode the DB path — always go through `tusk`.
SNIPPET
echo ""
