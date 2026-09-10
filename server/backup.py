"""备份与恢复。

- create()：用 SQLite 的 VACUUM INTO 生成一致、紧凑的快照文件。
- auto_backup_if_needed()：每天首次启动自动备份一次（幂等）。
- cleanup()：只清理 clinic_ 前缀的自动备份，保留最近 N 份（N 可配置）；
  manual_ / restore_before_ 前缀的手动备份永不自动删除。
- schedule_restore() / apply_pending_restore()：服务运行时数据库文件被占用，
  不能直接覆盖，因此恢复分两步——先做安全备份并写「待恢复」标记、程序退出；
  下次启动在起服务之前（db.migrate 开头）完成替换。
"""
import datetime as dt
import re
import shutil
import sqlite3
from pathlib import Path

from . import db, paths

AUTO_PREFIX = "clinic_"
PENDING_RESTORE = "clinic.db.pending_restore"
_NAME_RE = re.compile(r"^[A-Za-z0-9_]+\.db$")


def _fresh_connection() -> sqlite3.Connection:
    paths.ensure_dirs()
    return sqlite3.connect(paths.db_path())


def create(kind: str = "manual") -> str:
    # 带微秒，避免同一秒内两次备份（如恢复前的安全备份）文件名碰撞
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    prefix = AUTO_PREFIX if kind == "auto" else "manual_"
    dest = paths.backup_dir() / f"{prefix}{ts}.db"
    conn = _fresh_connection()
    try:
        conn.execute("VACUUM INTO ?", (str(dest),))
    finally:
        conn.close()
    if kind == "auto":
        db.set_setting("last_auto_backup", dt.date.today().isoformat())
        cleanup()
    return dest.name


def cleanup(keep: int | None = None) -> int:
    if keep is None:
        try:
            keep = int(db.get_setting("backup_keep") or 30)
        except ValueError:
            keep = 30
    keep = max(1, keep)
    autos = sorted(paths.backup_dir().glob(f"{AUTO_PREFIX}*.db"))
    removed = 0
    for old in autos[:-keep]:
        old.unlink(missing_ok=True)
        removed += 1
    return removed


def auto_backup_if_needed() -> str | None:
    today = dt.date.today().isoformat()
    if db.get_setting("last_auto_backup") == today:
        return None
    return create("auto")


def list_backups() -> list[dict]:
    items = []
    for p in paths.backup_dir().glob("*.db"):
        items.append({
            "name": p.name,
            "kind": "auto" if p.name.startswith(AUTO_PREFIX) else "manual",
            "size": p.stat().st_size,
            "mtime": dt.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    items.sort(key=lambda x: x["name"], reverse=True)
    return items


def _quick_check(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        row = conn.execute("PRAGMA quick_check").fetchone()
    finally:
        conn.close()
    if not row or row[0] != "ok":
        raise ValueError(f"备份文件校验失败：{path.name}")


def schedule_restore(name: str) -> None:
    if not _NAME_RE.match(name):
        raise ValueError("非法的备份文件名")
    src = paths.backup_dir() / name
    if not src.is_file():
        raise ValueError("备份文件不存在")
    _quick_check(src)
    # 恢复前给当前数据做一次安全备份（manual_ 前缀，不参与自动清理）
    create("manual")
    (paths.data_dir() / PENDING_RESTORE).write_text(name, encoding="utf-8")


def apply_pending_restore() -> str | None:
    """启动早期调用：存在待恢复标记则完成数据库替换。返回所用备份名。"""
    flag = paths.data_dir() / PENDING_RESTORE
    if not flag.is_file():
        return None
    name = flag.read_text(encoding="utf-8").strip()
    src = paths.backup_dir() / name
    flag.unlink(missing_ok=True)
    if not src.is_file():
        raise ValueError(f"待恢复的备份文件不存在：{name}")
    target = paths.db_path()
    for suffix in ("", "-wal", "-shm"):
        Path(str(target) + suffix).unlink(missing_ok=True)
    shutil.copy2(src, target)
    return name
