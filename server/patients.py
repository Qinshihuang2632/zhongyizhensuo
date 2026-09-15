"""患者档案：登记、搜索、修改。编号 = 自增 id 补零显示（如 000012）。

必填：姓名、性别、年龄、电话、病情（多选标签，选项在系统设置→病情标签维护）；
出生日期选填（填了则显示时优先按出生日期换算年龄）。
"""
import datetime as dt
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import db

router = APIRouter(prefix="/api/patients")

_GENDERS = ("男", "女")
_LIMITS = {"name": 50, "phone": 20, "address": 100,
           "allergy_history": 500, "medical_history": 500, "note": 500}


class PatientBody(BaseModel):
    name: str
    gender: str = ""
    age: int = 0
    birth_date: str = ""
    phone: str = ""
    address: str = ""
    allergy_history: str = ""
    medical_history: str = ""
    note: str = ""
    condition_tags: list[str] = []


def get_condition_tags(conn, pid: int) -> str:
    """取患者当前病情标签 JSON（供各处快照）。"""
    row = conn.execute("SELECT condition_tags FROM patients WHERE id = ?", (pid,)).fetchone()
    return (row["condition_tags"] if row else "[]") or "[]"


def _clean_tags(tags: list[str]) -> str:
    cleaned, seen = [], set()
    for t in tags:
        t = (t or "").strip()
        if not t:
            continue
        if len(t) > 30:
            raise HTTPException(400, f"病情标签「{t}」超过 30 字")
        if t not in seen:
            seen.add(t)
            cleaned.append(t)
    if len(cleaned) > 8:
        raise HTTPException(400, "病情标签最多 8 个")
    if cleaned:
        names = {r["name"] for r in db.query("SELECT name FROM condition_tags")}
        if names:
            unknown = [t for t in cleaned if t not in names]
            if unknown:
                raise HTTPException(400, f"病情标签「{'、'.join(unknown)}」不在标签字典中，请先在系统设置里添加")
    return json.dumps(cleaned, ensure_ascii=False)


def _clean(body: PatientBody) -> tuple:
    data = {
        "name": body.name.strip(),
        "gender": body.gender.strip(),
        "age": body.age,
        "birth_date": body.birth_date.strip(),
        "phone": body.phone.strip(),
        "address": body.address.strip(),
        "allergy_history": body.allergy_history.strip(),
        "medical_history": body.medical_history.strip(),
        "note": body.note.strip(),
    }
    if not data["name"]:
        raise HTTPException(400, "姓名不能为空")
    if data["gender"] not in _GENDERS:
        raise HTTPException(400, "性别必填（男 / 女）")
    if not 1 <= data["age"] <= 130:
        raise HTTPException(400, "年龄必填，范围 1~130")
    if not data["phone"]:
        raise HTTPException(400, "电话不能为空")
    if data["birth_date"]:
        try:
            dt.datetime.strptime(data["birth_date"], "%Y-%m-%d")
        except ValueError:
            raise HTTPException(400, "出生日期格式应为 YYYY-MM-DD") from None
        if data["birth_date"] > dt.date.today().isoformat():
            raise HTTPException(400, "出生日期不能晚于今天")
    for key in ("name", "phone", "address", "allergy_history", "medical_history", "note"):
        if len(data[key]) > _LIMITS[key]:
            raise HTTPException(400, f"「{key}」长度不能超过 {_LIMITS[key]} 字")
    tags_json = _clean_tags(body.condition_tags)
    return tuple(data.values()) + (tags_json,)


def _to_dict(row) -> dict:
    d = dict(row)
    d["no"] = f"{d['id']:06d}"
    d["has_card"] = bool(d.get("card_since"))
    try:
        d["condition_tags"] = json.loads(d.get("condition_tags") or "[]")
    except Exception:
        d["condition_tags"] = []
    return d


@router.get("")
def list_patients(keyword: str = "", page: int = 1, size: int = 20, exclude_inpatient: int = 0):
    page = max(1, page)
    size = min(max(1, size), 100)
    kw = keyword.strip()
    conds = []
    if kw:
        conds.append("(name LIKE '%' || :kw || '%' OR phone LIKE '%' || :kw || '%'"
                     " OR CAST(id AS TEXT) = :kw)")
    if exclude_inpatient:
        conds.append("id NOT IN (SELECT patient_id FROM admissions WHERE status = '在院')")
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    params = {"kw": kw, "size": size, "offset": (page - 1) * size}
    total = db.one(f"SELECT COUNT(*) AS c FROM patients {where}", params)["c"]
    rows = db.query(
        f"SELECT * FROM patients {where} ORDER BY id DESC LIMIT :size OFFSET :offset", params
    )
    return {"total": total, "page": page, "size": size, "items": [_to_dict(r) for r in rows]}


@router.post("")
def create_patient(body: PatientBody):
    values = _clean(body)
    with db.tx() as conn:
        cur = conn.execute(
            "INSERT INTO patients (name, gender, age, birth_date, phone, address,"
            " allergy_history, medical_history, note, condition_tags)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", values,
        )
        return {"id": cur.lastrowid}


@router.get("/{pid}")
def get_patient(pid: int):
    row = db.one("SELECT * FROM patients WHERE id = ?", (pid,))
    if row is None:
        raise HTTPException(404, "患者不存在")
    return _to_dict(row)


@router.put("/{pid}")
def update_patient(pid: int, body: PatientBody):
    if db.one("SELECT id FROM patients WHERE id = ?", (pid,)) is None:
        raise HTTPException(404, "患者不存在")
    values = _clean(body)
    with db.tx() as conn:
        cur = conn.execute(
            "UPDATE patients SET name=?, gender=?, age=?, birth_date=?, phone=?, address=?,"
            " allergy_history=?, medical_history=?, note=?, condition_tags=?,"
            " updated_at=datetime('now','localtime') WHERE id=?", values + (pid,),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "患者不存在")
    return {"ok": True}
