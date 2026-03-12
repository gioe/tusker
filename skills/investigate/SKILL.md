---
name: investigate
description: Investigate the scope of a problem and form an honest assessment — task creation is optional
allowed-tools: Bash, Read, Glob, Grep, Task, Write, EnterPlanMode
---

# Investigate Skill

Scopes a problem through structured codebase research and forms an honest assessment. **This skill is investigation-only — it never modifies files, runs tests, or implements anything.** The investigation may conclude that no action is needed; task creation is a conditional outcome, not a guaranteed one.

## Step 0: Start Cost Tracking

Record the start of this investigation so cost can be captured at the end:

```bash
tusk skill-run start investigate
```

This prints `{"run_id": N, "started_at": "..."}`. Capture `run_id` — you will need it in Step 8.

## Step 1: Capture the Problem

The user provides a problem statement after `/investigate`. It could be:
- A bug report or error message
- A performance concern or regression
- A design smell or architectural issue
- A feature area in need of refactoring
- A vague concern ("something feels wrong in auth")

If the user didn't provide a description, ask:

> What problem should I investigate? Describe the issue, area of concern, or question you want scoped.

**Valid outcomes include "no action needed."** The goal is an honest assessment, not a task list. If investigation reveals the concern is unfounded, the code is already correct, or existing tasks cover it, say so clearly — that is a successful investigation.

## Step 2: Enter Plan Mode

Use the `EnterPlanMode` tool now. This enforces the investigation contract — no files will be written or modified during the investigation phase.

## Step 3: Load Project Context

Fetch config and open backlog for reference:

```bash
tusk setup
```

Parse the returned JSON. Hold `config` (domains, agents, task_types, priorities, complexity) and `backlog` (open tasks) in context. You'll need both during investigation — `backlog` lets you catch tasks that already cover the same ground, which is also a first-class reason to conclude "no action needed."

If `PILLARS.md` exists in the project root, read it now:

```
Read file: <project_root>/PILLARS.md
```

Hold the pillar definitions in context — you will use them in Step 5 to evaluate whether proposed tasks align with the project's design values.

## Step 4: Investigate

Use read-only tools to understand the problem. Shape the investigation around the problem statement — don't go wide for completeness, go deep where the problem points.

**Allowed tools during investigation:**
- `Read` — read source files, configs, tests, docs
- `Glob` — discover files in relevant directories
- `Grep` — search for patterns, symbols, error strings, function calls
- `Task` with `subagent_type=Explore` — broad multi-location searches where simple grep is insufficient
- `Bash` — run `tusk` commands only (queries to the task database, not build/test commands)

**Prohibited during investigation:**
- `Write`, `Edit` — do not touch any project files
- Build commands, test runners, scripts that produce side effects

### What to answer for each affected area

| Question | Why it matters |
|----------|----------------|
| What files/modules are affected? | Defines the scope of remediation |
| What is the root cause? | Ensures tasks fix causes, not symptoms |
| What is currently broken or missing? | Drives acceptance criteria |
| What edge cases or failure modes exist? | Surfaces what a narrow fix would miss |
| Are there related issues in nearby code? | Candidates for tangential tasks |
| Are any open backlog tasks already addressing this? | Avoids duplicating existing work |

Stop when you have a clear picture of the problem area — whether that leads to concrete remediation tasks or to the conclusion that no action is needed.

**Exhaustiveness:** Report every distinct finding the evidence supports — do not force findings into clusters to reach a round number. The correct count may be 0, 1, 4, 7, or any other number. Artificial grouping hides signal; artificial splitting adds noise. Let the data determine the count.

## Step 5: Write the Investigation Report

Before drafting the report, apply the **Decision Criteria** filter to each potential finding:

### Decision Criteria

A finding belongs in **Proposed Remediation** only if it passes all five filters. If it fails any filter, move it to **Out of Scope** and note which filter it failed and why.

| Filter | Question to ask |
|--------|-----------------|
| **Pillar impact** | Does acting on this finding align with at least one project pillar (from PILLARS.md, if loaded)? Findings that conflict with core design values belong out of scope regardless of severity. *(Skip this filter if PILLARS.md was not loaded — projects without one have no pillar constraints to check.)* |
| **Root cause vs. symptom** | Is this the root cause, or a downstream symptom of another finding already in scope? Symptoms should reference their root-cause task rather than get their own. |
| **Actionability** | Can a task be written with clear, verifiable acceptance criteria? Vague concerns without a concrete "done" condition belong in Open Questions, not Proposed Remediation. |
| **Cost of inaction** | If left unfixed, does this finding cause measurable harm (data loss, user-facing breakage, security risk, compounding tech debt)? Low-stakes cosmetic issues that are "nice to fix" belong out of scope. |
| **Backlog coverage** | Is an open backlog task already addressing this? If yes, note the existing task ID and exclude it from Proposed Remediation. |

---

Prepare the report before exiting plan mode. Format:

```markdown
## Investigation: <problem title>

### Summary
One or two sentences: root cause and scope.

### Affected Areas
- `path/to/file.py` — what is wrong here
- `path/to/other.ts` — what is wrong here

### Root Cause
Detailed explanation. Include relevant code snippets inline (do not re-read files at this stage).

### Proposed Remediation *(omit this section if investigation finds nothing actionable)*

> Zero tasks is a valid outcome. Only include tasks that passed all five Decision Criteria filters above.

**<imperative summary>** (Priority · Domain · Type · Complexity)
> What needs to be done and why. Include acceptance criteria ideas.

**<imperative summary>** (Priority · Domain · Type · Complexity)
> ...

*If no remediation is warranted, replace this section with a brief explanation of why no action is needed.*

### Out of Scope
Related issues discovered that did not pass the Decision Criteria filters. Note which filter each failed. Candidates for separate tasks or future work.

### Open Questions
Ambiguities or decisions that need input before work can begin. Omit this section if none.
```

## Step 6: Exit Plan Mode

Use `ExitPlanMode` to present the investigation report for user review. Set `allowedPrompts` to allow only task creation — no implementation:

```json
[{"tool": "Bash", "prompt": "run /create-task to create tasks if the user approves"}]
```

After presenting the report, explicitly ask the user:

> Should I create tasks for the proposed remediation, or is this finding sufficient on its own?

Wait for the user to respond. They may:
- Ask follow-up questions → answer from your investigation findings; re-investigate only if genuinely new ground is needed
- Request a deeper look at a specific area → use read-only tools, then update the report
- Approve the proposed tasks → proceed to Step 7
- Remove specific tasks → exclude them from Step 7
- Decline to create tasks, or if no remediation was proposed → proceed to Step 8 to close the skill gracefully

## Step 7: Create Tasks via /create-task *(conditional — skip if user declined or no tasks are warranted)*

> **Note:** Keep the `run_id` from Step 0 in context — you will need it after `/create-task` completes in Step 8.

**If the user declined task creation, or if the investigation found nothing actionable, skip this step entirely and proceed to Step 8.**

If the user approved task creation, pass the proposed remediation tasks to the `/create-task` workflow. Read the skill:

```
Read file: <base_directory>/../create-task/SKILL.md
```

Follow its instructions from **Step 1**, using the Proposed Remediation section from your report as the input text. `/create-task` will handle:
- Decomposition review and user approval
- Acceptance criteria generation
- Duplicate detection
- Metadata assignment (priority, domain, task_type, complexity, assignee)
- Dependency proposals

## Step 7.5: Offer Deferred Tasks for Out of Scope Items *(conditional)*

> **Note:** Keep the `run_id` from Step 0 in context — you will need it in Step 8.

**Skip this step if the report's Out of Scope section is empty or absent.**

If Out of Scope items were identified, ask the user:

> The investigation also surfaced these out-of-scope findings. Should I capture any as deferred tasks so they're not lost?
>
> [list the Out of Scope items]

Wait for the user's response. If they decline or don't select any items, proceed to Step 8 with `<D>` = 0.

For each item the user approves, insert it as a deferred task:

```bash
tusk task-insert "<summary>" "<description>" \
  --priority "Low" \
  --deferred
```

- Each deferred task gets `is_deferred=1`, a `[Deferred]` prefix in the summary, and `expires_at = now + 60 days`.
- Assign `domain`, `task_type`, and `complexity` where inferrable from the item; omit flags if unclear.
- Do **not** run `/create-task` — insert directly via `tusk task-insert --deferred`.

Track how many deferred tasks were inserted (`<D>`) — you will need it in Step 8.

## Step 8: Finish Cost Tracking

Record cost for this investigation run. Replace `<run_id>` with the value captured in Step 0, `<N>` with the number of tasks proposed in your Investigation Report (Step 5), and `<M>` with the total number of tasks created — include both tasks created by `/create-task` (Step 7) and deferred tasks inserted in Step 7.5. If neither step created any tasks, set `<M>` to 0.

```bash
tusk skill-run finish <run_id> --metadata '{"tasks_proposed":<N>,"tasks_created":<M>}'
```

This reads the Claude Code transcript for the time window of this run and stores token counts, estimated cost, and productivity metadata in the `skill_runs` table. Note that the captured window covers the full session — including both the investigation phase and the `/create-task` workflow — so the reported cost reflects the entire `/investigate` invocation.

To view cost history across all investigate runs:

```bash
tusk skill-run list investigate
```

## Hard Constraints

- **Never write or edit project files** — not during investigation, not after
- **Never run build commands, test runners, or scripts** — `Bash` is for `tusk` queries only
- **Never implement any proposed task** — that is the job of `/tusk`
- **Task creation is optional** — if investigation finds nothing actionable, or the user declines, close gracefully without calling `/create-task`
- **Never insert tasks directly** with `tusk task-insert` — if creating tasks, always hand off to `/create-task`
- If the fix is trivially obvious (a one-line typo, obvious config error), note it in the report as a "Trivial Fix" and let the user decide whether to create a task or fix it manually — do not apply it yourself
