"""M2 患者档案 API 自测：python tests/m2_api_test.py

前置：服务已启动且数据库为全新（未初始化）。测试自行完成初始化与登录。
"""
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


Zhang = {
    "name": "张三", "gender": "男", "birth_date": "1980-05-01",
    "phone": "13800001111", "address": "测试路1号",
    "allergy_history": "青霉素过敏", "medical_history": "高血压", "note": "复诊患者",
}


def main():
    global TOKEN
    s = call("GET", "/api/setup/status", token=False)
    if not s.get("initialized"):
        call("POST", "/api/setup/init", {"password": "123456", "clinic_name": "测试诊所A"}, token=False)
    r = call("POST", "/api/auth/login", {"username": "admin", "password": "123456"}, token=False)
    TOKEN = r.get("token", "")
    check("登录", len(TOKEN) > 20)

    # --- 创建 ---
    r = call("POST", "/api/patients", Zhang)
    pid1 = r.get("id", 0)
    check("创建完整患者", pid1 > 0)
    r = call("POST", "/api/patients", {"name": "李四"})
    pid2 = r.get("id", 0)
    check("创建最小患者", pid2 > pid1)

    call("POST", "/api/patients", {"name": ""}, expect=400)
    call("POST", "/api/patients", {"name": "王五", "gender": "未知"}, expect=400)
    call("POST", "/api/patients", {"name": "王五", "birth_date": "1980-13-01"}, expect=400)
    call("POST", "/api/patients", {"name": "王五", "birth_date": "2999-01-01"}, expect=400)

    # --- 列表与搜索 ---
    lst = call("GET", "/api/patients")
    check("列表总数", lst.get("total", 0) >= 2, str(lst.get("total")))
    check("编号补零", all(len(i["no"]) == 6 for i in lst.get("items", [])))
    lst = call("GET", "/api/patients?keyword=" + quote("张三"))
    check("按姓名搜索", any(i["id"] == pid1 for i in lst.get("items", [])))
    lst = call("GET", "/api/patients?keyword=" + quote("13800001111"))
    check("按电话搜索", any(i["id"] == pid1 for i in lst.get("items", [])))
    lst = call("GET", f"/api/patients?keyword={pid2}")
    check("按编号搜索", any(i["id"] == pid2 for i in lst.get("items", [])))
    lst = call("GET", "/api/patients?keyword=" + quote("查无此人xyz"))
    check("无结果搜索", lst.get("total") == 0)

    # --- 详情与修改 ---
    p = call("GET", f"/api/patients/{pid1}")
    check("详情字段一致", p.get("name") == "张三" and p.get("allergy_history") == "青霉素过敏")
    call("GET", "/api/patients/999999", expect=404)
    call("PUT", f"/api/patients/{pid1}", {**Zhang, "phone": "13900002222", "address": "新路2号"})
    p = call("GET", f"/api/patients/{pid1}")
    check("修改已生效", p.get("phone") == "13900002222" and p.get("address") == "新路2号")
    check("updated_at刷新", p.get("updated_at") >= p.get("created_at"), str(p))
    call("PUT", "/api/patients/999999", {"name": "赵六"}, expect=404)
    call("PUT", f"/api/patients/{pid1}", {"name": ""}, expect=400)

    # --- 打印（数据由前端取好后传入打印框架） ---
    r = call("POST", "/api/print/preview", {"template": "patient_info", "data": {"p": {**Zhang, "no": f"{pid1:06d}", "age": 46, "created_at": "2026-09-10 17:00"}}})
    html = r.get("html", "")
    check("打印含诊所抬头", "测试诊所A" in html)
    check("打印含患者信息", "张三" in html and "青霉素过敏" in html and "0000" in html)
    call("POST", "/api/print/preview", {"template": "patient_info", "data": {}}, expect=400)  # 缺数据应报错而非500

    call("POST", "/api/shutdown")


if __name__ == "__main__":
    main()
    print(f"== 结果：PASS {PASS} / FAIL {FAIL} ==")
    sys.exit(1 if FAIL else 0)
