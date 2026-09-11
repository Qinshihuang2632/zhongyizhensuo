"""查询中心与报表：收费流水、出入库流水、患者汇总、日结（支持日期范围）、月结、年结。

月结/年结只对"已结束"的周期开放打印：当月/当年未结束时拒绝，
当月/当年至今的数据通过日结的日期范围查看。
"""
import calendar
import datetime as dt

from fastapi import APIRouter, HTTPException

from . import db

router = APIRouter(prefix="/api")

_SOURCE_LABEL = {"treatment_order": "治疗项目", "prescription": "中药处方", "sale": "药品销售", "": "其他"}


def _aggregate(start: str, end: str) -> dict:
    params = {"start": start, "end": end}
    conds = "date(created_at) >= :start AND date(created_at) <= :end"
    by_type = {r["no_type"]: r["s"] for r in db.query(
        f"SELECT no_type, ROUND(SUM(amount), 2) AS s FROM charges WHERE {conds} GROUP BY no_type",
        params,
    )}
    by_method = {r["method"]: r["s"] for r in db.query(
        f"SELECT method, ROUND(SUM(amount), 2) AS s FROM charges WHERE {conds}"
        " AND no_type IN ('收费', '出院结算') GROUP BY method", params,
    )}
    by_category = {r["st"]: r["s"] for r in db.query(
        f"SELECT COALESCE(l.source_type, c.source_type, '') AS st,"
        " ROUND(SUM(COALESCE(l.amount, c.amount)), 2) AS s"
        f" FROM charges c LEFT JOIN charge_links l ON l.charge_id = c.id WHERE {conds}"
        " AND c.no_type IN ('收费', '出院结算', '退费')"
        " GROUP BY COALESCE(l.source_type, c.source_type, '')", params,
    )}
    count = db.one(f"SELECT COUNT(*) AS c FROM charges WHERE {conds}", params)["c"]
    income = round(sum(by_type.values()), 2)
    return {
        "start": start,
        "end": end,
        "period": start if start == end else f"{start} 至 {end}",
        "income": income,
        "count": count,
        "by_type": by_type,
        "by_method": by_method,
        "by_category": {_SOURCE_LABEL.get(k, k): v for k, v in by_category.items()},
    }


def _validate_date(s: str) -> dt.date:
    try:
        return dt.datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "日期格式应为 YYYY-MM-DD") from None


@router.get("/queries/patients-summary")
def patients_summary(keyword: str = "", start: str = "", end: str = ""):
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
def daily(date: str = "", start: str = "", end: str = ""):
    """单日或日期范围汇总（范围可用于查看当月至今）。"""
    if start and end:
        s, e = _validate_date(start), _validate_date(end)
        if e < s:
            raise HTTPException(400, "结束日期不能早于开始日期")
        return _aggregate(start, end)
    date = date or dt.date.today().isoformat()
    _validate_date(date)
    return _aggregate(date, date)


@router.get("/reports/monthly")
def monthly(month: str = ""):
    try:
        y, m = map(int, month.split("-"))
        assert 1 <= m <= 12
    except (ValueError, AssertionError):
        raise HTTPException(400, "月份格式应为 YYYY-MM") from None
    last = calendar.monthrange(y, m)[1]
    end = dt.date(y, m, last)
    if end >= dt.date.today():
        raise HTTPException(400, f"{y}年{m}月尚未结束，不能出月结单；当月数据请在日结中用日期范围查看")
    return _aggregate(f"{y:04d}-{m:02d}-01", end.isoformat())


@router.get("/reports/yearly")
def yearly(year: int = 0):
    end = dt.date(year, 12, 31)
    if end >= dt.date.today():
        raise HTTPException(400, f"{year}年尚未结束，不能出年结单；当年数据请在日结中用日期范围查看")
    return _aggregate(f"{year:04d}-01-01", end.isoformat())
