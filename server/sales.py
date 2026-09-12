"""药品销售（中成药/西药/中药饮片零售 + 协定处方整方销售）。

- 创建即按 FIFO 扣减库存（协定方按组成明细扣减），库存不足整单失败。
- 作废/退费时按快照成本退回库存。
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import audit, db, stock

router = APIRouter(prefix="/api/sales")

_OWNERS = ("散户", "住院")


class SaleLineBody(BaseModel):
    line_type: str = "item"      # item=药品 / formula=协定处方
    ref_id: int
    qty: float = 1


class SaleBody(BaseModel):
    owner_type: str
    patient_id: int | None = None
    patient_name: str = ""
    note: str = ""
    lines: list[SaleLineBody]


def _deduct_for_line(conn, line: SaleLineBody, sale_no: str) -> tuple[str, str, float, float, float]:
    """扣减一行，返回 (name, unit, price, amount, cost_total)。"""
    if not 0.01 <= line.qty <= 9999:
        raise HTTPException(400, "数量应在 0.01~9999 之间")
    if line.line_type == "item":
        item = conn.execute("SELECT * FROM items WHERE id = ?", (line.ref_id,)).fetchone()
        if item is None or item["category"] not in stock.DRUG_CATEGORIES:
            raise HTTPException(400, "只能销售药品（中成药/西药/中药饮片）")
        if not item["active"]:
            raise HTTPException(400, f"「{item['name']}」已停用")
        cost = stock.deduct(conn, item["id"], line.qty, "sale", sale_no)
        amount = round(item["price"] * line.qty, 2)
        return item["name"], item["unit"], item["price"], amount, cost
    elif line.line_type == "formula":
        f = conn.execute("SELECT * FROM formulas WHERE id = ?", (line.ref_id,)).fetchone()
        if f is None or not f["active"]:
            raise HTTPException(400, "协定处方不存在或已停用")
        comps = conn.execute(
            "SELECT fi.item_id, fi.qty, i.name FROM formula_items fi"
            " JOIN items i ON i.id = fi.item_id WHERE fi.formula_id = ?", (line.ref_id,)
        ).fetchall()
        if not comps:
            raise HTTPException(400, f"「{f['name']}」没有组成明细，请先在字典中补全")
        cost_total = 0.0
        for comp in comps:
            need = round(comp["qty"] * line.qty, 4)
            cost_total += stock.deduct(conn, comp["item_id"], need, "sale", sale_no)
        amount = round(f["price"] * line.qty, 2)
        return f["name"], "剂", f["price"], amount, cost_total
    raise HTTPException(400, "行类型不合法")


def _restore_sale(conn, sale_id: int, ref_no: str) -> None:
    for line in conn.execute(
        "SELECT * FROM sale_lines WHERE sale_id = ?", (sale_id,)
    ).fetchall():
        if line["line_type"] == "item":
            stock.restore(conn, line["ref_id"], line["qty"],
                          line["cost"] / line["qty"] if line["qty"] else 0, "void", ref_no)
        else:
            comps = conn.execute(
                "SELECT fi.item_id, fi.qty FROM formula_items fi WHERE fi.formula_id = ?",
                (line["ref_id"],),
            ).fetchall()
            total_units = sum(c["qty"] for c in comps) * line["qty"]
            per_unit = line["cost"] / total_units if total_units else 0
            for comp in comps:
                need = round(comp["qty"] * line["qty"], 4)
                stock.restore(conn, comp["item_id"], need, per_unit, "void", ref_no)


def _validate_header(body: SaleBody, conn) -> tuple[int | None, str]:
    if body.owner_type not in _OWNERS:
        raise HTTPException(400, "对象类型只能是 散户 / 住院")
    if len(body.note.strip()) > 200:
        raise HTTPException(400, "备注过长")
    if body.patient_id is None:
        if body.owner_type == "住院":
            raise HTTPException(400, "住院销售单必须选择患者")
        name = body.patient_name.strip() or "散户"
        if len(name) > 50:
            raise HTTPException(400, "患者姓名过长")
        return None, name
    row = conn.execute("SELECT name FROM patients WHERE id = ?", (body.patient_id,)).fetchone()
    if row is None:
        raise HTTPException(400, "所选患者不存在")
    if body.owner_type == "住院":
        adm = conn.execute(
            "SELECT id FROM admissions WHERE patient_id = ? AND status = '在院'", (body.patient_id,)
        ).fetchone()
        if adm is None:
            raise HTTPException(400, "该患者当前不在院，请先到「住院手续」办理入院")
    else:
        adm = conn.execute(
            "SELECT id FROM admissions WHERE patient_id = ? AND status = '在院'", (body.patient_id,)
        ).fetchone()
        if adm is not None:
            raise HTTPException(400, "该患者在院，住院期间费用请用「住院」对象记账")
    return body.patient_id, row["name"]


def _dict(row, with_lines=False) -> dict:
    d = dict(row)
    d["no"] = f"XC{d['id']:06d}"
    if with_lines:
        d["lines"] = [dict(r) for r in db.query(
            "SELECT * FROM sale_lines WHERE sale_id = ? ORDER BY id", (d["id"],)
        )]
    return d


@router.post("")
def create(body: SaleBody):
    if not body.lines:
        raise HTTPException(400, "销售单至少一行")
    if len(body.lines) > 50:
        raise HTTPException(400, "一张销售单最多 50 行")
    with db.tx() as conn:
        pid, pname = _validate_header(body, conn)
        # 先插头拿单号（扣减流水要引用），失败随事务回滚
        cur = conn.execute(
            "INSERT INTO sales (patient_id, patient_name, owner_type, note)"
            " VALUES (?, ?, ?, ?)", (pid, pname, body.owner_type, body.note.strip()),
        )
        sale_id = cur.lastrowid
        no = f"XC{sale_id:06d}"
        total = 0.0
        for line in body.lines:
            name, unit, price, amount, cost = _deduct_for_line(conn, line, no)
            conn.execute(
                "INSERT INTO sale_lines (sale_id, line_type, ref_id, item_name, unit,"
                " price, qty, amount, cost) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (sale_id, line.line_type, line.ref_id, name, unit, price, line.qty, amount, round(cost, 4)),
            )
            total += amount
        total = round(total, 2)
        conn.execute("UPDATE sales SET total = ? WHERE id = ?", (total, sale_id))
    return {"id": sale_id, "no": no, "total": total}


@router.get("")
def list_sales(owner_type: str = "", status: str = "", keyword: str = "",
               page: int = 1, size: int = 20):
    page = max(1, page)
    size = min(max(1, size), 100)
    conds, params = [], {"offset": (page - 1) * size, "size": size}
    if owner_type in _OWNERS:
        conds.append("owner_type = :owner_type")
        params["owner_type"] = owner_type
    if status in ("待收费", "已收费", "已作废", "已退费"):
        conds.append("status = :status")
        params["status"] = status
    kw = keyword.strip()
    if kw:
        conds.append("(patient_name LIKE '%' || :kw || '%' OR CAST(id AS TEXT) = :kw)")
        params["kw"] = kw
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    total = db.one(f"SELECT COUNT(*) AS c FROM sales {where}", params)["c"]
    rows = db.query(
        f"SELECT s.*, (SELECT COUNT(*) FROM sale_lines l WHERE l.sale_id = s.id) AS lines_count"
        f" FROM sales s {where} ORDER BY s.id DESC LIMIT :size OFFSET :offset", params,
    )
    return {"total": total, "page": page, "size": size, "items": [_dict(r) for r in rows]}


@router.get("/{sale_id}")
def detail(sale_id: int):
    row = db.one("SELECT * FROM sales WHERE id = ?", (sale_id,))
    if row is None:
        raise HTTPException(404, "销售单不存在")
    return _dict(row, with_lines=True)


@router.post("/{sale_id}/void")
def void(sale_id: int):
    with db.tx() as conn:
        row = conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "销售单不存在")
        if row["status"] != "待收费":
            raise HTTPException(400, f"该单已{row['status']}，不能作废；已收费请走退费")
        no = f"XC{sale_id:06d}"
        _restore_sale(conn, sale_id, no)
        conn.execute(
            "UPDATE sales SET status='已作废', updated_at=datetime('now','localtime') WHERE id=?",
            (sale_id,),
        )
        detail = f"{no} {row['patient_name']} {row['total']}元"
    audit.record("作废销售单", detail)
    return {"ok": True}
