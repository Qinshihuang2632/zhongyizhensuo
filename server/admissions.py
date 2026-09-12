"""出入院（极简）：入院登记 → 在院（销售/处方/治疗记账 + 预交款）→ 出院结算。

出院时把该患者在院期间所有「待收费」单据统一收费，并与预交款对冲：
差额补收（出院结算），多退（退费记录）。打印《出院汇总清单》分治疗/成药/中药三节，
末尾附固化医嘱（系统设置可维护，默认文案内置）。
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import audit, charges, db

router = APIRouter(prefix="/api/admissions")

DEFAULT_DISCHARGE_ORDERS = (
    "1、按时服药，忌生冷、辛辣、油腻之品；\n"
    "2、注意休息，避免劳累，保持心情舒畅；\n"
    "3、如症状加重或出现不适，请及时就诊；\n"
    "4、遵医嘱复诊。"
)


class AdmBody(BaseModel):
    patient_id: int
    note: str = ""


class DischargeBody(BaseModel):
    method: str = "现金"


class OrdersBody(BaseModel):
    custom_orders: str = ""


@router.put("/{adm_id}/orders")
def save_orders(adm_id: int, body: OrdersBody):
    """出院个性化医嘱（打印时附加在固定医嘱之后）。"""
    if len(body.custom_orders.strip()) > 500:
        raise HTTPException(400, f"个性化医嘱不能超过 500 字（当前 {len(body.custom_orders.strip())} 字）")
    row = db.one("SELECT id FROM admissions WHERE id = ?", (adm_id,))
    if row is None:
        raise HTTPException(404, "住院记录不存在")
    with db.tx() as conn:
        conn.execute("UPDATE admissions SET custom_orders = ? WHERE id = ?",
                     (body.custom_orders.strip(), adm_id))
    return {"ok": True}


@router.post("")
def create(body: AdmBody):
    if len(body.note.strip()) > 200:
        raise HTTPException(400, "备注过长")
    with db.tx() as conn:
        p = conn.execute("SELECT * FROM patients WHERE id = ?", (body.patient_id,)).fetchone()
        if p is None:
            raise HTTPException(400, "患者不存在")
        dup = conn.execute(
            "SELECT id FROM admissions WHERE patient_id = ? AND status = '在院'", (body.patient_id,)
        ).fetchone()
        if dup:
            raise HTTPException(400, f"该患者已有在院记录（ZY{dup['id']:06d}），请先办理出院")
        cur = conn.execute(
            "INSERT INTO admissions (patient_id, patient_name, note) VALUES (?, ?, ?)",
            (body.patient_id, p["name"], body.note.strip()),
        )
        adm_id = cur.lastrowid
    audit.record("入院登记", f"ZY{adm_id:06d} {p['name']}")
    return {"id": adm_id, "no": f"ZY{adm_id:06d}"}


@router.get("")
def list_admissions(status: str = "", keyword: str = "", page: int = 1, size: int = 20):
    page = max(1, page)
    size = min(max(1, size), 100)
    conds, params = [], {"offset": (page - 1) * size, "size": size}
    if status in ("在院", "已出院"):
        conds.append("status = :status")
        params["status"] = status
    kw = keyword.strip()
    if kw:
        conds.append("(patient_name LIKE '%' || :kw || '%' OR CAST(id AS TEXT) = :kw)")
        params["kw"] = kw
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    total = db.one(f"SELECT COUNT(*) AS c FROM admissions {where}", params)["c"]
    rows = db.query(
        f"SELECT * FROM admissions {where} ORDER BY id DESC LIMIT :size OFFSET :offset", params
    )
    items = []
    for r in rows:
        d = dict(r)
        d["no"] = f"ZY{d['id']:06d}"
        items.append(d)
    return {"total": total, "page": page, "size": size, "items": items}


def _settle_pending(conn, adm: dict, method: str) -> None:
    """把该患者在院期间的待收费单据统一收费（每单一条收费记录）。"""
    pid = adm["patient_id"]
    # 表名 → charges.source_type 统一用单数键，与收费模块一致
    for table, source_type in (("treatment_orders", "treatment_order"),
                               ("prescriptions", "prescription"), ("sales", "sale")):
        pending_status = "已付药" if table == "prescriptions" else "待收费"
        rows = conn.execute(
            f"SELECT id, total, patient_name, owner_type FROM {table}"
            f" WHERE patient_id = ? AND owner_type = '住院' AND status = ?", (pid, pending_status),
        ).fetchall()
        for doc in rows:
            conn.execute(
                "INSERT INTO charges (no_type, owner_type, patient_id, patient_name,"
                " admission_id, source_type, source_id, amount, method)"
                " VALUES ('收费', '住院', ?, ?, ?, ?, ?, ?, ?)",
                (pid, doc["patient_name"], adm["id"], source_type, doc["id"], doc["total"], method),
            )
            conn.execute(
                f"UPDATE {table} SET status='已收费', updated_at=datetime('now','localtime') WHERE id=?",
                (doc["id"],),
            )


def _totals(conn, adm: dict) -> dict:
    pid = adm["patient_id"]
    deposits = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS s FROM charges"
        " WHERE admission_id = ? AND no_type IN ('预交款')", (adm["id"],),
    ).fetchone()["s"]
    billed = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS s FROM charges"
        " WHERE admission_id = ? AND no_type IN ('收费', '出院结算')", (adm["id"],),
    ).fetchone()["s"]
    refunds = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS s FROM charges"
        " WHERE admission_id = ? AND no_type = '退费'", (adm["id"],),
    ).fetchone()["s"]
    docs = {}
    pending = 0.0
    for table in ("treatment_orders", "sales", "prescriptions"):
        time_col = ", treatment_time" if table == "treatment_orders" else ""
        rows = [dict(r) for r in conn.execute(
            f"SELECT id, total, status, created_at{time_col} FROM {table}"
            " WHERE patient_id = ? AND owner_type = '住院' AND status != '已作废'"
            " ORDER BY id", (pid,),
        ).fetchall()]
        docs[table] = rows
        # 处方付药后（已付药）即视为待收费；治疗/销售单本身以「待收费」为待结状态
        pending_statuses = ("已付药",) if table == "prescriptions" else ("待收费",)
        pending += sum(r["total"] for r in rows if r["status"] in pending_statuses)
    return {
        "deposits": round(deposits, 2),
        "billed": round(billed, 2),
        "refunds": round(refunds, 2),
        "pending": round(pending, 2),
        "balance": round(billed + pending - deposits + refunds, 2),
        "treatments": docs["treatment_orders"],
        "sales": docs["sales"],
        "prescriptions": docs["prescriptions"],
    }


@router.get("/{adm_id}")
def detail(adm_id: int):
    row = db.one("SELECT * FROM admissions WHERE id = ?", (adm_id,))
    if row is None:
        raise HTTPException(404, "住院记录不存在")
    d = dict(row)
    d["no"] = f"ZY{d['id']:06d}"
    p = db.one("SELECT * FROM patients WHERE id = ?", (d["patient_id"],))
    d["patient"] = dict(p) if p else {}
    t = _totals(db.connect(), d)
    d.update(t)
    d["discharge_orders"] = db.get_setting("discharge_orders") or DEFAULT_DISCHARGE_ORDERS
    return d


@router.post("/{adm_id}/discharge")
def discharge(adm_id: int, body: DischargeBody):
    if body.method not in ("现金", "扫码"):
        raise HTTPException(400, "收款方式只能是 现金 / 扫码")
    with db.tx() as conn:
        adm = conn.execute("SELECT * FROM admissions WHERE id = ?", (adm_id,)).fetchone()
        if adm is None:
            raise HTTPException(404, "住院记录不存在")
        if adm["status"] != "在院":
            raise HTTPException(400, "该患者已出院")
        _settle_pending(conn, adm, "住院结算")
        # 与预交款对冲
        row = conn.execute(
            "SELECT"
            " (SELECT COALESCE(SUM(amount),0) FROM charges WHERE admission_id=:a AND no_type IN ('收费','出院结算')) AS billed,"
            " (SELECT COALESCE(SUM(amount),0) FROM charges WHERE admission_id=:a AND no_type='预交款') AS deposits,"
            " (SELECT COALESCE(SUM(amount),0) FROM charges WHERE admission_id=:a AND no_type='退费') AS refunds",
            {"a": adm_id},
        ).fetchone()
        balance = round(row["billed"] - row["deposits"] + row["refunds"], 2)
        if balance > 0:
            conn.execute(
                "INSERT INTO charges (no_type, owner_type, patient_id, patient_name, admission_id,"
                " amount, method, note) VALUES ('出院结算', '住院', ?, ?, ?, ?, ?, '出院补收')",
                (adm["patient_id"], adm["patient_name"], adm_id, balance, body.method),
            )
        elif balance < 0:
            conn.execute(
                "INSERT INTO charges (no_type, owner_type, patient_id, patient_name, admission_id,"
                " amount, method, note) VALUES ('退费', '住院', ?, ?, ?, ?, ?, '出院退回多缴预交款')",
                (adm["patient_id"], adm["patient_name"], adm_id, balance, "现金"),
            )
        conn.execute(
            "UPDATE admissions SET status='已出院', discharged_at=datetime('now','localtime') WHERE id=?",
            (adm_id,),
        )
        detail = f"ZY{adm_id:06d} {adm['patient_name']} 结算{balance}元 {body.method}"
    audit.record("出院结算", detail)
    return {"ok": True, "balance": balance}
