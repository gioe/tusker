---
name: dag
description: Generate and open an interactive dependency DAG visualization
allowed-tools: Bash
---

# DAG Skill

Generates an interactive Mermaid.js dependency graph of tasks and opens it in the browser. Nodes are colored by status and shaped by complexity, with a click-to-inspect sidebar showing per-task metrics.

## Usage

Ask the user whether they want to see only active tasks or the full graph.

### Active tasks only (default)

Shows tasks that are not Done:

```bash
tusk dag
```

### All tasks (including Done)

Includes completed and isolated tasks:

```bash
tusk dag --all
```

Then confirm to the user that the DAG has been generated and opened in their browser.
