"""路径解析：开发态基于项目根目录，打包态基于 exe 所在目录。

约定：程序目录（可整体替换）与数据目录（永不随更新变动）彻底分离，
全部业务数据都在「数据」文件夹内，便于备份与换机迁移。
"""
import sys
from pathlib import Path


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    return app_root() / "数据"


def db_path() -> Path:
    return data_dir() / "clinic.db"


def backup_dir() -> Path:
    return data_dir() / "备份"


def log_dir() -> Path:
    return data_dir() / "日志"


def version_file() -> Path:
    return app_root() / "版本.json"


def migrations_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "server" / "migrations"  # noqa: SLF001
    return Path(__file__).resolve().parent / "migrations"


def frontend_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "frontend" / "dist"  # noqa: SLF001
    return app_root() / "frontend" / "dist"


def ensure_dirs() -> None:
    for d in (data_dir(), backup_dir(), log_dir()):
        d.mkdir(parents=True, exist_ok=True)
