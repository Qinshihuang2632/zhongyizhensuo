"""保健卡：治愈判定授予、权益窗口、开始使用与登录提醒。

窗口规则（"自获卡之日起"第 1 天 = 获卡当日）：
  第 1 轮 = 第 61~90 天；此后每 180 天一轮，取该轮第 151~180 天
  （即第 241~270、421~450……天）。每轮窗口 30 天，期内任选连续 7 天使用，
  自开始日起 7 个自然日内有效，每轮限用一次。
提醒规则：窗口生效日前 7 天起提醒，至窗口结束；确认后不再提醒（跨重启）。
"""
import datetime as dt

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import audit, db

router = APIRouter(prefix="/api/cards")

FIRST_START_OFFSET = 60    # 第 61 天（获卡日为第 1 天）
WINDOW_DAYS = 30           # 每轮窗口 30 天（第 61-90 / 151-180 天）
WINDOW_SPACING = 180       # 此后每 180 天一轮
USAGE_DAYS = 7             # 每轮使用期为连续 7 个自然日
REMIND_AHEAD = 7           # 生效日前 7 天起提醒
MAX_WINDOWS = 60


def _today() -> dt.date:
    return dt.date.today()


def generate_windows(since: dt.date, horizon_days: int = 550) -> list[dict]:
    """生成获卡日后的权益窗口，直到超出展望期（默认覆盖前 3 轮）。"""
    out = []
    n = 1
    while n <= MAX_WINDOWS:
        start = since + dt.timedelta(days=FIRST_START_OFFSET + WINDOW_SPACING * (n - 1))
        if (start - _today()).days > horizon_days:
            break
        out.append({
            "index": n,
            "start": start.isoformat(),
            "end": (start + dt.timedelta(days=WINDOW_DAYS - 1)).isoformat(),
        })
        n += 1
    return out


def _window_status(win: dict, used: dict | None, confirmed: bool) -> dict:
    today = _today()
    start = dt.date.fromisoformat(win["start"])
    end = dt.date.fromisoformat(win["end"])
    row = dict(win)
    row["remind_confirmed"] = confirmed
    if used:
        row["status"] = "已使用"
        row["usage_start"] = used["start_date"]
        row["usage_end"] = used["end_date"]
    elif today < start:
        row["status"] = "未生效"
        row["days_to_start"] = (start - today).days
    elif today <= end:
        row["status"] = "可使用"
    else:
        row["status"] = "已过期"
    return row


def _card_row(pid: int):
    row = db.one("SELECT id, name, phone, card_since FROM patients WHERE id = ?", (pid,))
    if row is None:
        raise HTTPException(404, "患者不存在")
    return row


@router.get("/reminders")
def reminders():
    """待提醒列表：窗口生效日前 7 天起、至窗口结束，未使用且未确认。"""
    today = _today()
    out = []
    rows = db.query("SELECT id, name, phone, card_since FROM patients WHERE card_since != ''")
    for p in rows:
        since = dt.date.fromisoformat(p["card_since"])
        usages = {u["window_index"] for u in db.query(
            "SELECT window_index FROM card_usages WHERE patient_id = ?", (p["id"],))}
        confirmed = {r["window_index"] for r in db.query(
            "SELECT window_index FROM card_reminders WHERE patient_id = ?", (p["id"],))}
        for win in generate_windows(since, horizon_days=REMIND_AHEAD + 40):
            start = dt.date.fromisoformat(win["start"])
            end = dt.date.fromisoformat(win["end"])
            if start - dt.timedelta(days=REMIND_AHEAD) > today:
                break  # 窗口按时间升序，后续更远
            if win["index"] in usages or win["index"] in confirmed:
                continue
            if today > end:
                continue
            out.append({
                "patient_id": p["id"],
                "patient_name": p["name"],
                "phone": p["phone"],
                "window_index": win["index"],
                "start": win["start"],
                "end": win["end"],
                "effective": today >= start,
                "days_to_start": (start - today).days,
            })
            break  # 每位患者同一时间最多提醒一个窗口（最早的未确认窗口）
    out.sort(key=lambda x: (x["start"], x["patient_id"]))
    return out


@router.post("/{pid}/grant")
def grant(pid: int, body: dict | None = None):
    since = (body or {}).get("since") or _today().isoformat()
    try:
        d = dt.date.fromisoformat(since)
    except ValueError:
        raise HTTPException(400, "获卡日期格式应为 YYYY-MM-DD") from None
    if d > _today():
        raise HTTPException(400, "获卡日期不能晚于今天")
    row = _card_row(pid)
    if row["card_since"]:
        raise HTTPException(409, f"该患者已有保健卡（获卡于 {row['card_since']}）")
    with db.tx() as conn:
        conn.execute("UPDATE patients SET card_since = ?, updated_at=datetime('now','localtime') WHERE id = ?",
                     (d.isoformat(), pid))
    audit.record("授予保健卡", f"{row['name']} 获卡日 {d.isoformat()}")
    return {"ok": True, "since": d.isoformat()}


@router.get("/{pid}")
def card_detail(pid: int):
    row = _card_row(pid)
    if not row["card_since"]:
        return {"has_card": False, "since": "", "windows": []}
    since = dt.date.fromisoformat(row["card_since"])
    usages = {u["window_index"]: u for u in db.query(
        "SELECT * FROM card_usages WHERE patient_id = ?", (pid,))}
    confirmed = {r["window_index"] for r in db.query(
        "SELECT window_index FROM card_reminders WHERE patient_id = ?", (pid,))}
    windows = []
    for win in generate_windows(since):
        windows.append(_window_status(win, usages.get(win["index"]), win["index"] in confirmed))
    return {"has_card": True, "since": row["card_since"], "windows": windows}


@router.post("/{pid}/start")
def start_usage(pid: int, body: dict):
    win_index = body.get("window_index")
    start_date = (body.get("start_date") or "").strip()
    if not win_index or not start_date:
        raise HTTPException(400, "缺少轮次或开始日期")
    row = _card_row(pid)
    if not row["card_since"]:
        raise HTTPException(400, "该患者没有保健卡")
    since = dt.date.fromisoformat(row["card_since"])
    wins = {w["index"]: w for w in generate_windows(since)}
    win = wins.get(win_index)
    if win is None:
        raise HTTPException(400, "权益轮次不存在")
    used = db.one("SELECT * FROM card_usages WHERE patient_id = ? AND window_index = ?",
                  (pid, win_index))
    if used:
        raise HTTPException(400, f"该轮权益已使用（{used['start_date']} ~ {used['end_date']}）")
    try:
        s = dt.date.fromisoformat(start_date)
    except ValueError:
        raise HTTPException(400, "开始日期格式应为 YYYY-MM-DD") from None
    w_start = dt.date.fromisoformat(win["start"])
    w_end = dt.date.fromisoformat(win["end"])
    if s < w_start or s + dt.timedelta(days=USAGE_DAYS - 1) > w_end:
        raise HTTPException(
            400, f"开始日期须使连续 {USAGE_DAYS} 天完整落在权益窗口内（{win['start']} ~ {win['end']}）")
    e = s + dt.timedelta(days=USAGE_DAYS - 1)
    # 权益归属标签：取不晚于开始日的最近一次入院的标签快照；无住院则用患者当前标签
    from .patients import get_condition_tags
    adm = db.one(
        "SELECT condition_tags FROM admissions WHERE patient_id = ? AND id = ("
        " SELECT MAX(id) FROM admissions WHERE patient_id = ?)", (pid, pid))
    tags = (adm["condition_tags"] if adm and adm["condition_tags"] not in (None, "", "[]")
            else get_condition_tags(db.connect(), pid)) or "[]"
    with db.tx() as conn:
        conn.execute(
            "INSERT INTO card_usages (patient_id, window_index, start_date, end_date, condition_tags)"
            " VALUES (?, ?, ?, ?, ?)", (pid, win_index, s.isoformat(), e.isoformat(), tags))
    audit.record("权益开始使用", f"{row['name']} 第{win_index}轮 {s.isoformat()} ~ {e.isoformat()}")
    return {"ok": True, "start": s.isoformat(), "end": e.isoformat()}


@router.post("/{pid}/reminders/{win_index}/confirm")
def confirm_reminder(pid: int, win_index: int):
    row = _card_row(pid)
    exists = db.one("SELECT id FROM card_reminders WHERE patient_id = ? AND window_index = ?",
                    (pid, win_index))
    if not exists:
        with db.tx() as conn:
            conn.execute("INSERT INTO card_reminders (patient_id, window_index) VALUES (?, ?)",
                         (pid, win_index))
    return {"ok": True}
