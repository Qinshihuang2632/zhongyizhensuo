"""患者档案：登记、搜索、修改。编号 = 自增 id 补零显示（如 000012）。

必填：姓名、性别、年龄、电话；出生日期选填（填了则显示时优先按出生日期换算年龄）。
"""
import datetime as dt

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
    return tuple(data.values())


def _to_dict(row) -> dict:
    d = dict(row)
    d["no"] = f"{d['id']:06d}"
    return d


@router.get("")
def list_patients(keyword: str = "", page: int = 1, size: int = 20):
    page = max(1, page)
    size = min(max(1, size), 100)
    kw = keyword.strip()
    where = ("WHERE :kw = '' OR name LIKE '%' || :kw || '%' "
             "OR phone LIKE '%' || :kw || '%' OR CAST(id AS TEXT) = :kw")
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
            " allergy_history, medical_history, note)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", values,
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
            " allergy_history=?, medical_history=?, note=?,"
            " updated_at=datetime('now','localtime') WHERE id=?", values + (pid,),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "患者不存在")
    return {"ok": True}
