"""收费结算：散户现结（支持同患者多单合并收款）/ 退费（支持多单合并退费）/
住院预交款。住院单据在出院时统一结算（见 admissions）。

每张收费/退费记录通过 charge_links 关联其覆盖的业务单据；单笔操作同样写
link，保证凭证打印与退费追溯口径一致。所有动作写审计。
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import audit, db, stock

router = APIRouter(prefix="/api/charges")

_METHODS = ("现金", "扫码")
_SOURCES = ("treatment_order", "prescription", "sale")

# source_type -> (表名, 单号前缀, 待结算状态)
_SOURCE_TABLE = {
    "treatment_order": ("treatment_orders", "TO", "待收费"),
    "prescription": ("prescriptions", "CF", "已付药"),
    "sale": ("sales", "XC", "待收费"),
}


def _doc_no(source_type: str, source_id: int) -> str:
    return f"{_SOURCE_TABLE[source_type][1]}{source_id:06d}"


def _load_doc(conn, source_type: str, source_id: int):
    if source_type not in _SOURCES:
        raise HTTPException(400, "单据类型不合法")
    table, _prefix, _pending = _SOURCE_TABLE[source_type]
    doc = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (source_id,)).fetchone()
    if doc is None:
        raise HTTPException(404, f"单据不存在（{_SOURCE_TABLE[source_type][1]}{source_id:06d}）")
    return doc


def _check_same_patient(docs) -> None:
    """合并结算仅限同一患者：有档案的按档案 ID，散户无档案的按姓名。"""
    with_pid = [d for d in docs if d["patient_id"] is not None]
    if with_pid:
        if len(with_pid) != len(docs):
            raise HTTPException(400, "已建档与未建档的单据不能合并结算")
        pid = with_pid[0]["patient_id"]
        if any(d["patient_id"] != pid for d in docs):
            raise HTTPException(400, "只能合并同一患者的单据")
    else:
        if len({d["patient_name"] for d in docs}) > 1:
            raise HTTPException(400, "只能合并同一患者的单据")


def _insert_charge(conn, no_type: str, docs, amount: float, method: str,
                   note: str = "", admission_id: int | None = None) -> int:
    """docs: [(doc_row, source_type, source_id), ...]"""
    from .patients import get_condition_tags
    first = docs[0][0]
    pid = first["patient_id"] if all(d[0]["patient_id"] == first["patient_id"] for d in docs) else None
    owner = docs[0][0]["owner_type"] if len({d[0]["owner_type"] for d in docs}) == 1 else "散户"
    tags = get_condition_tags(conn, pid) if pid else "[]"
    cur = conn.execute(
        "INSERT INTO charges (no_type, owner_type, patient_id, patient_name, admission_id,"
        " source_type, source_id, amount, method, note, condition_tags)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (no_type, owner, pid, first["patient_name"], admission_id,
         docs[0][1], docs[0][2], amount, method, note, tags),
    )
    charge_id = cur.lastrowid
    for doc, st, sid in docs:
        amt = round(doc["total"], 2)
        if no_type == "退费":
            amt = -amt  # 退费链接金额带符号，保证按类别净额统计正确
        conn.execute(
            "INSERT INTO charge_links (charge_id, source_type, source_id, amount)"
            " VALUES (?, ?, ?, ?)", (charge_id, st, sid, amt),
        )
    return charge_id


class SettleBody(BaseModel):
    source_type: str
    source_id: int
    method: str = "现金"


class BatchBody(BaseModel):
    items: list[SettleBody]
    method: str = "现金"


class DepositBody(BaseModel):
    admission_id: int
    amount: float
    method: str = "现金"
    note: str = ""


def _do_settle(conn, items: list[SettleBody], method: str) -> tuple[int, float]:
    if method not in _METHODS:
        raise HTTPException(400, "收款方式只能是 现金 / 扫码")
    if not items:
        raise HTTPException(400, "请选择要收费的单据")
    if len(items) > 50:
        raise HTTPException(400, "一次最多合并 50 张单据")
    docs = []
    for it in items:
        doc = _load_doc(conn, it.source_type, it.source_id)
        pending = _SOURCE_TABLE[it.source_type][2]
        if doc["status"] != pending:
            raise HTTPException(400, f"单据 {_doc_no(it.source_type, it.source_id)} 已{doc['status']}，无需收费")
        if doc["owner_type"] != "散户":
            raise HTTPException(400, "住院单据在出院时统一结算，不能在此收费")
        docs.append((doc, it.source_type, it.source_id))
    _check_same_patient([d for d, _st, _sid in docs])
    total = round(sum(d["total"] for d, _st, _sid in docs), 2)
    charge_id = _insert_charge(conn, "收费", docs, total, method)
    for doc, st, sid in docs:
        table = _SOURCE_TABLE[st][0]
        conn.execute(
            f"UPDATE {table} SET status='已收费', updated_at=datetime('now','localtime') WHERE id=?",
            (sid,),
        )
    detail = ("+".join(_doc_no(st, sid) for _d, st, sid in docs)
              + f" {docs[0][0]['patient_name']} {total}元 {method}")
    return charge_id, total, detail


@router.post("/settle")
def settle(body: SettleBody):
    with db.tx() as conn:
        charge_id, total, detail = _do_settle(conn, [SettleBody(**body.model_dump())], body.method)
    audit.record("收费", detail)
    return {"id": charge_id, "no": f"SF{charge_id:06d}", "amount": total}


@router.post("/settle-batch")
def settle_batch(body: BatchBody):
    with db.tx() as conn:
        charge_id, total, detail = _do_settle(conn, body.items, body.method)
    audit.record("合并收费", detail)
    return {"id": charge_id, "no": f"SF{charge_id:06d}", "amount": total}


def _restore_source_stock(conn, source_type: str, source_id: int) -> None:
    no = _doc_no(source_type, source_id)
    if source_type == "prescription":
        rx = conn.execute("SELECT * FROM prescriptions WHERE id = ?", (source_id,)).fetchone()
        for line in conn.execute(
            "SELECT * FROM prescription_lines WHERE prescription_id = ?", (source_id,)
        ).fetchall():
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
    # treatment_order 无库存动作


def _do_refund(conn, items: list[SettleBody]) -> tuple[int, float, str]:
    if not items:
        raise HTTPException(400, "请选择要退费的单据")
    if len(items) > 50:
        raise HTTPException(400, "一次最多合并退费 50 张单据")
    docs = []
    for it in items:
        doc = _load_doc(conn, it.source_type, it.source_id)
        if doc["status"] != "已收费":
            raise HTTPException(400, f"单据 {_doc_no(it.source_type, it.source_id)} 状态为「{doc['status']}」，只有已收费的散户单据可以退费")
        if doc["owner_type"] != "散户":
            raise HTTPException(400, "住院单据费用随出院结算处理，不能在此退费")
        docs.append((doc, it.source_type, it.source_id))
    _check_same_patient([d for d, _st, _sid in docs])
    # 收款方式取原收费记录
    method = "现金"
    for _doc, st, sid in docs:
        orig = conn.execute(
            "SELECT c.method FROM charges c JOIN charge_links l ON l.charge_id = c.id"
            " WHERE c.no_type IN ('收费', '出院结算') AND l.source_type = ? AND l.source_id = ?"
            " ORDER BY c.id DESC LIMIT 1", (st, sid),
        ).fetchone()
        if orig is None:
            orig = conn.execute(
                "SELECT method FROM charges WHERE no_type IN ('收费', '出院结算')"
                " AND source_type = ? AND source_id = ? ORDER BY id DESC LIMIT 1", (st, sid),
            ).fetchone()
        if orig:
            method = orig["method"]
            break
    total = round(sum(d["total"] for d, _st, _sid in docs), 2)
    charge_id = _insert_charge(conn, "退费", docs, -total, method, note="散户退费")
    for doc, st, sid in docs:
        _restore_source_stock(conn, st, sid)
        table = _SOURCE_TABLE[st][0]
        conn.execute(
            f"UPDATE {table} SET status='已退费', updated_at=datetime('now','localtime') WHERE id=?",
            (sid,),
        )
    detail = ("+".join(_doc_no(st, sid) for _d, st, sid in docs)
              + f" {docs[0][0]['patient_name']} -{total}元")
    return charge_id, total, detail


class RefundBody(BaseModel):
    source_type: str
    source_id: int


@router.post("/refund")
def refund(body: RefundBody):
    with db.tx() as conn:
        charge_id, total, detail = _do_refund(conn, [SettleBody(source_type=body.source_type, source_id=body.source_id)])
    audit.record("退费", detail)
    return {"id": charge_id, "no": f"SF{charge_id:06d}", "amount": -total}


@router.post("/refund-batch")
def refund_batch(body: BatchBody):
    with db.tx() as conn:
        charge_id, total, detail = _do_refund(conn, body.items)
    audit.record("合并退费", detail)
    return {"id": charge_id, "no": f"SF{charge_id:06d}", "amount": -total}


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
            " amount, method, note, condition_tags) VALUES ('预交款', '住院', ?, ?, ?, ?, ?, ?, ?)",
            (adm["patient_id"], adm["patient_name"], adm["id"], body.amount,
             body.method, body.note.strip(), adm["condition_tags"] or "[]"),
        )
        charge_id = cur.lastrowid
        detail = f"ZY{adm['id']:06d} {adm['patient_name']} 预交{body.amount}元 {body.method}"
    audit.record("预交款", detail)
    return {"id": charge_id, "no": f"SF{charge_id:06d}"}


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
            try:
                d["source_no"] = _doc_no(d["source_type"], d["source_id"])
            except KeyError:
                d["source_no"] = ""
        items.append(d)
    return {"total": total, "page": page, "size": size, "items": items}


@router.get("/{charge_id}")
def detail(charge_id: int):
    row = db.one("SELECT * FROM charges WHERE id = ?", (charge_id,))
    if row is None:
        raise HTTPException(404, "收费记录不存在")
    d = dict(row)
    d["no"] = f"SF{d['id']:06d}"
    links = []
    for l in db.query(
        "SELECT * FROM charge_links WHERE charge_id = ? ORDER BY id", (charge_id,)
    ):
        try:
            no = _doc_no(l["source_type"], l["source_id"])
        except KeyError:
            no = ""
        links.append({"source_type": l["source_type"], "source_id": l["source_id"],
                      "no": no, "amount": l["amount"]})
    d["links"] = links
    d["source_no"] = links[0]["no"] if len(links) == 1 else f"{len(links)}张单据合并"
    return d
