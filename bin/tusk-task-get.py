#!/usr/bin/env python3
"""Read-only fetch of a single task bundle.

Called by the tusk wrapper:
    tusk task-get <task_id>

Arguments received from tusk:
    sys.argv[1] — DB path
    sys.argv[2] — config path (unused)
    sys.argv[3] — task_id (integer or TASK-NNN form)

Returns JSON with task row, acceptance_criteria array, and task_progress array.
Does not modify any state.
"""

import importlib.util
import json
import os
import sqlite3
import sys


def _load_db_lib():
    _p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tusk-db-lib.py")
    _s = importlib.util.spec_from_file_location("tusk_db_lib", _p)
    _m = importlib.util.module_from_spec(_s)
    _s.loader.exec_module(_m)
    return _m


_db_lib = _load_db_lib()
get_connection = _db_lib.get_connection


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("Usage: tusk task-get <task_id>", file=sys.stderr)
        return 1

    db_path = argv[0]
    raw_id = argv[2]

    # Accept both plain integer and TASK-NNN form
    if raw_id.upper().startswith("TASK-"):
        raw_id = raw_id[5:]
    try:
        task_id = int(raw_id)
    except ValueError:
        print(f"Error: Invalid task ID: {argv[2]}", file=sys.stderr)
        return 1

    conn = get_connection(db_path)
    try:
        task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not task:
            print(f"Error: Task {task_id} not found", file=sys.stderr)
            return 1

        criteria_rows = conn.execute(
            "SELECT id, task_id, criterion, source, is_completed, "
            "criterion_type, verification_spec, created_at, updated_at "
            "FROM acceptance_criteria WHERE task_id = ? ORDER BY id",
            (task_id,),
        ).fetchall()

        progress_rows = conn.execute(
            "SELECT * FROM task_progress WHERE task_id = ? ORDER BY created_at DESC",
            (task_id,),
        ).fetchall()

        result = {
            "task": {key: task[key] for key in task.keys()},
            "acceptance_criteria": [{key: row[key] for key in row.keys()} for row in criteria_rows],
            "task_progress": [{key: row[key] for key in row.keys()} for row in progress_rows],
        }

        print(json.dumps(result, indent=2))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
