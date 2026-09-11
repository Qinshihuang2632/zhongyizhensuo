"""治疗项目登记：住院/散户患者的治疗单。

- 登记时按字典当前售价做快照（item_name/unit/price 存入明细），合计即划价金额。
- 状态流转：待收费 →（M5 收费）已收费；待收费可改可作废，作废留痕不删。
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import db

router = APIRouter(prefix="/api/treatment-orders")

_OWNERS = ("散户", "住院")


class OrderLineBody(BaseModel):
    item_id: int
    qty: float = 1


class OrderBody(BaseModel):
    owner_type: str
    patient_id: int | None = None
    patient_name: str = ""
    note: str = ""
    lines: list[OrderLineBody]


def _resolve_patient(conn, body: OrderBody) -> tuple[int | None, str]:
    if body.owner_type == "住院":
        if body.patient_id is None:
            raise HTTPException(400, "住院治疗单必须选择患者")
        p = conn.execute("SELECT name FROM patients WHERE id = ?", (body.patient_id,)).fetchone()
        if p is None:
            raise HTTPException(400, "所选患者不存在")
        adm = conn.execute(
            "SELECT id FROM admissions WHERE patient_id = ? AND status = '在院'", (body.patient_id,)
        ).fetchone()
        if adm is None:
            raise HTTPException(400, "该患者当前不在院，请先到「办理出院」办理入院")
        return body.patient_id, p["name"]
    if body.patient_id is None:
        name = body.patient_name.strip() or "散户"
        if len(name) > 50:
            raise HTTPException(400, "患者姓名过长")
        return None, name
    row = conn.execute("SELECT name FROM patients WHERE id = ?", (body.patient_id,)).fetchone()
    if row is None:
        raise HTTPException(400, "所选患者不存在")
    return body.patient_id, row["name"]


def _build_lines(conn, lines: list[OrderLineBody]) -> tuple[list, float]:
    if not lines:
        raise HTTPException(400, "至少登记一个治疗项目")
    if len(lines) > 50:
        raise HTTPException(400, "一张治疗单最多 50 行")
    out, total = [], 0.0
    for line in lines:
        if not 0.01 <= line.qty <= 9999:
            raise HTTPException(400, "数量应在 0.01~9999 之间")
        item = conn.execute("SELECT * FROM items WHERE id = ?", (line.item_id,)).fetchone()
        if item is None:
            raise HTTPException(400, f"项目不存在（id={line.item_id}）")
        if not item["active"]:
            raise HTTPException(400, f"「{item['name']}」已停用，不能登记")
        total += round(item["price"] * line.qty, 2)
        out.append((item["id"], item["name"], item["unit"], item["price"], line.qty))
    return out, round(total, 2)


def _order_dict(row) -> dict:
    d = dict(row)
    d["no"] = f"{d['id']:06d}"
    return d


@router.post("")
def create_order(body: OrderBody):
    if body.owner_type not in _OWNERS:
        raise HTTPException(400, "对象类型只能是 散户 / 住院")
    if len(body.note.strip()) > 200:
        raise HTTPException(400, "备注长度不能超过 200 字")
    with db.tx() as conn:
        pid, pname = _resolve_patient(conn, body)
        lines, total = _build_lines(conn, body.lines)
        cur = conn.execute(
            "INSERT INTO treatment_orders (patient_id, patient_name, owner_type, status, note, total)"
            " VALUES (?, ?, ?, '待收费', ?, ?)",
            (pid, pname, body.owner_type, body.note.strip(), total),
        )
        oid = cur.lastrowid
        conn.executemany(
            "INSERT INTO treatment_order_lines (order_id, item_id, item_name, unit, price, qty)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [(oid, *line) for line in lines],
        )
    return {"id": oid, "total": total}


@router.get("")
def list_orders(owner_type: str = "", status: str = "", keyword: str = "",
                page: int = 1, size: int = 20):
    page = max(1, page)
    size = min(max(1, size), 100)
    conds, params = [], {"offset": (page - 1) * size, "size": size}
    if owner_type in _OWNERS:
        conds.append("o.owner_type = :owner_type")
        params["owner_type"] = owner_type
    if status in ("待收费", "已收费", "已作废"):
        conds.append("o.status = :status")
        params["status"] = status
    kw = keyword.strip()
    if kw:
        conds.append("(o.patient_name LIKE '%' || :kw || '%' OR CAST(o.id AS TEXT) = :kw)")
        params["kw"] = kw
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    total = db.one(f"SELECT COUNT(*) AS c FROM treatment_orders o {where}", params)["c"]
    rows = db.query(
        "SELECT o.*, (SELECT COUNT(*) FROM treatment_order_lines l WHERE l.order_id = o.id)"
        f" AS lines_count FROM treatment_orders o {where}"
        " ORDER BY o.id DESC LIMIT :size OFFSET :offset", params,
    )
    return {"total": total, "page": page, "size": size, "items": [_order_dict(r) for r in rows]}


@router.get("/{oid}")
def get_order(oid: int):
    row = db.one("SELECT * FROM treatment_orders WHERE id = ?", (oid,))
    if row is None:
        raise HTTPException(404, "治疗单不存在")
    order = _order_dict(row)
    order["lines"] = [dict(r) for r in db.query(
        "SELECT * FROM treatment_order_lines WHERE order_id = ? ORDER BY id", (oid,)
    )]
    return order


@router.put("/{oid}")
def update_order(oid: int, body: OrderBody):
    if body.owner_type not in _OWNERS:
        raise HTTPException(400, "对象类型只能是 散户 / 住院")
    if len(body.note.strip()) > 200:
        raise HTTPException(400, "备注长度不能超过 200 字")
    with db.tx() as conn:
        row = conn.execute("SELECT status FROM treatment_orders WHERE id = ?", (oid,)).fetchone()
        if row is None:
            raise HTTPException(404, "治疗单不存在")
        if row["status"] != "待收费":
            raise HTTPException(400, f"该单已{row['status']}，不能再修改")
        pid, pname = _resolve_patient(conn, body)
        lines, total = _build_lines(conn, body.lines)
        conn.execute(
            "UPDATE treatment_orders SET patient_id=?, patient_name=?, owner_type=?,"
            " note=?, total=?, updated_at=datetime('now','localtime') WHERE id=?",
            (pid, pname, body.owner_type, body.note.strip(), total, oid),
        )
        conn.execute("DELETE FROM treatment_order_lines WHERE order_id = ?", (oid,))
        conn.executemany(
            "INSERT INTO treatment_order_lines (order_id, item_id, item_name, unit, price, qty)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [(oid, *line) for line in lines],
        )
    return {"ok": True, "total": total}


@router.post("/{oid}/void")
def void_order(oid: int):
    with db.tx() as conn:
        row = conn.execute("SELECT status FROM treatment_orders WHERE id = ?", (oid,)).fetchone()
        if row is None:
            raise HTTPException(404, "治疗单不存在")
        if row["status"] != "待收费":
            raise HTTPException(400, f"该单已{row['status']}，不能作废")
        conn.execute(
            "UPDATE treatment_orders SET status='已作废',"
            " updated_at=datetime('now','localtime') WHERE id=?", (oid,),
        )
    return {"ok": True}
