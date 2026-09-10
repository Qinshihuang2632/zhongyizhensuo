"""字典管理：药品与治疗项目统一条目（items）+ 协定处方（formulas）。

- items 四类条目（中药饮片/中成药/西药/治疗项目）统一存放，划价、销售、
  库存都围绕 item id 展开；停用（active=0）后不可再被登记/开单。
- 协定处方 = 自家定好的成方：整方价 + 药品组成。
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import db

router = APIRouter(prefix="/api")

CATEGORIES = ("中药饮片", "中成药", "西药", "治疗项目")
DRUG_CATEGORIES = ("中药饮片", "中成药", "西药")


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


@router.post("/items")
def create_item(body: ItemBody):
    values = _clean_item(body)
    with db.tx() as conn:
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
