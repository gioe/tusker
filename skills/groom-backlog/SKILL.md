---
name: groom-backlog
description: Groom the backlog by closing completed tickets, removing redundant/stale tickets, reprioritizing, and assigning agents
allowed-tools: Bash, Glob, Grep, Read
---

# Groom Backlog Skill

Grooms the local task database by identifying completed, redundant, incorrectly prioritized, or unassigned tasks.

## Setup: Discover Project Config

Before grooming, discover valid values for this project:

```bash
tusk config
```

This returns the full config as JSON (domains, agents, task_types, priorities, complexity, etc.). Use these values (not hardcoded ones) throughout the grooming process.

## Step 0: Auto-Close Expired Deferred Tasks

Before analyzing the backlog, close any deferred tasks that have passed their 60-day expiry. This is automatic and does not require user approval.

```bash
# Collect IDs of expired deferred tasks before closing them
EXPIRED_IDS=$(tusk "
SELECT id FROM tasks
WHERE summary LIKE '%[Deferred]%'
  AND status = 'To Do'
  AND expires_at IS NOT NULL
  AND expires_at < datetime('now')
")

echo "Expired deferred tasks: $(echo "$EXPIRED_IDS" | grep -c . || echo 0)"

# Auto-close expired deferred tasks
tusk "
UPDATE tasks
SET status = 'Done',
    closed_reason = 'expired',
    updated_at = datetime('now'),
    description = description || char(10) || char(10) || '---' || char(10) || 'Auto-closed: Deferred task expired after 60 days without action (' || datetime('now') || ').'
WHERE summary LIKE '%[Deferred]%'
  AND status = 'To Do'
  AND expires_at IS NOT NULL
  AND expires_at < datetime('now');
"

# Close any open sessions for each expired task via the CLI
for TASK_ID in $EXPIRED_IDS; do
  tusk session-close --task-id "$TASK_ID" --skip-stats
done
```

Report how many were auto-closed before proceeding.

## Step 0b: Flag In Progress Tasks with Merged PRs

Detect tasks stuck in "In Progress" whose GitHub PR has already been merged. These are orphaned tasks from sessions that ended before finalization.

```bash
# Find In Progress tasks that have a github_pr URL
tusk -header -column "
SELECT id, summary, github_pr
FROM tasks
WHERE status = 'In Progress'
  AND github_pr IS NOT NULL
  AND github_pr <> ''
"
```

For each task returned, check whether the PR has been merged:

```bash
gh pr view <pr_url> --json state,mergedAt --jq '{state: .state, mergedAt: .mergedAt}'
```

If the PR state is `MERGED`, auto-close the task and any orphaned sessions:

```bash
tusk "UPDATE tasks SET status = 'Done', closed_reason = 'completed', updated_at = datetime('now'),
  description = description || char(10) || char(10) || '---' || char(10) || 'Auto-closed: PR was already merged (' || datetime('now') || ').'
WHERE id = <id>"

# Close any open sessions for this task
tusk session-close --task-id <id> --skip-stats
```

If the PR state is `CLOSED` (not merged), flag it for user review in Step 4 with a note that the PR was closed without merging.

Report how many orphaned In Progress tasks were auto-closed before proceeding.

## Step 0c: Cascade-Close Moot Contingent Tasks

Find open tasks that have a `contingent` dependency on a task that closed as `wont_do` or `expired`. These tasks are moot — the upstream evaluation/investigation determined the work isn't needed.

```bash
# Find contingent dependents of tasks closed as wont_do/expired
tusk -header -column "
SELECT t.id, t.summary, t.status,
       d.depends_on_id as closed_task_id,
       upstream.summary as closed_task_summary,
       upstream.closed_reason
FROM tasks t
JOIN task_dependencies d ON t.id = d.task_id
JOIN tasks upstream ON d.depends_on_id = upstream.id
WHERE t.status <> 'Done'
  AND d.relationship_type = 'contingent'
  AND upstream.status = 'Done'
  AND upstream.closed_reason IN ('wont_do', 'expired')
"
```

For each match, auto-close as `wont_do`:

```bash
tusk "UPDATE tasks SET status = 'Done', closed_reason = 'wont_do',
  updated_at = datetime('now'),
  description = description || char(10) || char(10) || '---' || char(10) ||
    'Auto-closed: Contingent on TASK-<upstream_id> which closed as <reason> (' || datetime('now') || ').'
WHERE id = <id>"
```

Report how many contingent tasks were auto-closed before proceeding.

## Step 1: Fetch All Backlog Tasks

```bash
tusk -header -column "
SELECT id, summary, SUBSTR(description, 1, 300) AS description,
       status, priority, domain, assignee, task_type, priority_score, closed_reason
FROM tasks
WHERE status <> 'Done'
ORDER BY priority_score DESC, id
"

tusk deps blocked
tusk deps all
```

## Step 2: Scan for Duplicates and Categorize Tasks

### Step 2a: Scan for Duplicate Pairs

```bash
tusk dupes scan --status "To Do"
```

Any pairs found should be included in **Category B** with reason "duplicate".

### Step 2b: Categorize Tasks

Analyze each task and categorize. In addition to the heuristic scan results from Step 2a, look for **semantic duplicates** — tasks that cover the same intent but use different wording (e.g., "Implement password reset flow" vs. "Add forgot password endpoint"). The heuristic catches textual near-matches; you should catch conceptual overlap that differs in phrasing.

### Category A: Candidates for Done (Acceptance Criteria Already Met)
Tasks where the work has already been completed in the codebase:
1. **Verify against code**: Search the codebase to determine if the work is done
2. **Evidence required**: Provide specific file paths and code as proof
3. **Mark as Done**:
   ```bash
   tusk "UPDATE tasks SET status = 'Done', closed_reason = 'completed', updated_at = datetime('now') WHERE id = <id>"
   ```

### Category B: Candidates for Deletion
- **Redundant tasks**: Duplicates or near-duplicates
- **Obsolete tasks**: No longer relevant
- **Stale tasks**: Untouched with no clear path forward
- **Vague tasks**: Insufficient detail to act on

Before recommending deletion, check dependents:
```bash
tusk deps dependents <id>
```

### Category C: Candidates for Reprioritization
- **Under-prioritized**: Security issues, user-facing bugs
- **Over-prioritized**: Nice-to-haves, speculative work

### Category D: Unassigned Tasks
Tasks without an agent assignee:

```bash
tusk -header -column "SELECT id, summary, domain FROM tasks WHERE status <> 'Done' AND assignee IS NULL"
```

Assign based on project agents (from `tusk config`).

### Category E: Healthy Tasks
Correctly prioritized, assigned, and relevant. No action needed.

## Step 3: Review Context

```bash
tusk -header -column "SELECT * FROM tasks WHERE id = <id>"
```

Also review recent commits and project documentation to understand current priorities.

## Step 4: Present Findings for Approval

Present analysis in this format:

```markdown
## Backlog Grooming Analysis

### Total Tasks Analyzed: X

### Ready for Done (W tasks)
| ID | Summary | Evidence |

### Recommended for Deletion (Y tasks)
| ID | Summary | Reason |

### Recommended for Reprioritization (Z tasks)
| ID | Summary | Current | Recommended | Reason |

### Unassigned Tasks (U tasks)
| ID | Summary | Recommended Agent | Reason |

### No Action Needed (V tasks)
```

## Step 5: Get User Confirmation

**IMPORTANT**: Before making any changes, explicitly ask the user to approve each category.

## Step 6: Execute Changes

Only after user approval:

### For Done Transitions:
```bash
tusk "UPDATE tasks SET status = 'Done', closed_reason = 'completed', updated_at = datetime('now') WHERE id = <id>"
```

### For Deletions:
```bash
# Duplicates:
tusk "UPDATE tasks SET status = 'Done', closed_reason = 'duplicate', updated_at = datetime('now') WHERE id = <id>"

# Obsolete/won't-do:
tusk "UPDATE tasks SET status = 'Done', closed_reason = 'wont_do', updated_at = datetime('now') WHERE id = <id>"
```

### For Priority Changes:
```bash
tusk "UPDATE tasks SET priority = '<New Priority>' WHERE id = <id>"
```

### For Agent Assignments:
```bash
tusk "UPDATE tasks SET assignee = '<agent-name>' WHERE id = <id>"
```

### After Each Change:
```bash
tusk -header -column "SELECT id, summary, status, priority FROM tasks WHERE id = <id>"
```

## Step 7: Bulk-Estimate Unsized Tasks

Before computing priority scores, ensure every open task has a complexity estimate. Tasks without one default to `M` weight in the WSJF formula, so explicit sizing produces better rankings.

### 7a: Find unsized tasks

```bash
tusk -header -column "
SELECT id, summary, description, domain, task_type
FROM tasks
WHERE status <> 'Done'
  AND complexity IS NULL
ORDER BY id
"
```

If no rows are returned, skip to Step 8.

### 7b: Estimate complexity

For each unsized task, estimate complexity using this scale (same as `/create-task`):

| Size | Meaning |
|------|---------|
| `XS` | Partial session — a quick tweak or config change |
| `S`  | ~1 session — a focused, well-scoped change |
| `M`  | 2–3 sessions — moderate scope, may touch several files |
| `L`  | 3–5 sessions — significant feature or cross-cutting change |
| `XL` | 5+ sessions — large effort, architectural change |

Base the estimate on the task's summary, description, and domain. When unsure, default to `M`.

### 7c: Present estimates for approval

Show all proposed estimates in a table:

```markdown
| ID | Summary | Estimated Complexity |
|----|---------|---------------------|
| 12 | Add rate limiting middleware | S |
| 17 | Refactor auth module | L |
```

Ask the user to confirm or adjust before applying.

### 7d: Apply estimates

After approval, update each task:

```bash
tusk "UPDATE tasks SET complexity = '<size>', updated_at = datetime('now') WHERE id = <id>"
```

## Step 8: Compute Priority Scores (WSJF)

After all grooming changes are complete (including complexity estimates from Step 7), compute `priority_score` for all open tasks using WSJF (Weighted Shortest Job First) scoring.

### Scoring Formula

```
raw_score = base_priority + source_bonus + unblocks_bonus + contingent_penalty
priority_score = ROUND(raw_score / complexity_weight)
```

Where:
- **base_priority**: Highest=100, High=80, Medium=60, Low=40, Lowest=20
- **source_bonus**: +10 if NOT a `[Deferred]` task
- **unblocks_bonus**: +5 per dependent task, capped at +15
- **contingent_penalty**: -10 if ALL of the task's blockers are `contingent` (none are `blocks`), biasing `/next-task` toward tasks with guaranteed value
- **complexity_weight**: XS=1, S=2, M=3, L=5, XL=8 (NULL defaults to 3, same as M)

This gives small, high-priority tasks a natural advantage over large ones — a High/XS task (90) outranks a Highest/XL task (14).

```bash
tusk "
UPDATE tasks SET priority_score = ROUND(
  (
    CASE priority
      WHEN 'Highest' THEN 100
      WHEN 'High' THEN 80
      WHEN 'Medium' THEN 60
      WHEN 'Low' THEN 40
      WHEN 'Lowest' THEN 20
      ELSE 40
    END
    + CASE WHEN summary NOT LIKE '%[Deferred]%' THEN 10 ELSE 0 END
    + MIN(COALESCE((
      SELECT COUNT(*) * 5
      FROM task_dependencies d
      WHERE d.depends_on_id = tasks.id
    ), 0), 15)
    + CASE WHEN EXISTS (
      SELECT 1 FROM task_dependencies d
      WHERE d.task_id = tasks.id AND d.relationship_type = 'contingent'
    ) AND NOT EXISTS (
      SELECT 1 FROM task_dependencies d
      WHERE d.task_id = tasks.id AND d.relationship_type = 'blocks'
    ) THEN -10 ELSE 0 END
  ) * 1.0
  / CASE complexity
      WHEN 'XS' THEN 1
      WHEN 'S' THEN 2
      WHEN 'M' THEN 3
      WHEN 'L' THEN 5
      WHEN 'XL' THEN 8
      ELSE 3
    END
)
WHERE status <> 'Done';
"

# Verify — show complexity alongside scores so the WSJF effect is visible
tusk -header -column "
SELECT id, summary, priority, complexity, priority_score
FROM tasks
WHERE status = 'To Do'
ORDER BY priority_score DESC
LIMIT 15;
"
```

## Step 9: Generate Summary Report

```markdown
## Backlog Grooming Complete

### Actions Taken:
- **Moved to Done**: W tasks
- **Deleted**: X tasks
- **Reprioritized**: Y tasks
- **Assigned**: U tasks
- **Unchanged**: Z tasks
```

Show final backlog state:
```bash
tusk -header -column "SELECT id, summary, status, priority, domain, assignee FROM tasks WHERE status <> 'Done' ORDER BY priority DESC, id"
```

## Important Guidelines

1. **Never modify without approval**: Always present findings and wait for explicit user confirmation
2. **Verify against code thoroughly**: Use Glob, Grep, and Read to find evidence
3. **Be conservative**: When in doubt, keep the task open
4. **Preserve history**: Close with a reason rather than DELETE
5. **Consider dependencies**: Check dependents before deleting
6. **Batch operations carefully**: Execute changes one at a time
7. **Keep the backlog lean (< 20 open tasks)**: The full backlog dump scales at ~700 tokens/task and is repeated across ~15+ agentic turns during grooming. A 30-task backlog can consume over 300k tokens in a single session. Aggressively close, merge, or defer tasks to stay under 20 open items
