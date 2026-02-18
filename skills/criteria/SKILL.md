---
name: criteria
description: Manage acceptance criteria for tasks (add, list, complete, reset)
allowed-tools: Bash
---

# Criteria Skill

Manages per-task acceptance criteria in the project task database (via `tusk` CLI). Acceptance criteria define the conditions that must be met for a task to be considered done.

## Commands

### Add a criterion

```bash
tusk criteria add <task_id> "criterion text" [--source original|subsumption|pr_review]
```

The `--source` flag tracks where the criterion came from (default: `original`):
- **`original`** — defined when the task was created
- **`subsumption`** — inherited from a subsumed duplicate task
- **`pr_review`** — added during PR review

Example:
```bash
tusk criteria add 42 "API returns 200 with valid payload" --source original
```

### List criteria for a task

```bash
tusk criteria list <task_id>
```

### Mark a criterion as done

```bash
tusk criteria done <criterion_id>
```

### Reset a criterion to incomplete

```bash
tusk criteria reset <criterion_id>
```

## Arguments

Parse the user's request to determine:
1. The subcommand (add, list, done, reset)
2. The task ID or criterion ID involved
3. The criterion text and source (for add)

Then run the appropriate command from the examples above.
