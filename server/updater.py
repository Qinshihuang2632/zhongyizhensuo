"""软件更新：校验更新包 → 暂存 → 下次启动时应用。

约定：更新包是 zip，必须包含 zhongyizhensuo.exe 与 版本.json，且版本号须大于当前。
应用时只替换程序文件，「数据」目录永不触碰；运行中的 exe/_internal 被 Windows
锁定无法直接覆盖，采用「改名让位 *.old、下轮清理」策略，在启动最早期应用。
"""
import datetime as dt
import json
import os
import re
import shutil
import zipfile
from pathlib import Path

from . import paths

STAGE_DIRNAME = "更新暂存"
UPDATE_MARKER = "update_pending.json"
MAX_UPLOAD = 300 * 1024 * 1024


def current_version() -> str:
    f = paths.version_file()
    if f.exists():
        try:
            return str(json.loads(f.read_text(encoding="utf-8")).get("version", "dev"))
        except Exception:
            pass
    return "dev"


def parse_version(v: str) -> tuple:
    nums = re.findall(r"\d+", str(v))
    return tuple(int(n) for n in nums) or (0,)


def validate_update_zip(zpath: Path) -> str:
    """校验更新包结构与版本，返回新版本号；不合法抛 ValueError。"""
    with zipfile.ZipFile(zpath) as z:
        names = set(z.namelist())
        if "zhongyizhensuo.exe" not in names:
            raise ValueError("更新包缺少主程序（zhongyizhensuo.exe），不是有效的更新包")
        if "版本.json" not in names:
            raise ValueError("更新包缺少版本文件（版本.json）")
        try:
            new_raw = str(json.loads(z.read("版本.json").decode("utf-8")).get("version", ""))
        except Exception:
            raise ValueError("更新包版本文件解析失败") from None
    new, cur = parse_version(new_raw), parse_version(current_version())
    if new <= cur:
        raise ValueError(
            f"更新包版本（{new_raw}）不高于当前版本（{current_version()}），无需更新"
        )
    return new_raw


def stage_update(zpath: Path, app_root: Path | None = None) -> str:
    """校验并解压到「更新暂存」，写入待更新标记；下次启动自动应用。"""
    version = validate_update_zip(zpath)
    app = app_root or paths.app_root()
    data = paths.data_dir() if app_root is None else app / "数据"
    stage = app / STAGE_DIRNAME
    if stage.exists():
        shutil.rmtree(stage, ignore_errors=True)
    with zipfile.ZipFile(zpath) as z:
        z.extractall(stage)
    data.mkdir(parents=True, exist_ok=True)
    (data / UPDATE_MARKER).write_text(
        json.dumps({"version": version,
                    "staged_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
                   ensure_ascii=False),
        encoding="utf-8",
    )
    return version


def _clear_path(target: Path) -> None:
    """删除目标；被进程占用（PermissionError）时改名 *.old 让位，下轮更新清理。"""
    if not target.exists() and not target.is_symlink():
        return
    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    except PermissionError:
        suffix = 0
        while True:
            old = target.with_name(f"{target.name}.old{suffix or ''}")
            if not old.exists():
                break
            suffix += 1
        os.rename(target, old)


def cleanup_old_files(app_root: Path | None = None) -> int:
    """清理历史更新产生的 *.old 让位文件（每次启动调用）。返回清理数。"""
    app = app_root or paths.app_root()
    removed = 0
    for junk in list(app.glob("_internal.old*")) + list(app.glob("zhongyizhensuo.exe.old*")):
        try:
            if junk.is_dir():
                shutil.rmtree(junk, ignore_errors=True)
            else:
                junk.unlink(missing_ok=True)
            removed += 1
        except OSError:
            continue
    return removed


def apply_pending_update(app_root: Path | None = None) -> str | None:
    """启动最早期调用：存在待更新标记则应用暂存文件（数据目录不碰）。返回新版本号。"""
    app = app_root or paths.app_root()
    data = paths.data_dir() if app_root is None else app / "数据"
    marker = data / UPDATE_MARKER
    stage = app / STAGE_DIRNAME
    if not marker.is_file():
        return None
    if not stage.is_dir():
        marker.unlink(missing_ok=True)
        return None
    try:
        info = json.loads(marker.read_text(encoding="utf-8"))
    except Exception:
        info = {}
    for junk in list(app.glob("_internal.old*")) + list(app.glob("zhongyizhensuo.exe.old*")):
        _clear_path(junk)
    for item in stage.iterdir():
        if item.name == "数据":
            continue
        target = app / item.name
        _clear_path(target)
        shutil.move(str(item), str(target))
    shutil.rmtree(stage, ignore_errors=True)
    marker.unlink(missing_ok=True)
    return str(info.get("version") or "?")
