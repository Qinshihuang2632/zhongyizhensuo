"""病情标签字典：系统设置中维护，供患者档案多选与统计分类使用。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import db

router = APIRouter(prefix="/api/conditions")


class TagBody(BaseModel):
    name: str


@router.get("")
def list_tags(active: int = -1):
    conds, params = [], {}
    if active in (0, 1):
        conds.append("active = :active")
        params["active"] = active
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    rows = db.query(f"SELECT * FROM condition_tags {where} ORDER BY id", params)
    return [{"id": r["id"], "name": r["name"], "active": bool(r["active"])} for r in rows]


@router.post("")
def create_tag(body: TagBody):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "标签名不能为空")
    if len(name) > 30:
        raise HTTPException(400, "标签名不能超过 30 字")
    if db.one("SELECT id FROM condition_tags WHERE name = ?", (name,)):
        raise HTTPException(409, f"标签「{name}」已存在")
    with db.tx() as conn:
        cur = conn.execute("INSERT INTO condition_tags (name) VALUES (?)", (name,))
        return {"id": cur.lastrowid, "name": name}


@router.put("/{tid}")
def update_tag(tid: int, body: TagBody):
    if db.one("SELECT id FROM condition_tags WHERE id = ?", (tid,)) is None:
        raise HTTPException(404, "标签不存在")
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "标签名不能为空")
    if len(name) > 30:
        raise HTTPException(400, "标签名不能超过 30 字")
    dup = db.one("SELECT id FROM condition_tags WHERE name = ? AND id != ?", (name, tid))
    if dup:
        raise HTTPException(409, f"标签「{name}」已存在")
    with db.tx() as conn:
        conn.execute("UPDATE condition_tags SET name = ? WHERE id = ?", (name, tid))
    return {"ok": True}


@router.post("/{tid}/toggle")
def toggle_tag(tid: int):
    row = db.one("SELECT active FROM condition_tags WHERE id = ?", (tid,))
    if row is None:
        raise HTTPException(404, "标签不存在")
    with db.tx() as conn:
        conn.execute("UPDATE condition_tags SET active = ? WHERE id = ?",
                     (0 if row["active"] else 1, tid))
    return {"ok": True, "active": not row["active"]}
