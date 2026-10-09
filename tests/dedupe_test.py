"""条目查重功能自测：python tests/dedupe_test.py

覆盖：同名拦截（含空白/分隔符变体）、同名不同价拦截、相近名称近价拦截、
价格差距大放行、编辑自身放行、预检接口。前置：服务已启动且数据库为全新。
"""
import json
import sys
import urllib.error
import urllib.request

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
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
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

    # 基准条目
    iid = call("POST", "/api/items", {"category": "治疗项目", "name": "火罐", "unit": "次", "price": 10}).get("id")
    check("基准条目创建", bool(iid))

    # 同名拦截（完全相同）
    call("POST", "/api/items", {"category": "治疗项目", "name": "火罐", "unit": "次", "price": 10}, expect=409)
    # 同名拦截（空白变体归一）
    call("POST", "/api/items", {"category": "治疗项目", "name": "火　罐", "unit": "次", "price": 10}, expect=409)
    # 同名不同价也拦截（提示改用修改）
    r = call("POST", "/api/items", {"category": "治疗项目", "name": "火罐", "unit": "次", "price": 500}, expect=409)
    check("同名不同价提示修改", "修改" in r.get("detail", ""))
    # 相近名称 + 价格相近拦截（包含关系）
    r = call("POST", "/api/items", {"category": "治疗项目", "name": "拔火罐", "unit": "次", "price": 10}, expect=409)
    check("相似近价拦截", "相近" in r.get("detail", ""))
    # 相近名称但价格差距大 → 放行
    ok = call("POST", "/api/items", {"category": "治疗项目", "name": "拔火罐", "unit": "次", "price": 300}).get("id")
    check("价格差距大放行", bool(ok))

    # 预检接口
    c = call("GET", "/api/items/duplicate-check?name=" + urllib.parse.quote("火罐") + "&price=10")
    check("预检命中", c.get("duplicate") is True and c["item"]["id"] == iid)
    c = call("GET", "/api/items/duplicate-check?name=" + urllib.parse.quote("不存在项目") + "&price=99")
    check("预检未命中", c.get("duplicate") is False)

    # 编辑自身（名称价格不变）放行；编辑冲突他人名称拦截
    call("PUT", f"/api/items/{iid}", {"category": "治疗项目", "name": "火罐", "unit": "次", "price": 12})
    p = call("GET", f"/api/items/{iid}")
    check("编辑自身放行", p.get("price") == 12)
    other = call("POST", "/api/items", {"category": "西药", "name": "阿莫西林", "unit": "盒", "price": 15}).get("id")
    call("PUT", f"/api/items/{other}", {"category": "西药", "name": "火罐", "unit": "盒", "price": 12}, expect=409)

    call("POST", "/api/shutdown")


if __name__ == "__main__":
    import urllib.parse
    main()
    print(f"== 结果：PASS {PASS} / FAIL {FAIL} ==")
    sys.exit(1 if FAIL else 0)
