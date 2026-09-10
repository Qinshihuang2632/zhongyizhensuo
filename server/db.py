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


def get_setting(key: str, default: str | None = None) -> str | None:
    row = one("SELECT value FROM settings WHERE key = ?", (key,))
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with tx() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )


def migrate() -> None:
    """启动入口：先处理待恢复（起服务前完成数据库替换），再执行迁移。"""
    from . import backup  # 局部导入，避免与 backup.py 的顶层导入成环

    paths.ensure_dirs()
    try:
        restored = backup.apply_pending_restore()
        if restored:
            logger.info("已完成数据恢复，所用备份：%s", restored)
    except Exception:
        logger.exception("执行待恢复失败，跳过（原数据保持不变）")

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
