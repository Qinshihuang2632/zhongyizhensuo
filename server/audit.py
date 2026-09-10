"""操作留痕：关键动作（登录、收费、退费、预交款、作废、库存调整、出院结算、
修改密码、恢复备份）写一行审计记录，供「系统设置 → 操作留痕」查看。"""
from . import db


def record(action: str, detail: str = "") -> None:
    try:
        with db.tx() as conn:
            conn.execute("INSERT INTO audit_log (action, detail) VALUES (?, ?)",
                         (action, detail[:500]))
    except Exception:
        # 留痕失败不阻断业务
        pass


def list_log(page: int = 1, size: int = 50) -> dict:
    page = max(1, page)
    size = min(max(1, size), 200)
    total = db.one("SELECT COUNT(*) AS c FROM audit_log")["c"]
    rows = db.query(
        "SELECT * FROM audit_log ORDER BY id DESC LIMIT ? OFFSET ?", (size, (page - 1) * size)
    )
    return {"total": total, "page": page, "size": size,
            "items": [dict(r) for r in rows]}
