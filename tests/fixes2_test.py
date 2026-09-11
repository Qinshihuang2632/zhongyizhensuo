"""2026-09-12 反馈修复自测：python tests/fixes2_test.py

覆盖：住院开单限在院患者（项目登记/药品销售/处方，未入院与出院后均拒绝）、
出院汇总清单以详情数据渲染（修复 'adm' is undefined）。
前置：服务已启动且数据库为全新（未初始化）。
"""
import datetime as dt
import json
import sys
import urllib.error
import urllib.request
import urllib.parse

BASE = "http://127.0.0.1:8321"
TOKEN = ""
PASS = FAIL = 0


def quote(s):
    return urllib.parse.quote(s)


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

    t1 = call("POST", "/api/items", {"category": "治疗项目", "name": "针灸", "unit": "次", "price": 30}).get("id")
    pid = call("POST", "/api/patients", {"name": "王五", "gender": "男", "age": 40, "phone": "13700000000"}).get("id")

    # 未入院：三类住院单全部拒绝
    call("POST", "/api/treatment-orders", {"owner_type": "住院", "patient_id": pid,
                                           "lines": [{"item_id": t1, "qty": 1}]}, expect=400)
    call("POST", "/api/sales", {"owner_type": "住院", "patient_id": pid, "lines": []}, expect=400)
    call("POST", "/api/prescriptions", {"owner_type": "住院", "patient_id": pid, "lines": []}, expect=400)

    # 入院后：允许
    adm = call("POST", "/api/admissions", {"patient_id": pid})
    to1 = call("POST", "/api/treatment-orders", {"owner_type": "住院", "patient_id": pid,
                                                 "lines": [{"item_id": t1, "qty": 1}]})
    check("在院可开住院单", bool(to1.get("id")))
    lst = call("GET", "/api/admissions?status=" + quote("在院"))
    check("在院名单含该患者", any(i["patient_id"] == pid for i in lst.get("items", [])))

    # 散户不能给在院患者记账；散户检索排除在院
    call("POST", "/api/treatment-orders", {"owner_type": "散户", "patient_id": pid,
                                           "lines": [{"item_id": t1, "qty": 1}]}, expect=400)
    exc = call("GET", "/api/patients?exclude_inpatient=1")
    check("散户检索排除在院", all(i["id"] != pid for i in exc.get("items", [])))
    inc = call("GET", "/api/patients")
    check("全档案仍含在院", any(i["id"] == pid for i in inc.get("items", [])))

    # 出院后：再开住院单拒绝（堵住截图里"出院后又记账"的漏洞）
    call("POST", f"/api/admissions/{adm['id']}/discharge", {"method": "现金"})
    call("POST", "/api/treatment-orders", {"owner_type": "住院", "patient_id": pid,
                                           "lines": [{"item_id": t1, "qty": 1}]}, expect=400)

    # 出院清单以详情数据渲染（'adm' is undefined 回归防护）
    d = call("GET", f"/api/admissions/{adm['id']}")
    r = call("POST", "/api/print/preview", {"template": "discharge", "data": {
        "adm": d, "patient": d.get("patient", {}), "treatments": d["treatments"],
        "sales": d["sales"], "prescriptions": d["prescriptions"], "billed": d["billed"],
        "deposits": d["deposits"], "balance": 30, "discharge_orders": d["discharge_orders"],
    }})
    html = r.get("html", "")
    check("出院清单渲染成功", "王五" in html and "出院医嘱" in html and "ZY" in html and "30.00" in html)

    call("POST", "/api/shutdown")


if __name__ == "__main__":
    main()
    print(f"== 结果：PASS {PASS} / FAIL {FAIL} ==")
    sys.exit(1 if FAIL else 0)
