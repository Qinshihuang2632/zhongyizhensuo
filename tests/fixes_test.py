"""2026-09-11 反馈修复项自测：python tests/fixes_test.py

覆盖：合并收款/合并退费（跨单据类型、同一患者）、退费状态约束修复、
合并凭证打印、日结日期范围、月结/年结校验、低库存线修改。
前置：服务已启动且数据库为全新（未初始化）。
"""
import datetime as dt
import json
import sys
import urllib.error
import urllib.request
from urllib.parse import quote

BASE = "http://127.0.0.1:8321"
TOKEN = ""
PASS = FAIL = 0


def call(method, path, body=None, token=True, expect=200):
    req = urllib.request.Request(BASE + path, method=method)
    if token and TOKEN:
        req.add_header("X-Token", TOKEN)
    data = None
    if body is not None:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(body).encode("utf-8")
    try:
        with urllib.request.urlopen(req, data=data, timeout=10) as r:
            code, payload = r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        code = e.code
        raw = e.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"raw": raw}
    global PASS, FAIL
    if code == expect:
        PASS += 1
        print(f"  PASS  {method} {path} -> {code}")
    else:
        FAIL += 1
        print(f"  FAIL  {method} {path} -> got {code}, want {expect}: {payload}")
    return payload


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} {detail}")


def close(a, b, tol=0.011):
    return abs(a - b) <= tol


def main():
    global TOKEN
    s = call("GET", "/api/setup/status", token=False)
    if not s.get("initialized"):
        call("POST", "/api/setup/init", {"password": "123456", "clinic_name": "测试诊所A"}, token=False)
    r = call("POST", "/api/auth/login", {"username": "admin", "password": "123456"}, token=False)
    TOKEN = r.get("token", "")

    # 准备
    h1 = call("POST", "/api/items", {"category": "中药饮片", "name": "当归", "unit": "克", "price": 0.5, "cost": 0.3}).get("id")
    p1 = call("POST", "/api/items", {"category": "中成药", "name": "六味地黄丸", "unit": "盒", "price": 22.5, "cost": 15}).get("id")
    t1 = call("POST", "/api/items", {"category": "治疗项目", "name": "针灸", "unit": "次", "price": 50}).get("id")
    call("POST", "/api/stock/in", {"lines": [{"item_id": h1, "qty": 500, "cost": 0.3}, {"item_id": p1, "qty": 50, "cost": 15}]})
    pid = call("POST", "/api/patients", {"name": "张三", "gender": "男", "age": 46, "phone": "13800001111"}).get("id")
    pid2 = call("POST", "/api/patients", {"name": "李四", "gender": "女", "age": 30, "phone": "13900002222"}).get("id")

    to1 = call("POST", "/api/treatment-orders", {"owner_type": "散户", "patient_id": pid, "lines": [{"item_id": t1, "qty": 1}]})
    rx1 = call("POST", "/api/prescriptions", {"owner_type": "散户", "patient_id": pid, "doses": 3,
                                              "lines": [{"item_id": h1, "qty": 10}]})
    call("POST", f"/api/prescriptions/{rx1['id']}/dispense")
    sa1 = call("POST", "/api/sales", {"owner_type": "散户", "patient_id": pid, "lines": [{"line_type": "item", "ref_id": p1, "qty": 2}]})
    to2 = call("POST", "/api/treatment-orders", {"owner_type": "散户", "patient_id": pid2, "lines": [{"item_id": t1, "qty": 1}]})

    # ---- 合并收款（跨类型、同一患者） ----
    ch = call("POST", "/api/charges/settle-batch", {
        "method": "现金",
        "items": [{"source_type": "treatment_order", "source_id": to1["id"]},
                  {"source_type": "prescription", "source_id": rx1["id"]},
                  {"source_type": "sale", "source_id": sa1["id"]}]})
    check("合并收款金额(50+15+45=110)", close(ch.get("amount", 0), 110), str(ch))
    d = call("GET", f"/api/charges/{ch['id']}")
    check("凭证关联3张单", len(d.get("links", [])) == 3, str(d.get("links")))
    check("关联单号齐全", {l["no"][:2] for l in d.get("links", [])} == {"TO", "CF", "XC"})
    d1 = call("GET", f"/api/treatment-orders/{to1['id']}")
    d2 = call("GET", f"/api/prescriptions/{rx1['id']}")
    d3 = call("GET", f"/api/sales/{sa1['id']}")
    check("三单均已收费", d1["status"] == d2["status"] == d3["status"] == "已收费")
    r = call("POST", "/api/print/preview", {"template": "charge", "data": {"c": d}})
    html = r.get("html", "")
    check("合并凭证含三单与合计", all(x in html for x in ("TO", "CF", "XC", "110.00", "合并")))

    # 跨患者合并应拒绝
    call("POST", "/api/charges/settle-batch", {
        "items": [{"source_type": "treatment_order", "source_id": to2["id"]},
                  {"source_type": "sale", "source_id": call("POST", "/api/sales", {
                      "owner_type": "散户", "patient_id": pid,
                      "lines": [{"line_type": "item", "ref_id": p1, "qty": 1}]})["id"]}]}, expect=400)

    # ---- 合并退费（含治疗单，验证 CHECK 修复不再 500） ----
    sa2 = call("POST", "/api/sales", {"owner_type": "散户", "patient_id": pid, "lines": [{"line_type": "item", "ref_id": p1, "qty": 1}]})
    call("POST", "/api/charges/settle", {"source_type": "sale", "source_id": sa2["id"], "method": "扫码"})
    rf = call("POST", "/api/charges/refund-batch", {
        "items": [{"source_type": "treatment_order", "source_id": to1["id"]},
                  {"source_type": "sale", "source_id": sa1["id"]},
                  {"source_type": "sale", "source_id": sa2["id"]}]})
    check("合并退费金额-117.5", close(rf.get("amount", 0), -117.5), str(rf))
    check("治疗单可退(状态已退费)", call("GET", f"/api/treatment-orders/{to1['id']}")["status"] == "已退费")
    check("销售单已退费", call("GET", f"/api/sales/{sa1['id']}")["status"] == "已退费")
    lst = call("GET", "/api/stock")
    qty_map = {i["id"]: i["qty"] for i in lst.get("items", [])}
    check("退费退回库存(六味49)", close(qty_map.get(p1, 0), 49), str(qty_map))
    check("处方未被退(已收费)", call("GET", f"/api/prescriptions/{rx1['id']}")["status"] == "已收费")
    call("POST", "/api/charges/refund", {"source_type": "treatment_order", "source_id": to1["id"]}, expect=400)

    # 处方单独退费（原 500 场景之一）
    call("POST", "/api/charges/refund", {"source_type": "prescription", "source_id": rx1["id"]})
    check("处方退费(状态已退费)", call("GET", f"/api/prescriptions/{rx1['id']}")["status"] == "已退费")

    # ---- 日结日期范围 / 月结 / 年结 ----
    today = dt.date.today().isoformat()
    rep = call("GET", f"/api/reports/daily?start={today}&end={today}")
    check("日结范围聚合(收支净额0)", close(rep.get("income", 0), 0) and rep.get("count") == 4, str(rep))
    check("日结周期标签", rep.get("period") == today)
    rep2 = call("GET", f"/api/reports/daily?start={today}&end={today}")
    check("分类净额全部为0", all(close(v, 0) for v in rep2.get("by_category", {}).values()), str(rep2.get("by_category")))
    call("GET", f"/api/reports/daily?start={today}&end=2000-01-01", expect=400)
    cm = dt.date.today().strftime("%Y-%m")
    call("GET", f"/api/reports/monthly?month={cm}", expect=400)
    prev_y, prev_m = (dt.date.today().year - 1, 12) if dt.date.today().month == 1 else (dt.date.today().year, dt.date.today().month - 1)
    rep3 = call("GET", f"/api/reports/monthly?month={prev_y}-{prev_m:02d}")
    check("上月月结可出(空数据)", rep3.get("income") == 0 and rep3.get("count") == 0)
    call("GET", "/api/reports/monthly?month=bad", expect=400)
    cy = dt.date.today().year
    call("GET", f"/api/reports/yearly?year={cy}", expect=400)
    rep4 = call("GET", f"/api/reports/yearly?year={cy - 1}")
    check("去年年结可出(空数据)", rep4.get("income") == 0)
    r = call("POST", "/api/print/preview", {"template": "daily_report", "data": {**rep3, "title": "收费月结单"}})
    check("月结单打印", "收费月结单" in r.get("html", ""))

    # ---- 低库存线修改 ----
    call("PUT", f"/api/stock/{p1}/min-stock", {"min_stock": 60})
    it = call("GET", f"/api/items/{p1}")
    check("低库存线已改", it.get("min_stock") == 60)
    lst = call("GET", "/api/stock?alert=low")
    check("低库存预警生效", any(i["id"] == p1 and i["low"] for i in lst.get("items", [])))
    call("PUT", f"/api/stock/{p1}/min-stock", {"min_stock": -1}, expect=400)

    call("POST", "/api/shutdown")


if __name__ == "__main__":
    main()
    print(f"== 结果：PASS {PASS} / FAIL {FAIL} ==")
    sys.exit(1 if FAIL else 0)
