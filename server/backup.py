"""备份与恢复。

命名规则：
  自动备份  auto_backup_YYYYMMDD_HHMMSS.db   （每天首启一份，超出保留份数滚动清理）
  手动备份  manual_backup_YYYYMMDD_HHMMSS.db （永不自动清理）
  兼容旧版  clinic_* / manual_* 等历史文件照常列出；旧式自动备份同样参与清理。

- create()：用 SQLite 的 VACUUM INTO 生成一致、紧凑的快照文件。
- auto_backup_if_needed()：每天首次启动自动备份一次（幂等）。
- cleanup()：只清理自动前缀的备份，保留最近 N 份（N 可配置）；
  manual 前缀的手动备份永不自动删除。
- schedule_restore() / apply_pending_restore()：服务运行时数据库文件被占用，
  不能直接覆盖，因此恢复分两步——先做安全备份并写「待恢复」标记、程序退出；
  下次启动在起服务之前（db.migrate 开头）完成替换。
"""
import datetime as dt
import json
import re
import shutil
import sqlite3
import zipfile
from pathlib import Path

from . import db, paths

AUTO_PREFIX = "auto_backup_"
LEGACY_AUTO_PREFIX = "clinic_"
PENDING_RESTORE = "clinic.db.pending_restore"
_NAME_RE = re.compile(r"^[A-Za-z0-9_]+\.db$")
_TS_RE = re.compile(r"(\d{8})_(\d{6})")


def _name_sort_key(p: Path) -> str:
    """从文件名提取时间串用于按时间排序；取不到时回退文件修改时间。"""
    m = _TS_RE.search(p.name)
    if m:
        return m.group(1) + m.group(2)
    return dt.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y%m%d%H%M%S")


def _is_auto(name: str) -> bool:
    return name.startswith((AUTO_PREFIX, LEGACY_AUTO_PREFIX))


def _fresh_connection() -> sqlite3.Connection:
    paths.ensure_dirs()
    return sqlite3.connect(paths.db_path())


def create(kind: str = "manual") -> str:
    prefix = AUTO_PREFIX if kind == "auto" else "manual_backup_"
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = paths.backup_dir() / f"{prefix}{ts}.db"
    if dest.exists():  # 同一秒内的第二次备份（如恢复前安全备份）追加微秒防重名
        dest = paths.backup_dir() / f"{prefix}{ts}_{dt.datetime.now().microsecond:06d}.db"
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
    autos = sorted(
        list(paths.backup_dir().glob(f"{AUTO_PREFIX}*.db"))
        + list(paths.backup_dir().glob(f"{LEGACY_AUTO_PREFIX}*.db")),
        key=_name_sort_key,
    )
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
            "kind": "auto" if _is_auto(p.name) else "manual",
            "size": p.stat().st_size,
            "mtime": dt.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            "_sort": _name_sort_key(p),
        })
    items.sort(key=lambda x: x["_sort"], reverse=True)  # 纯按时间倒序（最新在前）
    for it in items:
        it.pop("_sort", None)
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


def export_data_package() -> Path:
    """导出数据包：一致快照 clinic.db 打成 zip，供换电脑迁移。"""
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = paths.data_dir() / f"数据包_{ts}.zip"
    tmp = paths.data_dir() / f".export_{ts}.db"
    conn = _fresh_connection()
    try:
        conn.execute("VACUUM INTO ?", (str(tmp),))
    finally:
        conn.close()
    try:
        _quick_check(tmp)
        version = "dev"
        vf = paths.version_file()
        if vf.exists():
            try:
                version = str(json.loads(vf.read_text(encoding="utf-8")).get("version", "dev"))
            except Exception:
                pass
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(tmp, "clinic.db")
            z.writestr("meta.txt", (
                "中医诊所管理系统数据包\n"
                f"导出时间: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"程序版本: {version}\n"
            ))
    finally:
        tmp.unlink(missing_ok=True)
    return dest


def import_data_package(zpath: Path) -> str:
    """导入数据包：校验后存为手动备份并安排恢复（重启生效）。返回备份名。"""
    with zipfile.ZipFile(zpath) as z:
        names = set(z.namelist())
        if "clinic.db" not in names:
            raise ValueError("数据包缺少 clinic.db，不是有效的数据包")
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        tmp = paths.data_dir() / f".import_{ts}.db"
        with z.open("clinic.db") as src, open(tmp, "wb") as f:
            shutil.copyfileobj(src, f)
    try:
        _quick_check(tmp)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise ValueError("数据包中的 clinic.db 校验失败，文件可能损坏") from None
    ts2 = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    name = f"manual_import_{ts2}.db"
    shutil.move(str(tmp), str(paths.backup_dir() / name))
    schedule_restore(name)
    return name


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
