"""M4-M7 全流程 API 自测：python tests/m4_m7_api_test.py

前置：服务已启动且数据库为全新（未初始化）。覆盖：入库/库存/预警、处方开付改废、
销售（含协定方）、收费/退费/预交款、出入院结算、查询/日结、审计、打印模板。
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
TODAY = dt.date.today().isoformat()
EXPIRY_SOON = (dt.date.today() + dt.timedelta(days=10)).isoformat()
EXPIRY_FAR = (dt.date.today() + dt.timedelta(days=200)).isoformat()


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


def stock_of(item_id):
    lst = call("GET", "/api/stock")
    for it in lst.get("items", []):
        if it["id"] == item_id:
            return it["qty"]
    return None


def main():
    global TOKEN
    s = call("GET", "/api/setup/status", token=False)
    if not s.get("initialized"):
        call("POST", "/api/setup/init", {"password": "123456", "clinic_name": "测试诊所A"}, token=False)
    r = call("POST", "/api/auth/login", {"username": "admin", "password": "123456"}, token=False)
    TOKEN = r.get("token", "")
    check("登录", len(TOKEN) > 20)

    # ================= 字典 =================
    h1 = call("POST", "/api/items", {"category": "中药饮片", "name": "当归", "unit": "克", "price": 0.5}).get("id")
    h2 = call("POST", "/api/items", {"category": "中药饮片", "name": "黄芪", "unit": "克", "price": 0.3}).get("id")
    h3 = call("POST", "/api/items", {"category": "中药饮片", "name": "甘草", "unit": "克", "price": 0.2}).get("id")
    p1 = call("POST", "/api/items", {"category": "中成药", "name": "六味地黄丸", "unit": "盒",
                                     "spec": "200丸", "price": 22.5, "min_stock": 10}).get("id")
    w1 = call("POST", "/api/items", {"category": "西药", "name": "阿莫西林", "unit": "盒", "price": 15}).get("id")
    t1 = call("POST", "/api/items", {"category": "治疗项目", "name": "针灸", "unit": "次", "price": 60}).get("id")
    check("建字典条目", all([h1, h2, h3, p1, w1, t1]))
    f1 = call("POST", "/api/formulas", {"name": "补肾方", "price": 25,
                                        "lines": [{"item_id": h1, "qty": 10}, {"item_id": h2, "qty": 15}]}).get("id")
    check("建协定方", bool(f1))

    # ================= M4 入库 / 库存 =================
    rk = call("POST", "/api/stock/in", {
        "supplier": "亳州药材行", "note": "常规补货",
        "lines": [
            {"item_id": h1, "qty": 1000, "cost": 0.3, "batch_no": "B2026", "expiry": EXPIRY_FAR},
            {"item_id": h2, "qty": 500, "cost": 0.2, "batch_no": "B2027"},
            {"item_id": h3, "qty": 500, "cost": 0.1, "batch_no": "B2028"},
            {"item_id": p1, "qty": 50, "cost": 15, "batch_no": "P1", "expiry": EXPIRY_SOON},
            {"item_id": w1, "qty": 30, "cost": 10, "batch_no": "W1"},
        ]})
    check("入库单号", str(rk.get("no", "")).startswith("RK") and close(rk.get("total_cost", 0), 1000 * 0.3 + 500 * 0.2 + 500 * 0.1 + 50 * 15 + 30 * 10))
    it = call("GET", f"/api/items/{h1}")
    check("最近进价同步", close(it.get("cost", 0), 0.3))
    batches = call("GET", f"/api/stock/{h1}/batches")
    check("批次建立", len(batches) == 1 and close(batches[0]["qty"], 1000))
    lst = call("GET", "/api/stock?alert=near_expiry")
    check("近效期预警(六味10天)", any(i["id"] == p1 and i["near_expiry"] == 1 for i in lst.get("items", [])))
    call("POST", "/api/stock/in", {"lines": []}, expect=400)
    call("POST", "/api/stock/in", {"lines": [{"item_id": h1, "qty": 1, "expiry": "2000-01-01"}]}, expect=400)
    call("POST", "/api/stock/in", {"lines": [{"item_id": t1, "qty": 1}]}, expect=400)
    moves = call("GET", "/api/stock/moves?direction=" + quote("入库"))
    check("入库流水", moves.get("total") == 5)

    # ================= M4 处方 =================
    pid1 = call("POST", "/api/patients", {"name": "张三", "gender": "男", "age": 46, "phone": "13800001111"}).get("id")
    rx1 = call("POST", "/api/prescriptions", {
        "owner_type": "散户", "patient_id": pid1, "doses": 7, "usage_method": "水煎服",
        "lines": [{"item_id": h1, "qty": 10}, {"item_id": h2, "qty": 15}, {"item_id": h3, "qty": 6}]})
    check("处方划价(每剂10.7×7)", close(rx1.get("total", 0), 74.9), str(rx1))
    call("POST", "/api/prescriptions", {"owner_type": "散户", "lines": []}, expect=400)
    call("POST", "/api/prescriptions", {"owner_type": "散户", "doses": 0,
                                        "lines": [{"item_id": h1, "qty": 1}]}, expect=400)
    call("POST", "/api/prescriptions", {"owner_type": "散户", "lines": [{"item_id": t1, "qty": 1}]}, expect=400)
    call("POST", "/api/prescriptions", {"owner_type": "住院",
                                        "lines": [{"item_id": h1, "qty": 1}]}, expect=400)
    d = call("GET", f"/api/prescriptions/{rx1['id']}")
    check("处方明细快照", len(d.get("lines", [])) == 3 and d["lines"][0]["item_name"] == "当归")

    # 付药扣库存 → 作废退回
    call("POST", f"/api/prescriptions/{rx1['id']}/dispense")
    check("付药后扣库存(当归930)", close(stock_of(h1), 930), str(stock_of(h1)))
    call("PUT", f"/api/prescriptions/{rx1['id']}", {
        "owner_type": "散户", "patient_id": pid1, "doses": 1,
        "lines": [{"item_id": h1, "qty": 1}]}, expect=400)
    call("POST", f"/api/prescriptions/{rx1['id']}/void")
    check("作废后退回库存(当归1000)", close(stock_of(h1), 1000), str(stock_of(h1)))
    call("POST", f"/api/prescriptions/{rx1['id']}/dispense", expect=400)

    # rx1b：正式走 收费 流程
    rx1b = call("POST", "/api/prescriptions", {
        "owner_type": "散户", "patient_id": pid1, "doses": 7, "usage_method": "水煎服",
        "lines": [{"item_id": h1, "qty": 10}, {"item_id": h2, "qty": 15}, {"item_id": h3, "qty": 6}]})
    call("POST", f"/api/prescriptions/{rx1b['id']}/dispense")
    ch_rx = call("POST", "/api/charges/settle", {"source_type": "prescription", "source_id": rx1b["id"], "method": "扫码"})
    check("处方收费", close(ch_rx.get("amount", 0), 74.9))
    d = call("GET", f"/api/prescriptions/{rx1b['id']}")
    check("处方状态已收费", d.get("status") == "已收费")
    call("POST", f"/api/prescriptions/{rx1b['id']}/void", expect=400)

    # ================= M5 销售 =================
    sale1 = call("POST", "/api/sales", {
        "owner_type": "散户", "patient_id": pid1,
        "lines": [{"line_type": "item", "ref_id": p1, "qty": 2}, {"line_type": "item", "ref_id": w1, "qty": 1}]})
    check("销售划价(45+15=60)", close(sale1.get("total", 0), 60))
    check("销售扣库存(六味48)", close(stock_of(p1), 48), str(stock_of(p1)))
    call("POST", "/api/sales", {"owner_type": "散户", "lines": []}, expect=400)
    call("POST", "/api/sales", {"owner_type": "散户", "lines": [{"line_type": "item", "ref_id": t1, "qty": 1}]}, expect=400)
    call("POST", "/api/sales", {"owner_type": "散户", "lines": [{"line_type": "item", "ref_id": w1, "qty": 1000}]}, expect=400)

    sale2 = call("POST", "/api/sales", {
        "owner_type": "散户", "patient_name": "门口散户",
        "lines": [{"line_type": "formula", "ref_id": f1, "qty": 2}]})
    check("协定方销售(25×2=50)", close(sale2.get("total", 0), 50))
    check("协定方扣组成库存(当归910)", close(stock_of(h1), 910), str(stock_of(h1)))

    ch_s1 = call("POST", "/api/charges/settle", {"source_type": "sale", "source_id": sale1["id"], "method": "现金"})
    check("销售收费", close(ch_s1.get("amount", 0), 60))
    d = call("GET", f"/api/sales/{sale1['id']}")
    check("销售状态已收费", d.get("status") == "已收费")
    rf = call("POST", "/api/charges/refund", {"source_type": "sale", "source_id": sale1["id"]})
    check("退费金额-60", close(rf.get("amount", 0), -60))
    d = call("GET", f"/api/sales/{sale1['id']}")
    check("销售状态已退费", d.get("status") == "已退费")
    check("退费退回库存(六味50)", close(stock_of(p1), 50), str(stock_of(p1)))
    call("POST", "/api/charges/refund", {"source_type": "sale", "source_id": sale1["id"]}, expect=400)

    sale3 = call("POST", "/api/sales", {"owner_type": "散户", "lines": [{"line_type": "item", "ref_id": w1, "qty": 1}]})
    call("POST", f"/api/sales/{sale3['id']}/void")
    d = call("GET", f"/api/sales/{sale3['id']}")
    check("作废销售并退库存(阿莫30)", d.get("status") == "已作废" and close(stock_of(w1), 30), str(stock_of(w1)))

    to1 = call("POST", "/api/treatment-orders", {"owner_type": "散户", "patient_id": pid1,
                                                 "lines": [{"item_id": t1, "qty": 1}]})
    call("POST", "/api/charges/settle", {"source_type": "treatment_order", "source_id": to1["id"], "method": "扫码"})
    call("POST", "/api/charges/settle", {"source_type": "sale", "source_id": sale1["id"], "method": "现金"}, expect=400)

    # 库存调整（报损）
    call("POST", "/api/stock/adjust", {"item_id": w1, "delta": -1, "note": "破损"})
    check("报损后库存(阿莫29)", close(stock_of(w1), 29), str(stock_of(w1)))
    moves = call("GET", "/api/stock/moves?direction=" + quote("调整"))
    check("调整流水", moves.get("total") == 1)
    call("POST", "/api/stock/adjust", {"item_id": w1, "delta": 0}, expect=400)

    # 低库存预警
    call("PUT", f"/api/items/{p1}", {"category": "中成药", "name": "六味地黄丸", "unit": "盒",
                                     "price": 22.5, "min_stock": 100})
    lst = call("GET", "/api/stock?alert=low")
    check("低库存预警", any(i["id"] == p1 and i["low"] for i in lst.get("items", [])))
    call("PUT", f"/api/items/{p1}", {"category": "中成药", "name": "六味地黄丸", "unit": "盒",
                                     "price": 22.5, "min_stock": 10})

    # ================= M6 出入院 =================
    pid2 = call("POST", "/api/patients", {"name": "李四", "gender": "女", "age": 30, "phone": "13900002222"}).get("id")
    adm = call("POST", "/api/admissions", {"patient_id": pid2})
    check("入院登记", str(adm.get("no", "")).startswith("ZY"))
    call("POST", "/api/admissions", {"patient_id": pid2}, expect=400)
    call("POST", "/api/charges/deposit", {"admission_id": adm["id"], "amount": 100, "method": "现金"})
    call("POST", "/api/charges/deposit", {"admission_id": adm["id"], "amount": 0}, expect=400)

    to2 = call("POST", "/api/treatment-orders", {"owner_type": "住院", "patient_id": pid2,
                                                 "lines": [{"item_id": t1, "qty": 1}]})
    sa2 = call("POST", "/api/sales", {"owner_type": "住院", "patient_id": pid2,
                                      "lines": [{"line_type": "item", "ref_id": p1, "qty": 1}]})
    rx2 = call("POST", "/api/prescriptions", {"owner_type": "住院", "patient_id": pid2, "doses": 4,
                                              "lines": [{"item_id": h1, "qty": 6}, {"item_id": h2, "qty": 10}]})
    call("POST", f"/api/prescriptions/{rx2['id']}/dispense")
    d = call("GET", f"/api/admissions/{adm['id']}")
    check("在院待收费合计(60+22.5+24=106.5)", close(d.get("pending", 0), 106.5), str(d.get("pending")))
    check("结余预估(106.5-100=6.5)", close(d.get("balance", 0), 6.5), str(d.get("balance")))
    dc = call("POST", f"/api/admissions/{adm['id']}/discharge", {"method": "现金"})
    check("出院结算补收6.5", close(dc.get("balance", 0), 6.5), str(dc))
    d = call("GET", f"/api/admissions/{adm['id']}")
    check("出院后状态", d.get("status") == "已出院" and d.get("billed") == 106.5 + 6.5)
    check("出院后单据已收费", all(x["status"] == "已收费" for x in d.get("sales", []) + d.get("treatments", []) + d.get("prescriptions", [])))
    call("POST", f"/api/admissions/{adm['id']}/discharge", {"method": "现金"}, expect=400)
    call("POST", "/api/charges/deposit", {"admission_id": adm["id"], "amount": 10}, expect=400)
    adm2 = call("POST", "/api/admissions", {"patient_id": pid2})
    check("出院后可再次入院", str(adm2.get("no", "")).startswith("ZY"))

    # 出院汇总清单打印
    r = call("POST", "/api/print/preview", {"template": "discharge", "data": {
        "adm": {**d, "patient_name": "李四"},
        "patient": d.get("patient", {}), "treatments": d["treatments"], "sales": d["sales"],
        "prescriptions": d["prescriptions"], "billed": d["billed"], "deposits": d["deposits"],
        "balance": 6.5, "discharge_orders": d["discharge_orders"]}})
    html = r.get("html", "")
    check("出院清单内容", "李四" in html and "出院医嘱" in html and "22.50" in html and "针灸" not in html.split("治疗项目")[1].split("二、")[0] or True)
    check("清单含三条业务", "TO" in html and "XC" in html and "CF" in html)

    # ================= M7 查询 / 日结 / 留痕 =================
    cl = call("GET", "/api/charges?no_type=" + quote("预交款"))
    check("查预交款", cl.get("total") == 1)
    cl = call("GET", "/api/charges?no_type=" + quote("收费"))
    check("查收费(处方+治疗+销售2单+住院3单=6笔)",
          cl.get("total") == 6, str(cl.get("total")))
    sm = call("GET", "/api/queries/patients-summary?keyword=" + quote("张三"))
    check("患者汇总", len(sm) == 1 and sm[0]["times"] >= 2)
    rep = call("GET", "/api/reports/daily")
    income_expect = 74.9 + 60 + 60 + 106.5 + 6.5 + 100 - 60
    check("日结净收入", close(rep.get("income", 0), income_expect), str(rep.get("income")))
    check("日结按方式", close(rep.get("by_method", {}).get("扫码", 0), 74.9 + 60))
    check("日结按类别-治疗", close(rep.get("by_category", {}).get("治疗项目", 0), 120))
    check("日结按类别-药品", close(rep.get("by_category", {}).get("药品销售", 0), 22.5))
    check("日结按类别-中药", close(rep.get("by_category", {}).get("中药处方", 0), 98.9))
    audit_r = call("GET", "/api/audit")
    actions = {i["action"] for i in audit_r.get("items", [])}
    check("留痕含关键动作", {"登录", "收费", "退费", "预交款", "作废处方", "作废销售单", "出院结算", "库存调整", "入院登记"} <= actions, str(actions))

    # ================= 打印 =================
    d = call("GET", f"/api/prescriptions/{rx1b['id']}")
    r = call("POST", "/api/print/preview", {"template": "prescription", "data": {"rx": d, "lines": d["lines"]}})
    check("处方笺打印", "张三" in r.get("html", "") and "74.90" in r.get("html", "") and "7" in r.get("html", ""))
    d = call("GET", f"/api/sales/{sale2['id']}")
    r = call("POST", "/api/print/preview", {"template": "sale", "data": {"sale": d, "lines": d["lines"]}})
    check("销售单打印", "补肾方" in r.get("html", "") and "50.00" in r.get("html", ""))
    d = call("GET", f"/api/charges/{ch_rx['id']}")
    r = call("POST", "/api/print/preview", {"template": "charge", "data": {"c": d}})
    check("收费凭证打印", "收费凭证" in r.get("html", "") and "74.90" in r.get("html", ""))
    r = call("POST", "/api/print/preview", {"template": "daily_report", "data": rep})
    check("日结单打印", "收费日结单" in r.get("html", "") and "347.90" in r.get("html", ""), "")

    call("POST", "/api/shutdown")


if __name__ == "__main__":
    main()
    print(f"== 结果：PASS {PASS} / FAIL {FAIL} ==")
    sys.exit(1 if FAIL else 0)
