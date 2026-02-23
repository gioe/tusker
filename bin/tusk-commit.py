#!/usr/bin/env python3
"""Lint, stage, and commit in one atomic operation.

Called by the tusk wrapper:
    tusk commit <task_id> "<message>" [files...] [--criteria <id> ...]

Arguments received from tusk:
    sys.argv[1] — repo root
    sys.argv[2:] — task_id, message, files, and optional --criteria flags

Steps:
    1. Run tusk lint (advisory — output is printed but never blocks)
    2. git add the specified files
    3. git commit with [TASK-<id>] <message> format and Co-Authored-By trailer
    4. For each --criteria <id>, call tusk criteria done <id> (captures HEAD automatically)
"""

import subprocess
import sys


TRAILER = "Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"


def run(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, check=check)


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(
            "Usage: tusk commit <task_id> \"<message>\" <file1> [file2 ...] [--criteria <id> ...]",
            file=sys.stderr,
        )
        return 1

    repo_root = argv[0]
    remaining = argv[1:]

    # Parse --criteria flags out of remaining args; collect everything else positionally
    criteria_ids: list[str] = []
    positional: list[str] = []
    i = 0
    while i < len(remaining):
        if remaining[i] == "--criteria":
            if i + 1 >= len(remaining):
                print("Error: --criteria requires an argument", file=sys.stderr)
                return 1
            criteria_ids.append(remaining[i + 1])
            i += 2
        else:
            positional.append(remaining[i])
            i += 1

    if len(positional) < 2:
        print(
            "Usage: tusk commit <task_id> \"<message>\" <file1> [file2 ...] [--criteria <id> ...]",
            file=sys.stderr,
        )
        return 1

    task_id_str = positional[0]
    message = positional[1]
    files = positional[2:]

    # Validate task_id is an integer
    try:
        task_id = int(task_id_str)
    except ValueError:
        print(f"Error: Invalid task ID: {task_id_str}", file=sys.stderr)
        return 1

    # Validate criteria IDs are integers
    for cid in criteria_ids:
        try:
            int(cid)
        except ValueError:
            print(f"Error: Invalid criterion ID: {cid}", file=sys.stderr)
            return 1

    if not message.strip():
        print("Error: Commit message must not be empty", file=sys.stderr)
        return 1

    # ── Step 1: Run lint (advisory) ──────────────────────────────────
    print("=== Running tusk lint (advisory) ===")
    lint = subprocess.run(["tusk", "lint"], capture_output=False)
    if lint.returncode != 0:
        print("\nLint reported warnings (advisory only — continuing)\n")
    else:
        print()

    # ── Step 2: Stage files ──────────────────────────────────────────
    result = run(["git", "add"] + files, check=False)
    if result.returncode != 0:
        print(f"Error: git add failed:\n{result.stderr.strip()}", file=sys.stderr)
        return 2

    # ── Step 3: Commit ───────────────────────────────────────────────
    full_message = f"[TASK-{task_id}] {message}\n\n{TRAILER}"
    result = run(["git", "commit", "-m", full_message], check=False)
    if result.returncode != 0:
        print(f"Error: git commit failed:\n{result.stderr.strip()}", file=sys.stderr)
        return 2

    print(result.stdout.strip())

    # ── Step 4: Mark criteria done (captures new HEAD automatically) ─
    for cid in criteria_ids:
        print(f"\n=== Marking criterion {cid} done ===")
        result = subprocess.run(
            ["tusk", "criteria", "done", cid], capture_output=False, check=False
        )
        if result.returncode != 0:
            print(
                f"Warning: Failed to mark criterion {cid} done (continuing)",
                file=sys.stderr,
            )

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
