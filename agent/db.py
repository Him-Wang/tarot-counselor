# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""db.py — SQLite 连接与 schema 版本迁移（stdlib only）。

每个模块把自己的建表语句登记成 (version, fn)，migrate() 只在
PRAGMA user_version 落后时执行，升级不会重复建表，也不会丢旧数据。
"""

import os
import sqlite3


def connect(path, timeout=10):
    """Open a SQLite connection with the project-wide defaults."""
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, timeout=timeout)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def version(conn):
    return int(conn.execute("PRAGMA user_version").fetchone()[0] or 0)


def migrate(conn, migrations):
    """Apply pending migrations.

    migrations: iterable of (version: int, apply: callable(conn)).
    Returns the resulting schema version.
    """
    current = version(conn)
    for target, apply in migrations:
        if current < target:
            apply(conn)
            conn.execute("PRAGMA user_version=%d" % int(target))
            conn.commit()
            current = int(target)
    return current


def ensure(conn, target, script):
    """Convenience: create/upgrade a schema with one executescript block."""
    if version(conn) < target:
        conn.executescript(script)
        conn.execute("PRAGMA user_version=%d" % int(target))
        conn.commit()
        return True
    return False
