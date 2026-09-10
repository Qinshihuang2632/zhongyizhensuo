"""SQLite 数据层：WAL + 事务 + 线程内连接复用 + 版本化迁移。

- 每次「收费、扣库存、写流水」这类多步写入都放在 tx() 事务里执行，
  要么全部生效、要么整体回滚，不会留下半截数据。
- WAL 模式允许多线程并发读、写操作自动排队，断电后文件不易损坏。
"""
import logging
import sqlite3
import threading
from contextlib import contextmanager
from collections.abc import Iterator

from . import paths

logger = logging.getLogger(__name__)

_local = threading.local()


def connect() -> sqlite3.Connection:
    """返回当前线程的数据库连接（懒创建，线程内复用）。"""
    conn = getattr(_local, "conn", None)
    if conn is None:
        paths.ensure_dirs()
        conn = sqlite3.connect(paths.db_path(), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        _local.conn = conn
    return conn


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    conn = connect()
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.rollback()
        raise
    else:
        conn.commit()


def query(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    return connect().execute(sql, params).fetchall()


def one(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    return connect().execute(sql, params).fetchone()


def migrate() -> None:
    """按文件名序号依次执行 server/migrations/*.sql，已应用的不重复执行。"""
    conn = connect()
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        " version INTEGER PRIMARY KEY,"
        " applied_at TEXT NOT NULL DEFAULT (datetime('now','localtime')))"
    )
    conn.commit()
    row = conn.execute("SELECT COALESCE(MAX(version), 0) AS v FROM schema_version").fetchone()
    current = row["v"]
    for sql_file in sorted(paths.migrations_dir().glob("*.sql")):
        version = int(sql_file.name.split("_", 1)[0])
        if version <= current:
            continue
        logger.info("应用迁移 %s", sql_file.name)
        conn.executescript(sql_file.read_text(encoding="utf-8"))
        with tx() as c:
            c.execute("INSERT INTO schema_version(version) VALUES (?)", (version,))
