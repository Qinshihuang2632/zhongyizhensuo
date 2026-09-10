"""收费结算：散户现结 / 退费 / 住院预交款。住院单据在出院时统一结算（见 admissions）。

收费动作与单据状态更新在同一事务；每次动作写审计。
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import audit, db, stock

router = APIRouter(prefix="/api/charges")

_METHODS = ("现金", "扫码")
_SOURCES = ("treatment_order", "prescription", "sale")

_SOURCE_TABLE = {
    "treatment_order": ("treatment_orders", "TO", "待收费"),
    "prescription": ("prescriptions", "CF", "已付药"),
    "sale": ("sales", "XC", "待收费"),
}


def _doc_no(source_type: str, source_id: int) -> str:
    table, prefix, _pending = _SOURCE_TABLE[source_type]
    return f"{prefix}{source_id:06d}"


def _restore_source_stock(conn, source_type: str, source_id: int) -> None:
    no = _doc_no(source_type, source_id)
    if source_type == "prescription":
        rx = conn.execute("SELECT * FROM prescriptions WHERE id = ?", (source_id,)).fetchone()
        lines = conn.execute(
            "SELECT * FROM prescription_lines WHERE prescription_id = ?", (source_id,)
        ).fetchall()
        for line in lines:
            need = round(line["qty"] * rx["doses"], 4)
            stock.restore(conn, line["item_id"], need, line["cost"], "void", no)
    elif source_type == "sale":
        for line in conn.execute(
            "SELECT * FROM sale_lines WHERE sale_id = ?", (source_id,)
        ).fetchall():
            if line["line_type"] == "item":
                stock.restore(conn, line["ref_id"], line["qty"],
                              line["cost"] / line["qty"] if line["qty"] else 0, "void", no)
            else:
                comps = conn.execute(
                    "SELECT fi.item_id, fi.qty FROM formula_items fi WHERE fi.formula_id = ?",
                    (line["ref_id"],),
                ).fetchall()
                total_units = sum(c["qty"] for c in comps) * line["qty"]
                per_unit = line["cost"] / total_units if total_units else 0
                for comp in comps:
                    stock.restore(conn, comp["item_id"],
                                  round(comp["qty"] * line["qty"], 4), per_unit, "void", no)


class SettleBody(BaseModel):
    source_type: str
    source_id: int
    method: str = "现金"


class DepositBody(BaseModel):
    admission_id: int
    amount: float
    method: str = "现金"
    note: str = ""


class RefundBody(BaseModel):
    source_type: str
    source_id: int


@router.post("/settle")
def settle(body: SettleBody):
    if body.method not in _METHODS:
        raise HTTPException(400, "收款方式只能是 现金 / 扫码")
    if body.source_type not in _SOURCES:
        raise HTTPException(400, "单据类型不合法")
    with db.tx() as conn:
        table = _SOURCE_TABLE[body.source_type][0]
        pending_status = _SOURCE_TABLE[body.source_type][2]
        doc = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (body.source_id,)).fetchone()
        if doc is None:
            raise HTTPException(404, "单据不存在")
        if doc["status"] != pending_status:
            raise HTTPException(400, f"该单据已{doc['status']}，无需收费")
        cur = conn.execute(
            "INSERT INTO charges (no_type, owner_type, patient_id, patient_name,"
            " source_type, source_id, amount, method)"
            " VALUES ('收费', ?, ?, ?, ?, ?, ?, ?)",
            (doc["owner_type"], doc["patient_id"], doc["patient_name"],
             body.source_type, body.source_id, doc["total"], body.method),
        )
        charge_id = cur.lastrowid
        conn.execute(
            f"UPDATE {table} SET status='已收费', updated_at=datetime('now','localtime') WHERE id=?",
            (body.source_id,),
        )
        detail = (f"{_doc_no(body.source_type, body.source_id)} {doc['patient_name']}"
                  f" {doc['total']}元 {body.method}")
    audit.record("收费", detail)
    return {"id": charge_id, "no": f"SF{charge_id:06d}", "amount": doc["total"]}


@router.post("/deposit")
def deposit(body: DepositBody):
    if body.method not in _METHODS:
        raise HTTPException(400, "收款方式只能是 现金 / 扫码")
    if not 0.01 <= body.amount <= 999999:
        raise HTTPException(400, "金额应在 0.01~999999 之间")
    with db.tx() as conn:
        adm = conn.execute("SELECT * FROM admissions WHERE id = ?", (body.admission_id,)).fetchone()
        if adm is None or adm["status"] != "在院":
            raise HTTPException(400, "住院记录不存在或已出院")
        cur = conn.execute(
            "INSERT INTO charges (no_type, owner_type, patient_id, patient_name, admission_id,"
            " amount, method, note) VALUES ('预交款', '住院', ?, ?, ?, ?, ?, ?)",
            (adm["patient_id"], adm["patient_name"], adm["id"], body.amount,
             body.method, body.note.strip()),
        )
        charge_id = cur.lastrowid
        detail = f"ZY{adm['id']:06d} {adm['patient_name']} 预交{body.amount}元 {body.method}"
    audit.record("预交款", detail)
    return {"id": charge_id, "no": f"SF{charge_id:06d}"}


@router.post("/refund")
def refund(body: RefundBody):
    if body.source_type not in _SOURCES:
        raise HTTPException(400, "单据类型不合法")
    with db.tx() as conn:
        table = _SOURCE_TABLE[body.source_type][0]
        doc = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (body.source_id,)).fetchone()
        if doc is None:
            raise HTTPException(404, "单据不存在")
        if doc["status"] != "已收费":
            raise HTTPException(400, "只有已收费的散户单据可以退费")
        orig = conn.execute(
            "SELECT * FROM charges WHERE no_type='收费' AND source_type=? AND source_id=?"
            " ORDER BY id DESC LIMIT 1", (body.source_type, body.source_id),
        ).fetchone()
        method = orig["method"] if orig else "现金"
        _restore_source_stock(conn, body.source_type, body.source_id)
        cur = conn.execute(
            "INSERT INTO charges (no_type, owner_type, patient_id, patient_name,"
            " source_type, source_id, amount, method, note)"
            " VALUES ('退费', ?, ?, ?, ?, ?, ?, ?, ?)",
            (doc["owner_type"], doc["patient_id"], doc["patient_name"],
             body.source_type, body.source_id, -doc["total"], method, "散户退费"),
        )
        charge_id = cur.lastrowid
        conn.execute(
            f"UPDATE {table} SET status='已退费', updated_at=datetime('now','localtime') WHERE id=?",
            (body.source_id,),
        )
        detail = f"{_doc_no(body.source_type, body.source_id)} {doc['patient_name']} -{doc['total']}元"
    audit.record("退费", detail)
    return {"id": charge_id, "no": f"SF{charge_id:06d}", "amount": -doc["total"]}


@router.get("")
def list_charges(no_type: str = "", method: str = "", keyword: str = "",
                 start: str = "", end: str = "", page: int = 1, size: int = 20):
    page = max(1, page)
    size = min(max(1, size), 200)
    conds, params = [], {"offset": (page - 1) * size, "size": size}
    if no_type in ("收费", "退费", "预交款", "出院结算"):
        conds.append("no_type = :no_type")
        params["no_type"] = no_type
    if method in _METHODS:
        conds.append("method = :method")
        params["method"] = method
    kw = keyword.strip()
    if kw:
        conds.append("(patient_name LIKE '%' || :kw || '%' OR CAST(id AS TEXT) = :kw)")
        params["kw"] = kw
    if start:
        conds.append("date(created_at) >= :start")
        params["start"] = start
    if end:
        conds.append("date(created_at) <= :end")
        params["end"] = end
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    total = db.one(f"SELECT COUNT(*) AS c FROM charges {where}", params)["c"]
    rows = db.query(
        f"SELECT * FROM charges {where} ORDER BY id DESC LIMIT :size OFFSET :offset", params
    )
    items = []
    for r in rows:
        d = dict(r)
        d["no"] = f"SF{d['id']:06d}"
        if d["source_type"] and d["source_id"]:
            d["source_no"] = _doc_no(d["source_type"], d["source_id"])
        items.append(d)
    return {"total": total, "page": page, "size": size, "items": items}


@router.get("/{charge_id}")
def detail(charge_id: int):
    row = db.one("SELECT * FROM charges WHERE id = ?", (charge_id,))
    if row is None:
        raise HTTPException(404, "收费记录不存在")
    d = dict(row)
    d["no"] = f"SF{d['id']:06d}"
    if d["source_type"] and d["source_id"]:
        d["source_no"] = _doc_no(d["source_type"], d["source_id"])
        table = _SOURCE_TABLE[d["source_type"]][0]
        src = db.one(f"SELECT total, note FROM {table} WHERE id = ?", (d["source_id"],))
        if src:
            d["source_total"] = src["total"]
    return d
