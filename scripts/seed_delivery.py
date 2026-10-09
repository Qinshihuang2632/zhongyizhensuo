"""生成交付种子数据库：诊所信息 + 管理密码 + 价格表项目，诊所装完即可直接登录使用。

用法：python scripts/seed_delivery.py --out 目标clinic.db路径 [--clinic 名称] [--password 密码]

种子库通过应用自身的迁移机制构建（schema_version 完整登记），诊所端启动时不会重复跑迁移。
"""
import argparse
import hashlib
import secrets
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 彭学锋中医诊所价格表（2026-10）
ITEMS = [
    ("按摩", "次", 50.0),
    ("针灸", "次", 50.0),
    ("牵引", "路", 20.0),
    ("超短波", "路", 20.0),
    ("电脑中频", "路", 20.0),
    ("经皮神经电刺激", "路", 20.0),
    ("痉挛肌治疗仪", "路", 15.0),
    ("神经损伤治疗仪", "路", 15.0),
    ("肌兴奋治疗仪", "路", 15.0),
    ("推筋", "次", 20.0),
    ("艾灸", "次", 40.0),
    ("刮痧", "次", 20.0),
    ("火罐", "次", 10.0),
    ("放血", "次", 50.0),
    ("水药", "次", 180.0),
    ("烧药", "次", 80.0),
    ("康复", "30分钟", 50.0),
    ("疗愈", "小时", 600.0),
]


def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return f"pbkdf2$120000${salt.hex()}${dk.hex()}"


def build(dest: Path, clinic: str = "彭学锋中医诊所", password: str = "123456") -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        Path(str(dest) + suffix).unlink(missing_ok=True)

    sys.path.insert(0, str(ROOT))
    # 将应用的数据库路径临时指向种子库，复用其迁移机制（含 schema_version 登记）
    import server.paths as paths
    paths.db_path = lambda: dest
    import server.db as sdb
    sdb.migrate()

    conn = sqlite3.connect(str(dest))
    conn.execute("INSERT INTO settings (key, value) VALUES ('clinic_name', ?)", (clinic,))
    conn.execute("INSERT INTO settings (key, value) VALUES ('password_hash', ?)",
                 (password_hash(password),))
    for name, unit, price in ITEMS:
        conn.execute(
            "INSERT INTO items (category, name, unit, price, cost, active)"
            " VALUES ('治疗项目', ?, ?, ?, 0, 1)", (name, unit, price),
        )
    conn.commit()
    n = conn.execute("SELECT COUNT(*) AS c FROM items").fetchone()[0]
    ver = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    conn.close()
    print(f"种子库生成: {dest} | 条目 {n} | 迁移版本 {ver} | 诊所 {clinic}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--clinic", default="彭学锋中医诊所")
    ap.add_argument("--password", default="123456")
    args = ap.parse_args()
    build(Path(args.out), args.clinic, args.password)
