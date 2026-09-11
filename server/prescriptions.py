"""中药处方：开药（划价快照）→ 付药（FIFO 扣库存）→ 收费（由 charges 模块完成）。

- total = 每剂金额 × 剂数；明细存每剂克数与单价快照。
- 付药后修改被禁止；作废（未收费）会整单退回库存。
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import audit, db, stock

router = APIRouter(prefix="/api/prescriptions")

_OWNERS = ("散户", "住院")


class RxLineBody(BaseModel):
    item_id: int
    qty: float


class RxBody(BaseModel):
    owner_type: str
    patient_id: int | None = None
    patient_name: str = ""
    doses: int = 1
    usage_method: str = ""
    note: str = ""
    lines: list[RxLineBody]


def _clean(body: RxBody, conn) -> tuple[int | None, str, list, float, float]:
    if body.owner_type not in _OWNERS:
        raise HTTPException(400, "对象类型只能是 散户 / 住院")
    if body.owner_type == "住院" and body.patient_id is None:
        raise HTTPException(400, "住院处方必须选择患者")
    if not 1 <= body.doses <= 1000:
        raise HTTPException(400, "剂数应在 1~1000 之间")
    if len(body.usage_method.strip()) > 100 or len(body.note.strip()) > 200:
        raise HTTPException(400, "用法/备注过长")
    if body.patient_id is None:
        if body.owner_type == "住院":
            raise HTTPException(400, "住院处方必须选择患者")
        name = body.patient_name.strip() or "散户"
        if len(name) > 50:
            raise HTTPException(400, "患者姓名过长")
        pid, pname = None, name
    else:
        row = conn.execute("SELECT name FROM patients WHERE id = ?", (body.patient_id,)).fetchone()
        if row is None:
            raise HTTPException(400, "所选患者不存在")
        if body.owner_type == "住院":
            adm = conn.execute(
                "SELECT id FROM admissions WHERE patient_id = ? AND status = '在院'", (body.patient_id,)
            ).fetchone()
            if adm is None:
                raise HTTPException(400, "该患者当前不在院，请先到「办理出院」办理入院")
        else:
            adm = conn.execute(
                "SELECT id FROM admissions WHERE patient_id = ? AND status = '在院'", (body.patient_id,)
            ).fetchone()
            if adm is not None:
                raise HTTPException(400, "该患者在院，住院期间费用请用「住院」对象记账")
        pid, pname = body.patient_id, row["name"]
    if not body.lines:
        raise HTTPException(400, "处方至少一味药")
    if len(body.lines) > 50:
        raise HTTPException(400, "一张处方最多 50 味药")
    lines, per_dose = [], 0.0
    for line in body.lines:
        if not 0.01 <= line.qty <= 9999:
            raise HTTPException(400, "每剂用量应在 0.01~9999 之间")
        item = conn.execute("SELECT * FROM items WHERE id = ?", (line.item_id,)).fetchone()
        if item is None or item["category"] != "中药饮片":
            raise HTTPException(400, f"「{item['name'] if item else line.item_id}」不是中药饮片，不能开入处方")
        if not item["active"]:
            raise HTTPException(400, f"「{item['name']}」已停用")
        per_dose += round(item["price"] * line.qty, 4)
        lines.append((item["id"], item["name"], item["unit"], item["price"], line.qty))
    return pid, pname, lines, round(per_dose, 2), round(per_dose * body.doses, 2)


def _dict(row, with_lines=False) -> dict:
    d = dict(row)
    d["no"] = f"CF{d['id']:06d}"
    if with_lines:
        d["lines"] = [dict(r) for r in db.query(
            "SELECT * FROM prescription_lines WHERE prescription_id = ? ORDER BY id", (d["id"],)
        )]
    return d


@router.post("")
def create(body: RxBody):
    with db.tx() as conn:
        pid, pname, lines, per_dose, total = _clean(body, conn)
        cur = conn.execute(
            "INSERT INTO prescriptions (patient_id, patient_name, owner_type, doses,"
            " usage_method, note, per_dose_total, total) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (pid, pname, body.owner_type, body.doses, body.usage_method.strip(),
             body.note.strip(), per_dose, total),
        )
        rx_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO prescription_lines (prescription_id, item_id, item_name, unit, price, qty)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [(rx_id, *line) for line in lines],
        )
    return {"id": rx_id, "no": f"CF{rx_id:06d}", "total": total}


@router.get("")
def list_rx(owner_type: str = "", status: str = "", keyword: str = "",
            page: int = 1, size: int = 20):
    page = max(1, page)
    size = min(max(1, size), 100)
    conds, params = [], {"offset": (page - 1) * size, "size": size}
    if owner_type in _OWNERS:
        conds.append("owner_type = :owner_type")
        params["owner_type"] = owner_type
    if status in ("待付药", "已付药", "已收费", "已作废"):
        conds.append("status = :status")
        params["status"] = status
    kw = keyword.strip()
    if kw:
        conds.append("(patient_name LIKE '%' || :kw || '%' OR CAST(id AS TEXT) = :kw)")
        params["kw"] = kw
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    total = db.one(f"SELECT COUNT(*) AS c FROM prescriptions {where}", params)["c"]
    rows = db.query(
        f"SELECT * FROM prescriptions {where} ORDER BY id DESC LIMIT :size OFFSET :offset", params
    )
    return {"total": total, "page": page, "size": size, "items": [_dict(r) for r in rows]}


@router.get("/{rx_id}")
def detail(rx_id: int):
    row = db.one("SELECT * FROM prescriptions WHERE id = ?", (rx_id,))
    if row is None:
        raise HTTPException(404, "处方不存在")
    return _dict(row, with_lines=True)


@router.put("/{rx_id}")
def update(rx_id: int, body: RxBody):
    with db.tx() as conn:
        row = conn.execute("SELECT status FROM prescriptions WHERE id = ?", (rx_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "处方不存在")
        if row["status"] != "待付药":
            raise HTTPException(400, f"该处方已{row['status']}，不能再修改")
        pid, pname, lines, per_dose, total = _clean(body, conn)
        conn.execute(
            "UPDATE prescriptions SET patient_id=?, patient_name=?, owner_type=?, doses=?,"
            " usage_method=?, note=?, per_dose_total=?, total=?,"
            " updated_at=datetime('now','localtime') WHERE id=?",
            (pid, pname, body.owner_type, body.doses, body.usage_method.strip(),
             body.note.strip(), per_dose, total, rx_id),
        )
        conn.execute("DELETE FROM prescription_lines WHERE prescription_id = ?", (rx_id,))
        conn.executemany(
            "INSERT INTO prescription_lines (prescription_id, item_id, item_name, unit, price, qty)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [(rx_id, *line) for line in lines],
        )
    return {"ok": True, "total": total}


@router.post("/{rx_id}/dispense")
def dispense(rx_id: int):
    """付药：按每剂用量×剂数 FIFO 扣减库存，快照成本。"""
    with db.tx() as conn:
        rx = conn.execute("SELECT * FROM prescriptions WHERE id = ?", (rx_id,)).fetchone()
        if rx is None:
            raise HTTPException(404, "处方不存在")
        if rx["status"] != "待付药":
            raise HTTPException(400, f"该处方已{rx['status']}，不能付药")
        lines = conn.execute(
            "SELECT * FROM prescription_lines WHERE prescription_id = ?", (rx_id,)
        ).fetchall()
        no = f"CF{rx_id:06d}"
        for line in lines:
            need = round(line["qty"] * rx["doses"], 4)
            cost = stock.deduct(conn, line["item_id"], need, "prescription", no)
            conn.execute("UPDATE prescription_lines SET cost = ? WHERE id = ?",
                         (cost / need if need else 0, line["id"]))
        conn.execute(
            "UPDATE prescriptions SET status='已付药', updated_at=datetime('now','localtime')"
            " WHERE id=?", (rx_id,),
        )
    return {"ok": True}


@router.post("/{rx_id}/void")
def void(rx_id: int):
    with db.tx() as conn:
        rx = conn.execute("SELECT * FROM prescriptions WHERE id = ?", (rx_id,)).fetchone()
        if rx is None:
            raise HTTPException(404, "处方不存在")
        if rx["status"] not in ("待付药", "已付药"):
            raise HTTPException(400, f"该处方已{rx['status']}，不能作废")
        no = f"CF{rx_id:06d}"
        if rx["status"] == "已付药":
            lines = conn.execute(
                "SELECT * FROM prescription_lines WHERE prescription_id = ?", (rx_id,)
            ).fetchall()
            for line in lines:
                need = round(line["qty"] * rx["doses"], 4)
                stock.restore(conn, line["item_id"], need, line["cost"], "void", no)
        conn.execute(
            "UPDATE prescriptions SET status='已作废', updated_at=datetime('now','localtime')"
            " WHERE id=?", (rx_id,),
        )
        detail = f"{no} {rx['patient_name']} {rx['total']}元"
    audit.record("作废处方", detail)
    return {"ok": True}
