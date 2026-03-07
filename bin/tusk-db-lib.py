"""Shared database and config utilities for tusk scripts.

Provides get_connection() and load_config() so every tusk-*.py script
can import them from one place instead of duplicating the 4-liner.

Imported via importlib (hyphenated filename requires it):

    import importlib.util
    import os

    def _load_db_lib():
        _p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tusk-db-lib.py")
        _s = importlib.util.spec_from_file_location("tusk_db_lib", _p)
        _m = importlib.util.module_from_spec(_s)
        _s.loader.exec_module(_m)
        return _m

    _db_lib = _load_db_lib()
    get_connection = _db_lib.get_connection
    load_config = _db_lib.load_config  # optional — only scripts that need it
"""

import json
import sqlite3


def get_connection(db_path: str) -> sqlite3.Connection:
    """Return a SQLite connection with row_factory and foreign keys enabled."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def load_config(config_path: str) -> dict:
    """Load and return the tusk config JSON."""
    with open(config_path) as f:
        return json.load(f)
