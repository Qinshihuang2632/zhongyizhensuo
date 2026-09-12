"""一次性恢复：把 dist/.数据保留_* 中的历史备份与旧库合并回标准备份目录。"""
import re
import shutil
import sqlite3
import sys
from pathlib import Path

DIST_DATA = Path("dist/中医诊所管理系统/数据")
BACKUPS = DIST_DATA / "备份"


def quick_check(p: Path) -> bool:
    c = sqlite3.connect(str(p))
    try:
        return c.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    finally:
        c.close()


def main() -> None:
    if not BACKUPS.is_dir():
        print("标准备份目录不存在")
        sys.exit(1)
    recovered = 0
    for folder in sorted(Path("dist").glob(".数据保留_*")):
        # 1) 历史自动备份 → manual_recover_ 前缀（永不自动清理）
        for f in sorted((folder / "备份").glob("clinic_*.db")):
            m = re.search(r"(\d{8}_\d{6})", f.name)
            stamp = m.group(1) if m else "unknown"
            dest = BACKUPS / f"manual_recover_{stamp}.db"
            if dest.exists():
                continue
            if quick_check(f):
                shutil.copy2(f, dest)
                print(f"恢复备份: {dest.name}")
                recovered += 1
            else:
                print(f"跳过损坏文件: {f}")
        # 2) 旧库本体也存为手动备份（内容与部分备份重叠，但保全起见）
        old_db = folder / "clinic.db"
        if old_db.is_file():
            m = re.search(r"(\d+)$", folder.name)
            dest = BACKUPS / f"manual_recover_snapshot_{m.group(1) if m else 'x'}.db"
            if not dest.exists() and quick_check(old_db):
                shutil.copy2(old_db, dest)
                print(f"恢复快照: {dest.name}")
                recovered += 1
    print(f"共恢复 {recovered} 个文件")
    print("当前备份列表:")
    for f in sorted(BACKUPS.glob("*.db")):
        print(" ", f.name)


if __name__ == "__main__":
    main()
