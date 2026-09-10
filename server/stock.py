"""药库：批次库存（先进先出 FIFO）、入库、库存调整（报损/盘盈亏）、库存与预警。

所有库存变动都同时写 stock_moves 流水；扣减在事务内执行，
库存不足时整体回滚并报错。
"""
import datetime as dt

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import audit, db

router = APIRouter(prefix="/api/stock")

DRUG_CATEGORIES = ("中药饮片", "中成药", "西药")
NEAR_EXPIRY_DAYS = 30


def current_qty(conn, item_id: int) -> float:
    row = conn.execute(
        "SELECT COALESCE(SUM(qty), 0) AS q FROM stock_batches WHERE item_id = ?", (item_id,)
    ).fetchone()
    return row["q"]


def _move(conn, item_id: int, direction: str, qty: float, cost: float,
          ref_type: str, ref_no: str, note: str = "") -> None:
    conn.execute(
        "INSERT INTO stock_moves (item_id, direction, qty, cost, ref_type, ref_no, note)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (item_id, direction, qty, cost, ref_type, ref_no, note),
    )


def deduct(conn, item_id: int, qty: float, ref_type: str, ref_no: str,
           move_direction: str = "出库") -> float:
    """按批次 FIFO 扣减，返回扣减成本合计。库存不足抛 400 并回滚外层事务。"""
    have = current_qty(conn, item_id)
    if have + 1e-9 < qty:
        item = conn.execute("SELECT name FROM items WHERE id = ?", (item_id,)).fetchone()
        raise HTTPException(400, f"「{item['name']}」库存不足：现有 {have:g}，需要 {qty:g}")
    remain, cost_total = qty, 0.0
    for b in conn.execute(
        "SELECT * FROM stock_batches WHERE item_id = ? AND qty > 0 ORDER BY id", (item_id,)
    ).fetchall():
        if remain <= 1e-9:
            break
        take = min(b["qty"], remain)
        conn.execute("UPDATE stock_batches SET qty = qty - ? WHERE id = ?", (take, b["id"]))
        cost_total += take * b["cost"]
        remain -= take
    _move(conn, item_id, move_direction, qty, cost_total / qty if qty else 0, ref_type, ref_no)
    return round(cost_total, 4)


def restore(conn, item_id: int, qty: float, cost: float, ref_type: str, ref_no: str) -> None:
    """退回：新建一个退回批次并记流水（效期信息不追溯，见流水备注）。"""
    conn.execute(
        "INSERT INTO stock_batches (item_id, qty, cost, source) VALUES (?, ?, ?, '退回')",
        (item_id, qty, cost),
    )
    _move(conn, item_id, "退回", qty, cost, ref_type, ref_no)


# ---- 入库 ----


class InLineBody(BaseModel):
    item_id: int
    qty: float
    cost: float = 0
    batch_no: str = ""
    expiry: str = ""


class InBody(BaseModel):
    supplier: str = ""
    note: str = ""
    lines: list[InLineBody]


@router.post("/in")
def create_in(body: InBody):
    if not body.lines:
        raise HTTPException(400, "入库单至少一行")
    if len(body.lines) > 50:
        raise HTTPException(400, "一张入库单最多 50 行")
    if len(body.supplier.strip()) > 50 or len(body.note.strip()) > 200:
        raise HTTPException(400, "供应商/备注过长")
    today = dt.date.today()
    for line in body.lines:
        if not 0.01 <= line.qty <= 999999:
            raise HTTPException(400, "入库数量应在 0.01~999999 之间")
        if not 0 <= line.cost <= 999999:
            raise HTTPException(400, "进价应在 0~999999 之间")
        if line.expiry:
            try:
                d = dt.datetime.strptime(line.expiry, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(400, "效期格式应为 YYYY-MM-DD") from None
            if d < today:
                raise HTTPException(400, "效期不能早于今天")
    with db.tx() as conn:
        total = 0.0
        for line in body.lines:
            item = conn.execute("SELECT * FROM items WHERE id = ?", (line.item_id,)).fetchone()
            if item is None:
                raise HTTPException(400, f"条目不存在（id={line.item_id}）")
            if item["category"] not in DRUG_CATEGORIES:
                raise HTTPException(400, f"「{item['name']}」不是药品，不能入库")
            total += line.qty * line.cost
        cur = conn.execute(
            "INSERT INTO stock_ins (supplier, note, total_cost) VALUES (?, ?, ?)",
            (body.supplier.strip(), body.note.strip(), round(total, 2)),
        )
        in_id = cur.lastrowid
        no = f"RK{in_id:06d}"
        for line in body.lines:
            item = conn.execute("SELECT * FROM items WHERE id = ?", (line.item_id,)).fetchone()
            conn.execute(
                "INSERT INTO stock_in_lines (stock_in_id, item_id, item_name, unit, qty, cost, batch_no, expiry)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (in_id, line.item_id, item["name"], item["unit"], line.qty,
                 line.cost, line.batch_no.strip(), line.expiry),
            )
            conn.execute(
                "INSERT INTO stock_batches (item_id, qty, cost, batch_no, expiry, source)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (line.item_id, line.qty, line.cost, line.batch_no.strip(), line.expiry, no),
            )
            _move(conn, line.item_id, "入库", line.qty, line.cost, "stock_in", no, body.note.strip())
            # 最近进价同步到字典，方便后续参考
            if line.cost > 0:
                conn.execute("UPDATE items SET cost = ? WHERE id = ?", (line.cost, line.item_id))
    audit.record("入库", f"{no} 供应商:{body.supplier.strip()} 金额:{round(total, 2)}")
    return {"id": in_id, "no": no, "total_cost": round(total, 2)}


@router.get("/in")
def list_in(page: int = 1, size: int = 20, keyword: str = ""):
    page = max(1, page)
    size = min(max(1, size), 100)
    kw = keyword.strip()
    where, params = "", {"size": size, "offset": (page - 1) * size}
    if kw:
        where = ("WHERE s.supplier LIKE '%' || :kw || '%' OR s.note LIKE '%' || :kw || '%'"
                 " OR CAST(s.id AS TEXT) = :kw OR EXISTS (SELECT 1 FROM stock_in_lines l"
                 " WHERE l.stock_in_id = s.id AND l.item_name LIKE '%' || :kw || '%')")
        params["kw"] = kw
    total = db.one(f"SELECT COUNT(*) AS c FROM stock_ins s {where}", params)["c"]
    rows = db.query(
        f"SELECT s.*, (SELECT COUNT(*) FROM stock_in_lines l WHERE l.stock_in_id = s.id) AS lines_count"
        f" FROM stock_ins s {where} ORDER BY s.id DESC LIMIT :size OFFSET :offset", params,
    )
    items = []
    for r in rows:
        d = dict(r)
        d["no"] = f"RK{d['id']:06d}"
        items.append(d)
    return {"total": total, "page": page, "size": size, "items": items}


@router.get("/in/{in_id}")
def get_in(in_id: int):
    row = db.one("SELECT * FROM stock_ins WHERE id = ?", (in_id,))
    if row is None:
        raise HTTPException(404, "入库单不存在")
    d = dict(row)
    d["no"] = f"RK{d['id']:06d}"
    d["lines"] = [dict(r) for r in db.query(
        "SELECT * FROM stock_in_lines WHERE stock_in_id = ? ORDER BY id", (in_id,)
    )]
    return d


# ---- 库存与预警 ----


@router.get("")
def list_stock(category: str = "", keyword: str = "", alert: str = "", page: int = 1, size: int = 50):
    """库存列表：qty=现存量，low=低库存，near_expiry=30天内到期批次数。"""
    page = max(1, page)
    size = min(max(1, size), 500)
    conds = ["i.category IN ('中药饮片', '中成药', '西药')", "i.active = 1"]
    params = {"size": size, "offset": (page - 1) * size}
    kw = keyword.strip()
    if category in DRUG_CATEGORIES:
        conds.append("i.category = :category")
        params["category"] = category
    if kw:
        conds.append("(i.name LIKE '%' || :kw || '%' OR CAST(i.id AS TEXT) = :kw)")
        params["kw"] = kw
    where = "WHERE " + " AND ".join(conds)
    rows = db.query(
        "SELECT i.*, COALESCE(b.qty, 0) AS qty,"
        " (SELECT COUNT(*) FROM stock_batches sb WHERE sb.item_id = i.id AND sb.qty > 0"
        "   AND sb.expiry != '' AND sb.expiry <= date('now', 'localtime', '+30 days')) AS near_expiry"
        f" FROM items i LEFT JOIN (SELECT item_id, SUM(qty) AS qty FROM stock_batches GROUP BY item_id) b"
        f" ON b.item_id = i.id {where} ORDER BY i.category, i.id LIMIT :size OFFSET :offset",
        params,
    )
    out = []
    for r in rows:
        d = dict(r)
        d["no"] = f"{d['id']:06d}"
        d["low"] = d["min_stock"] > 0 and d["qty"] <= d["min_stock"]
        if alert == "low" and not d["low"]:
            continue
        if alert == "near_expiry" and d["near_expiry"] == 0:
            continue
        out.append(d)
    return {"total": len(out), "page": 1, "size": len(out) or 1, "items": out}


@router.get("/{item_id}/batches")
def item_batches(item_id: int):
    rows = db.query(
        "SELECT * FROM stock_batches WHERE item_id = ? AND qty > 0 ORDER BY id", (item_id,)
    )
    return [dict(r) for r in rows]


# ---- 库存调整（报损 / 盘盈亏） ----


class AdjustBody(BaseModel):
    item_id: int
    delta: float
    note: str = ""


@router.post("/adjust")
def adjust(body: AdjustBody):
    if body.delta == 0:
        raise HTTPException(400, "调整数量不能为 0")
    if abs(body.delta) > 999999:
        raise HTTPException(400, "调整数量过大")
    with db.tx() as conn:
        item = conn.execute("SELECT * FROM items WHERE id = ?", (body.item_id,)).fetchone()
        if item is None or item["category"] not in DRUG_CATEGORIES:
            raise HTTPException(400, "条目不存在或不是药品")
        if body.delta < 0:
            deduct(conn, body.item_id, -body.delta, "adjust", "调整", move_direction="调整")
            direction = "报损/盘亏"
        else:
            cost = item["cost"]
            conn.execute(
                "INSERT INTO stock_batches (item_id, qty, cost, source) VALUES (?, ?, ?, '盘盈')",
                (body.item_id, body.delta, cost),
            )
            _move(conn, body.item_id, "调整", body.delta, cost, "adjust", "盘盈")
            direction = "盘盈"
        detail = f"{item['name']} {direction} {abs(body.delta):g}{item['unit']} {body.note.strip()}"
    audit.record("库存调整", detail)
    return {"ok": True}


@router.get("/moves")
def list_moves(item_id: int = 0, direction: str = "", keyword: str = "",
               start: str = "", end: str = "", page: int = 1, size: int = 20):
    page = max(1, page)
    size = min(max(1, size), 200)
    conds, params = [], {"offset": (page - 1) * size, "size": size}
    if item_id:
        conds.append("m.item_id = :item_id")
        params["item_id"] = item_id
    if direction in ("入库", "出库", "退回", "调整"):
        conds.append("m.direction = :direction")
        params["direction"] = direction
    kw = keyword.strip()
    if kw:
        conds.append("(i.name LIKE '%' || :kw || '%' OR m.ref_no LIKE '%' || :kw || '%')")
        params["kw"] = kw
    if start:
        conds.append("date(m.created_at) >= :start")
        params["start"] = start
    if end:
        conds.append("date(m.created_at) <= :end")
        params["end"] = end
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    total = db.one(
        f"SELECT COUNT(*) AS c FROM stock_moves m JOIN items i ON i.id = m.item_id {where}", params
    )["c"]
    rows = db.query(
        "SELECT m.*, i.name AS item_name, i.unit, i.category FROM stock_moves m"
        f" JOIN items i ON i.id = m.item_id {where} ORDER BY m.id DESC LIMIT :size OFFSET :offset",
        params,
    )
    return {"total": total, "page": page, "size": size, "items": [dict(r) for r in rows]}
