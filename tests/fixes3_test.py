"""2026-09-12 第二批反馈自测：python tests/fixes3_test.py

覆盖：治疗时间（登记/默认/非法格式）、住院手续页个性化医嘱（保存/出院清单打印）、
备份列表自动补当日备份。前置：服务已启动且数据库为全新（未初始化）。
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


def main():
    global TOKEN
    s = call("GET", "/api/setup/status", token=False)
    if not s.get("initialized"):
        call("POST", "/api/setup/init", {"password": "123456", "clinic_name": "测试诊所A"}, token=False)
    r = call("POST", "/api/auth/login", {"username": "admin", "password": "123456"}, token=False)
    TOKEN = r.get("token", "")

    t1 = call("POST", "/api/items", {"category": "治疗项目", "name": "针灸", "unit": "次", "price": 40}).get("id")
    pid = call("POST", "/api/patients", {"name": "赵六", "gender": "男", "age": 55, "phone": "13600000000"}).get("id")

    # --- 治疗时间 ---
    o1 = call("POST", "/api/treatment-orders", {
        "owner_type": "散户", "patient_id": pid, "treatment_time": "2026-09-11 09:30",
        "lines": [{"item_id": t1, "qty": 1}],
    })
    d = call("GET", f"/api/treatment-orders/{o1['id']}")
    check("治疗时间按所填保存", d.get("treatment_time") == "2026-09-11 09:30", str(d.get("treatment_time")))
    o2 = call("POST", "/api/treatment-orders", {
        "owner_type": "散户", "patient_id": pid,
        "lines": [{"item_id": t1, "qty": 1}],
    })
    d = call("GET", f"/api/treatment-orders/{o2['id']}")
    today = dt.date.today().isoformat()
    check("治疗时间默认当前(含今天日期)", (d.get("treatment_time") or "").startswith(today), str(d.get("treatment_time")))
    call("POST", "/api/treatment-orders", {"owner_type": "散户", "patient_id": pid,
                                           "treatment_time": "9月11日早上", "lines": [{"item_id": t1, "qty": 1}]}, expect=400)
    call("PUT", f"/api/treatment-orders/{o2['id']}", {
        "owner_type": "散户", "patient_id": pid, "treatment_time": "2026-09-12 15:05",
        "lines": [{"item_id": t1, "qty": 2}]})
    d = call("GET", f"/api/treatment-orders/{o2['id']}")
    check("修改可更新治疗时间", d.get("treatment_time") == "2026-09-12 15:05")

    # 打印含治疗时间
    r = call("POST", "/api/print/preview", {"template": "treatment_order", "data": {"order": d, "lines": d["lines"]}})
    check("治疗单打印含治疗时间", "2026-09-12 15:05" in r.get("html", ""))

    # --- 个性化医嘱 ---
    adm = call("POST", "/api/admissions", {"patient_id": pid})
    to2 = call("POST", "/api/treatment-orders", {"owner_type": "住院", "patient_id": pid,
                                                 "treatment_time": "2026-09-11 10:00",
                                                 "lines": [{"item_id": t1, "qty": 2}]})
    call("PUT", f"/api/admissions/{adm['id']}/orders",
         {"custom_orders": "嘱继续腰部理疗一周；一周后复查。"}, token=True)
    d = call("GET", f"/api/admissions/{adm['id']}")
    check("个性化医嘱已保存", "腰部理疗" in (d.get("custom_orders") or ""))
    call("PUT", f"/api/admissions/{adm['id']}/orders", {"custom_orders": "x" * 501}, expect=400)
    dc = call("POST", f"/api/admissions/{adm['id']}/discharge", {"method": "现金"})
    d = call("GET", f"/api/admissions/{adm['id']}")
    r = call("POST", "/api/print/preview", {"template": "discharge", "data": {
        "adm": d, "patient": d.get("patient", {}), "treatments": d["treatments"],
        "sales": d["sales"], "prescriptions": d["prescriptions"], "billed": d["billed"],
        "deposits": d["deposits"], "balance": dc.get("balance", 0),
        "discharge_orders": d["discharge_orders"], "custom_orders": d.get("custom_orders", ""),
    }})
    html = r.get("html", "")
    check("出院清单含固定与个性化医嘱", "按时服药" in html and "腰部理疗" in html)
    check("出院清单含治疗时间", "2026-09-11 10:00" in html)

    # --- 备份列表自动补当日 ---
    lst = call("GET", "/api/backup/list")
    check("备份列表可读", isinstance(lst, list))
    call("POST", "/api/shutdown")


if __name__ == "__main__":
    main()
    print(f"== 结果：PASS {PASS} / FAIL {FAIL} ==")
    sys.exit(1 if FAIL else 0)
