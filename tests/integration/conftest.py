"""Shared helpers for merge integration tests."""

import sqlite3


def _insert_task(conn: sqlite3.Connection, *, status: str = "In Progress") -> int:
    cur = conn.execute(
        "INSERT INTO tasks (summary, status, task_type, priority, complexity, priority_score)"
        " VALUES ('test task', ?, 'feature', 'Medium', 'S', 50)",
        (status,),
    )
    conn.commit()
    return cur.lastrowid


def _insert_session(conn: sqlite3.Connection, task_id: int, *, closed: bool = False) -> int:
    if closed:
        cur = conn.execute(
            "INSERT INTO task_sessions (task_id, started_at, ended_at)"
            " VALUES (?, datetime('now', '-1 hour'), datetime('now'))",
            (task_id,),
        )
    else:
        cur = conn.execute(
            "INSERT INTO task_sessions (task_id, started_at) VALUES (?, datetime('now'))",
            (task_id,),
        )
    conn.commit()
    return cur.lastrowid
