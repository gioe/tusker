---
name: dashboard
description: Generate and open an HTML task dashboard with per-task metrics
allowed-tools: Bash
---

# Dashboard Skill

Generates a self-contained HTML dashboard showing per-task token counts, cost, and session metrics, then opens it in the browser.

## Usage

When this skill is invoked, run:

```bash
tusk dashboard
```

Then confirm to the user that the dashboard has been generated and opened in their browser.

## What It Shows

The dashboard displays data from the `task_metrics` view including:
- Per-task session counts, duration, and cost
- Token usage (input/output) per task
- Lines added/removed per task
- Acceptance criteria completion stats
- Estimate-vs-actual complexity metrics
