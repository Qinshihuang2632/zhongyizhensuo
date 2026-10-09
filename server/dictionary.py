"""字典管理：药品与治疗项目统一条目（items）+ 协定处方（formulas）。

- items 四类条目（中药饮片/中成药/西药/治疗项目）统一存放，划价、销售、
  库存都围绕 item id 展开；停用（active=0）后不可再被登记/开单。
- 协定处方 = 自家定好的成方：整方价 + 药品组成。
- 查重：名称去空格归一后相同、或名称包含且价格相近的条目禁止重复录入。
"""
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import db

router = APIRouter(prefix="/api")

CATEGORIES = ("中药饮片", "中成药", "西药", "治疗项目")
DRUG_CATEGORIES = ("中药饮片", "中成药", "西药")
PRICE_CLOSE = 0.5  # 价格差在此之内视为"价格相近"


def _norm_name(s: str) -> str:
    """名称归一：去全部空白与常见分隔符后小写比较。"""
    return re.sub(r"[\s·・、,，.。/\\\-—()（）]+", "", (s or "")).lower()


def _find_duplicate(conn, name: str, price: float, exclude_id: int | None = None):
    """查重：返回 (已有条目, 重复类型)；类型=同名/相似同名近价/相似。"""
    norm = _norm_name(name)
    if not norm:
        return None, None
    for r in conn.execute("SELECT * FROM items").fetchall():
        if exclude_id and r["id"] == exclude_id:
            continue
        rn = _norm_name(r["name"])
        if not rn:
            continue
        close = abs(r["price"] - price) <= PRICE_CLOSE
        if rn == norm:
            return r, ("同名" if close else "同名不同价")
        if close and (norm in rn or rn in norm):
            return r, "相似同名近价"
    return None, None


class ItemBody(BaseModel):
    category: str
    name: str
    unit: str = ""
    spec: str = ""
    price: float = 0
    cost: float = 0
    min_stock: float = 0
    manufacturer: str = ""
    note: str = ""
    active: bool = True


_ITEM_TEXTS = {"unit": ("单位", 20), "spec": ("规格", 50),
               "manufacturer": ("厂家", 50), "note": ("备注", 200)}


def _clean_item(body: ItemBody) -> tuple:
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "名称不能为空")
    if len(name) > 50:
        raise HTTPException(400, "名称长度不能超过 50 字")
    if body.category not in CATEGORIES:
        raise HTTPException(400, "类别不合法")
    if not 0 <= body.price <= 999999:
        raise HTTPException(400, "售价应在 0~999999 之间")
    if not 0 <= body.cost <= 999999:
        raise HTTPException(400, "进价应在 0~999999 之间")
    if not 0 <= body.min_stock <= 999999:
        raise HTTPException(400, "最低库存应在 0~999999 之间")
    texts = {"unit": body.unit.strip(), "spec": body.spec.strip(),
             "manufacturer": body.manufacturer.strip(), "note": body.note.strip()}
    for key, (label, limit) in _ITEM_TEXTS.items():
        if len(texts[key]) > limit:
            raise HTTPException(400, f"「{label}」长度不能超过 {limit} 字")
    return (body.category, name, texts["unit"], texts["spec"],
            round(body.price, 2), round(body.cost, 2), body.min_stock,
            texts["manufacturer"], texts["note"], 1 if body.active else 0)


def _item_dict(row) -> dict:
    d = dict(row)
    d["no"] = f"{d['id']:06d}"
    d["active"] = bool(d["active"])
    return d


@router.get("/items")
def list_items(category: str = "", keyword: str = "", active: int = -1,
               page: int = 1, size: int = 50):
    page = max(1, page)
    size = min(max(1, size), 500)
    conds, params = [], {"offset": (page - 1) * size, "size": size}
    if category:
        if category not in CATEGORIES:
            raise HTTPException(400, "类别不合法")
        conds.append("category = :category")
        params["category"] = category
    kw = keyword.strip()
    if kw:
        conds.append("(name LIKE '%' || :kw || '%' OR spec LIKE '%' || :kw || '%'"
                     " OR manufacturer LIKE '%' || :kw || '%' OR CAST(id AS TEXT) = :kw)")
        params["kw"] = kw
    if active in (0, 1):
        conds.append("active = :active")
        params["active"] = active
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    total = db.one(f"SELECT COUNT(*) AS c FROM items {where}", params)["c"]
    rows = db.query(
        f"SELECT * FROM items {where} ORDER BY category, id DESC LIMIT :size OFFSET :offset",
        params,
    )
    return {"total": total, "page": page, "size": size, "items": [_item_dict(r) for r in rows]}


def _enforce_duplicate(conn, name: str, price: float, exclude_id: int | None = None) -> None:
    row, kind = _find_duplicate(conn, name, price, exclude_id)
    if row is None:
        return
    info = f"「{row['name']}（{row['category']}，{row['price']:.2f}元/{row['unit'] or '无单位'}，编号{row['id']:06d}）」"
    if kind == "相似同名近价":
        raise HTTPException(409, f"存在相近条目{info}，名称与价格相近，请勿重复录入")
    if kind == "同名不同价":
        raise HTTPException(409, f"已存在同名条目{info}；如需调整价格请改用列表中的「修改」功能")
    raise HTTPException(409, f"已存在相同条目{info}，请勿重复录入")


@router.get("/items/duplicate-check")
def duplicate_check(name: str, price: float = 0, exclude_id: int = 0):
    """录入前预检：返回是否命中查重及已有条目信息。"""
    with db.connect() as conn:
        row, kind = _find_duplicate(conn, name, price, exclude_id or None)
    if row is None:
        return {"duplicate": False}
    return {"duplicate": True, "kind": kind,
            "item": {"id": row["id"], "name": row["name"], "category": row["category"],
                     "unit": row["unit"], "price": row["price"]}}


@router.post("/items")
def create_item(body: ItemBody):
    values = _clean_item(body)
    with db.tx() as conn:
        _enforce_duplicate(conn, values[1], values[4])
        cur = conn.execute(
            "INSERT INTO items (category, name, unit, spec, price, cost, min_stock,"
            " manufacturer, note, active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", values,
        )
        return {"id": cur.lastrowid}


@router.get("/items/{iid}")
def get_item(iid: int):
    row = db.one("SELECT * FROM items WHERE id = ?", (iid,))
    if row is None:
        raise HTTPException(404, "条目不存在")
    return _item_dict(row)


@router.put("/items/{iid}")
def update_item(iid: int, body: ItemBody):
    if db.one("SELECT id FROM items WHERE id = ?", (iid,)) is None:
        raise HTTPException(404, "条目不存在")
    values = _clean_item(body)
    with db.tx() as conn:
        _enforce_duplicate(conn, values[1], values[4], exclude_id=iid)
        conn.execute(
            "UPDATE items SET category=?, name=?, unit=?, spec=?, price=?, cost=?, min_stock=?,"
            " manufacturer=?, note=?, active=?, updated_at=datetime('now','localtime')"
            " WHERE id=?", values + (iid,),
        )
    return {"ok": True}


# ---- 协定处方 ----


class FormulaLineBody(BaseModel):
    item_id: int
    qty: float = 1


class FormulaBody(BaseModel):
    name: str
    price: float = 0
    note: str = ""
    active: bool = True
    lines: list[FormulaLineBody] = []


def _validate_formula(body: FormulaBody) -> tuple:
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "方名不能为空")
    if len(name) > 50:
        raise HTTPException(400, "方名长度不能超过 50 字")
    if not 0 <= body.price <= 999999:
        raise HTTPException(400, "整方价应在 0~999999 之间")
    if len(body.note.strip()) > 200:
        raise HTTPException(400, "备注长度不能超过 200 字")
    if len(body.lines) > 50:
        raise HTTPException(400, "一张方最多 50 味药")
    cleaned = []
    for line in body.lines:
        if not 0.01 <= line.qty <= 9999:
            raise HTTPException(400, "组成数量应在 0.01~9999 之间")
        cleaned.append((line.item_id, line.qty))
    return name, round(body.price, 2), body.note.strip(), 1 if body.active else 0, cleaned


def _check_formula_items(conn, lines) -> None:
    for item_id, _qty in lines:
        row = conn.execute("SELECT category FROM items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            raise HTTPException(400, f"组成药品不存在（id={item_id}）")
        if row["category"] not in DRUG_CATEGORIES:
            raise HTTPException(400, "协定处方的组成只能是药品（饮片/中成药/西药）")


def _formula_dict(row, lines_by_fid: dict) -> dict:
    d = dict(row)
    d["no"] = f"{d['id']:06d}"
    d["active"] = bool(d["active"])
    d["lines"] = lines_by_fid.get(d["id"], [])
    return d


def _fetch_formula_lines(formula_ids: list[int] | None = None) -> dict:
    sql = ("SELECT fi.formula_id, fi.item_id, fi.qty, i.name AS item_name, i.unit, i.price"
           " FROM formula_items fi JOIN items i ON i.id = fi.item_id")
    params: tuple = ()
    if formula_ids is not None:
        if not formula_ids:
            return {}
        sql += " WHERE fi.formula_id IN (%s)" % ",".join("?" * len(formula_ids))
        params = tuple(formula_ids)
    grouped: dict[int, list] = {}
    for r in db.query(sql, params):
        grouped.setdefault(r["formula_id"], []).append(dict(r))
    return grouped


@router.get("/formulas")
def list_formulas(keyword: str = ""):
    kw = keyword.strip()
    if kw:
        rows = db.query(
            "SELECT * FROM formulas WHERE name LIKE '%' || ? || '%' ORDER BY id DESC", (kw,)
        )
    else:
        rows = db.query("SELECT * FROM formulas ORDER BY id DESC")
    grouped = _fetch_formula_lines([r["id"] for r in rows])
    return [_formula_dict(r, grouped) for r in rows]


@router.post("/formulas")
def create_formula(body: FormulaBody):
    name, price, note, active, lines = _validate_formula(body)
    with db.tx() as conn:
        _check_formula_items(conn, lines)
        cur = conn.execute(
            "INSERT INTO formulas (name, price, note, active) VALUES (?, ?, ?, ?)",
            (name, price, note, active),
        )
        fid = cur.lastrowid
        conn.executemany(
            "INSERT INTO formula_items (formula_id, item_id, qty) VALUES (?, ?, ?)",
            [(fid, item_id, qty) for item_id, qty in lines],
        )
    return {"id": fid}


@router.get("/formulas/{fid}")
def get_formula(fid: int):
    row = db.one("SELECT * FROM formulas WHERE id = ?", (fid,))
    if row is None:
        raise HTTPException(404, "协定处方不存在")
    grouped = _fetch_formula_lines([fid])
    return _formula_dict(row, grouped)


@router.put("/formulas/{fid}")
def update_formula(fid: int, body: FormulaBody):
    if db.one("SELECT id FROM formulas WHERE id = ?", (fid,)) is None:
        raise HTTPException(404, "协定处方不存在")
    name, price, note, active, lines = _validate_formula(body)
    with db.tx() as conn:
        _check_formula_items(conn, lines)
        conn.execute(
            "UPDATE formulas SET name=?, price=?, note=?, active=?,"
            " updated_at=datetime('now','localtime') WHERE id=?",
            (name, price, note, active, fid),
        )
        conn.execute("DELETE FROM formula_items WHERE formula_id = ?", (fid,))
        conn.executemany(
            "INSERT INTO formula_items (formula_id, item_id, qty) VALUES (?, ?, ?)",
            [(fid, item_id, qty) for item_id, qty in lines],
        )
    return {"ok": True}
