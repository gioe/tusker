#!/usr/bin/env python3
"""Validate referential integrity and consistency of the tusk tasks database."""

import json
import sqlite3
import sys
from datetime import datetime, timezone


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def check_foreign_keys(conn: sqlite3.Connection) -> list[str]:
    """Run SQLite's built-in foreign key check."""
    issues = []
    rows = conn.execute("PRAGMA foreign_key_check").fetchall()
    for row in rows:
        table, rowid, parent, fkid = row
        issues.append(
            f"Foreign key violation: {table} rowid={rowid} "
            f"references missing row in {parent}"
        )
    return issues


def check_done_without_closed_reason(conn: sqlite3.Connection) -> list[str]:
    """Find tasks marked Done but missing a closed_reason."""
    issues = []
    rows = conn.execute(
        "SELECT id, summary FROM tasks "
        "WHERE status = 'Done' AND closed_reason IS NULL"
    ).fetchall()
    for row in rows:
        issues.append(
            f"Task {row['id']} is Done but has no closed_reason: "
            f"{row['summary']}"
        )
    return issues


def check_closed_reason_on_open(conn: sqlite3.Connection) -> list[str]:
    """Find open tasks that have a closed_reason set."""
    issues = []
    rows = conn.execute(
        "SELECT id, summary, status, closed_reason FROM tasks "
        "WHERE status != 'Done' AND closed_reason IS NOT NULL"
    ).fetchall()
    for row in rows:
        issues.append(
            f"Task {row['id']} is '{row['status']}' but has "
            f"closed_reason='{row['closed_reason']}': {row['summary']}"
        )
    return issues


def check_expired_open_tasks(conn: sqlite3.Connection) -> list[str]:
    """Find open tasks past their expires_at date."""
    issues = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    rows = conn.execute(
        "SELECT id, summary, expires_at FROM tasks "
        "WHERE status != 'Done' AND expires_at IS NOT NULL AND expires_at < ?",
        (now,),
    ).fetchall()
    for row in rows:
        issues.append(
            f"Task {row['id']} expired on {row['expires_at']} "
            f"but is still open: {row['summary']}"
        )
    return issues


def check_circular_dependencies(conn: sqlite3.Connection) -> list[str]:
    """Detect circular dependency chains using DFS."""
    issues = []
    edges = conn.execute(
        "SELECT task_id, depends_on_id FROM task_dependencies"
    ).fetchall()

    # Build adjacency list: task_id -> [depends_on_id, ...]
    graph: dict[int, list[int]] = {}
    for edge in edges:
        graph.setdefault(edge["task_id"], []).append(edge["depends_on_id"])

    # Standard DFS cycle detection
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[int, int] = {}
    # Collect all nodes (both sides of edges)
    all_nodes = set(graph.keys())
    for deps in graph.values():
        all_nodes.update(deps)
    for node in all_nodes:
        color[node] = WHITE

    cycles: list[list[int]] = []

    def dfs(node: int, path: list[int]):
        color[node] = GRAY
        path.append(node)
        for neighbor in graph.get(node, []):
            if color[neighbor] == GRAY:
                # Found a cycle — extract just the cycle portion
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:] + [neighbor]
                cycles.append(cycle)
            elif color[neighbor] == WHITE:
                dfs(neighbor, path)
        path.pop()
        color[node] = BLACK

    for node in all_nodes:
        if color[node] == WHITE:
            dfs(node, [])

    for cycle in cycles:
        chain = " -> ".join(str(t) for t in cycle)
        issues.append(f"Circular dependency: {chain}")

    return issues


def check_config_mismatches(
    conn: sqlite3.Connection, config: dict,
) -> list[str]:
    """Find column values that don't match the current config."""
    issues = []
    checks = [
        ("status", "statuses"),
        ("priority", "priorities"),
        ("closed_reason", "closed_reasons"),
        ("domain", "domains"),
        ("task_type", "task_types"),
    ]
    for column, config_key in checks:
        allowed = config.get(config_key, [])
        if not allowed:
            continue  # empty list means no validation
        rows = conn.execute(
            f"SELECT id, summary, {column} FROM tasks "  # noqa: S608
            f"WHERE {column} IS NOT NULL "
            f"AND {column} NOT IN ({','.join('?' * len(allowed))})",
            allowed,
        ).fetchall()
        for row in rows:
            issues.append(
                f"Task {row['id']} has invalid {column}='{row[column]}' "
                f"(allowed: {', '.join(allowed)}): {row['summary']}"
            )
    return issues


def check_sessions_without_task(conn: sqlite3.Connection) -> list[str]:
    """Find sessions referencing non-existent tasks (beyond FK check)."""
    issues = []
    rows = conn.execute(
        "SELECT s.id, s.task_id FROM task_sessions s "
        "LEFT JOIN tasks t ON s.task_id = t.id WHERE t.id IS NULL"
    ).fetchall()
    for row in rows:
        issues.append(
            f"Session {row['id']} references non-existent task {row['task_id']}"
        )
    return issues


def check_progress_without_task(conn: sqlite3.Connection) -> list[str]:
    """Find progress entries referencing non-existent tasks."""
    issues = []
    rows = conn.execute(
        "SELECT p.id, p.task_id FROM task_progress p "
        "LEFT JOIN tasks t ON p.task_id = t.id WHERE t.id IS NULL"
    ).fetchall()
    for row in rows:
        issues.append(
            f"Progress entry {row['id']} references non-existent "
            f"task {row['task_id']}"
        )
    return issues


def main():
    if len(sys.argv) < 3:
        print("Usage: tusk-validate.py <db_path> <config_path>", file=sys.stderr)
        sys.exit(2)

    db_path = sys.argv[1]
    config_path = sys.argv[2]

    with open(config_path) as f:
        config = json.load(f)

    conn = get_connection(db_path)

    all_issues: list[tuple[str, list[str]]] = []
    checks = [
        ("Foreign key integrity", check_foreign_keys),
        ("Done tasks without closed_reason", check_done_without_closed_reason),
        ("Open tasks with closed_reason", check_closed_reason_on_open),
        ("Expired open tasks", check_expired_open_tasks),
        ("Circular dependencies", check_circular_dependencies),
        ("Orphaned sessions", check_sessions_without_task),
        ("Orphaned progress entries", check_progress_without_task),
    ]

    total_issues = 0
    for label, check_fn in checks:
        issues = check_fn(conn)
        all_issues.append((label, issues))
        total_issues += len(issues)

    # Config mismatch is separate because it needs the config dict
    config_issues = check_config_mismatches(conn, config)
    all_issues.append(("Config value mismatches", config_issues))
    total_issues += len(config_issues)

    conn.close()

    # Print report
    for label, issues in all_issues:
        if issues:
            print(f"\n  {label}:")
            for issue in issues:
                print(f"    - {issue}")

    if total_issues == 0:
        print("All checks passed. Database is consistent.")
        sys.exit(0)
    else:
        print(f"\nFound {total_issues} issue(s).")
        sys.exit(1)


if __name__ == "__main__":
    main()
