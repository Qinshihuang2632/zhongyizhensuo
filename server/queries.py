"""查询中心与日结：收费流水、出入库流水、综合汇总、日结。"""
import datetime as dt

from fastapi import APIRouter

from . import db

router = APIRouter(prefix="/api")

_SOURCE_LABEL = {"treatment_order": "治疗项目", "prescription": "中药处方", "sale": "药品销售", "": "其他"}


@router.get("/queries/patients-summary")
def patients_summary(keyword: str = "", start: str = "", end: str = ""):
    """按患者汇总：就诊/消费次数与金额（含住院）。"""
    conds, params = [], {}
    kw = keyword.strip()
    if kw:
        conds.append("(c.patient_name LIKE '%' || :kw || '%' OR CAST(c.patient_id AS TEXT) = :kw)")
        params["kw"] = kw
    if start:
        conds.append("date(c.created_at) >= :start")
        params["start"] = start
    if end:
        conds.append("date(c.created_at) <= :end")
        params["end"] = end
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    rows = db.query(
        "SELECT c.patient_id, c.patient_name, COUNT(*) AS times,"
        " SUM(CASE WHEN c.amount > 0 THEN c.amount ELSE 0 END) AS paid,"
        " SUM(CASE WHEN c.amount < 0 THEN -c.amount ELSE 0 END) AS refunded"
        f" FROM charges c {where}"
        " GROUP BY c.patient_id, c.patient_name ORDER BY paid DESC LIMIT 200", params,
    )
    return [dict(r) for r in rows]


@router.get("/reports/daily")
def daily(date: str = ""):
    date = date or dt.date.today().isoformat()
    try:
        dt.datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise ValueError("日期格式应为 YYYY-MM-DD") from None
    by_type = {r["no_type"]: r["s"] for r in db.query(
        "SELECT no_type, ROUND(SUM(amount), 2) AS s FROM charges"
        " WHERE date(created_at) = ? GROUP BY no_type", (date,)
    )}
    by_method = {r["method"]: r["s"] for r in db.query(
        "SELECT method, ROUND(SUM(amount), 2) AS s FROM charges"
        " WHERE date(created_at) = ? AND no_type IN ('收费', '出院结算') GROUP BY method", (date,)
    )}
    by_category = {r["st"]: r["s"] for r in db.query(
        "SELECT source_type AS st, ROUND(SUM(amount), 2) AS s FROM charges"
        " WHERE date(created_at) = ? AND no_type IN ('收费', '出院结算', '退费')"
        " GROUP BY source_type", (date,),
    )}
    categories = {
        _SOURCE_LABEL.get(k, k): v for k, v in by_category.items()
    }
    count = db.one("SELECT COUNT(*) AS c FROM charges WHERE date(created_at) = ?", (date,))["c"]
    income = round(by_type.get("收费", 0) + by_type.get("出院结算", 0)
                   + by_type.get("预交款", 0) + by_type.get("退费", 0), 2)
    return {
        "date": date,
        "income": income,
        "count": count,
        "by_type": by_type,
        "by_method": by_method,
        "by_category": categories,
    }
