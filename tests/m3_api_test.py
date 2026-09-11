"""M3 字典与治疗登记 API 自测：python tests/m3_api_test.py

前置：服务已启动且数据库为全新（未初始化）。
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


def main():
    global TOKEN
    s = call("GET", "/api/setup/status", token=False)
    if not s.get("initialized"):
        call("POST", "/api/setup/init", {"password": "123456", "clinic_name": "测试诊所A"}, token=False)
    r = call("POST", "/api/auth/login", {"username": "admin", "password": "123456"}, token=False)
    TOKEN = r.get("token", "")
    check("登录", len(TOKEN) > 20)

    # ---- 字典条目 ----
    iid_acu = call("POST", "/api/items", {"category": "治疗项目", "name": "针灸", "unit": "次", "price": 50}).get("id")
    iid_mass = call("POST", "/api/items", {"category": "治疗项目", "name": "推拿", "unit": "次", "price": 40}).get("id")
    iid_moxa = call("POST", "/api/items", {"category": "治疗项目", "name": "艾灸", "unit": "次", "price": 30}).get("id")
    iid_herb = call("POST", "/api/items", {"category": "中药饮片", "name": "当归", "unit": "克", "price": 0.5}).get("id")
    iid_pill = call("POST", "/api/items", {"category": "中成药", "name": "六味地黄丸", "unit": "盒", "spec": "200丸", "price": 22.5}).get("id")
    check("创建条目", all([iid_acu, iid_mass, iid_moxa, iid_herb, iid_pill]))

    call("POST", "/api/items", {"category": "治疗项目", "name": ""}, expect=400)
    call("POST", "/api/items", {"category": "五官科", "name": "x"}, expect=400)
    call("POST", "/api/items", {"category": "治疗项目", "name": "x", "price": -1}, expect=400)

    lst = call("GET", "/api/items?category=" + quote("治疗项目"))
    check("按类别过滤", lst.get("total") == 3, str(lst.get("total")))
    lst = call("GET", "/api/items?keyword=" + quote("当归"))
    check("关键字搜索", any(i["id"] == iid_herb for i in lst.get("items", [])))
    call("GET", "/api/items/999999", expect=404)

    call("PUT", f"/api/items/{iid_acu}", {"category": "治疗项目", "name": "针灸", "unit": "次", "price": 60})
    p = call("GET", f"/api/items/{iid_acu}")
    check("改价生效", p.get("price") == 60)
    call("PUT", f"/api/items/{iid_acu}", {"category": "治疗项目", "name": "针灸", "unit": "次", "price": 60, "active": False})
    lst = call("GET", "/api/items?category=" + quote("治疗项目") + "&active=1")
    check("停用后 active 过滤排除", all(i["id"] != iid_acu for i in lst.get("items", [])))
    call("PUT", f"/api/items/{iid_acu}", {"category": "治疗项目", "name": "针灸", "unit": "次", "price": 60, "active": True})

    # ---- 协定处方 ----
    fid = call("POST", "/api/formulas", {
        "name": "补肾方", "price": 120, "note": "经典协定方",
        "lines": [{"item_id": iid_herb, "qty": 10}, {"item_id": iid_pill, "qty": 1}],
    }).get("id")
    check("创建协定处方", bool(fid))
    f = call("GET", f"/api/formulas/{fid}")
    check("处方组成完整", len(f.get("lines", [])) == 2 and f["lines"][0]["item_name"] == "当归")
    call("POST", "/api/formulas", {"name": ""}, expect=400)
    call("POST", "/api/formulas", {"name": "x", "lines": [{"item_id": iid_herb, "qty": 0}]}, expect=400)
    call("POST", "/api/formulas", {"name": "x", "lines": [{"item_id": 999999, "qty": 1}]}, expect=400)
    call("POST", "/api/formulas", {"name": "x", "lines": [{"item_id": iid_mass, "qty": 1}]}, expect=400)  # 治疗项目不能入药方
    call("PUT", f"/api/formulas/{fid}", {"name": "补肾方(改)", "price": 135, "lines": [{"item_id": iid_herb, "qty": 12}]})
    f = call("GET", f"/api/formulas/{fid}")
    check("处方修改生效", f.get("price") == 135 and len(f.get("lines", [])) == 1)

    # ---- 患者与治疗登记 ----
    pid = call("POST", "/api/patients", {"name": "张三", "gender": "男", "age": 46, "phone": "13800001111"}).get("id")
    check("建档", bool(pid))

    o1 = call("POST", "/api/treatment-orders", {
        "owner_type": "散户", "patient_id": pid,
        "lines": [{"item_id": iid_acu, "qty": 2}, {"item_id": iid_mass, "qty": 1}],
    })
    check("散户登记划价", o1.get("total") == 160, str(o1))  # 针灸60x2 + 推拿40

    o2 = None
    adm = call("POST", "/api/admissions", {"patient_id": pid})  # 2026-09-12 起：住院单限在院患者
    o2 = call("POST", "/api/treatment-orders", {
        "owner_type": "住院", "patient_id": pid,
        "lines": [{"item_id": iid_moxa, "qty": 3}], "note": "住院期间艾灸",
    })
    check("住院登记", bool(o2.get("id")) and o2.get("total") == 90)

    o3 = call("POST", "/api/treatment-orders", {
        "owner_type": "散户", "patient_name": "门口散户",
        "lines": [{"item_id": iid_mass, "qty": 1}],
    })
    check("无档案散户登记", bool(o3.get("id")))

    call("POST", "/api/treatment-orders", {"owner_type": "散户", "lines": []}, expect=400)
    call("POST", "/api/treatment-orders", {"owner_type": "住院", "lines": [{"item_id": iid_mass, "qty": 1}]}, expect=400)
    call("POST", "/api/treatment-orders", {"owner_type": "散户", "patient_id": 999999, "lines": [{"item_id": iid_mass, "qty": 1}]}, expect=400)
    call("POST", "/api/treatment-orders", {"owner_type": "散户", "lines": [{"item_id": 999999, "qty": 1}]}, expect=400)
    call("POST", "/api/treatment-orders", {"owner_type": "散户", "lines": [{"item_id": iid_mass, "qty": 0}]}, expect=400)

    d = call("GET", f"/api/treatment-orders/{o1['id']}")
    check("明细快照", d.get("patient_name") == "张三" and len(d.get("lines", [])) == 2
          and d["lines"][0]["item_name"] == "针灸" and d["lines"][0]["price"] == 60)

    call("PUT", f"/api/treatment-orders/{o1['id']}", {
        "owner_type": "散户", "patient_id": pid,
        "lines": [{"item_id": iid_acu, "qty": 3}],
    })
    d = call("GET", f"/api/treatment-orders/{o1['id']}")
    check("修改后重划价", d.get("total") == 180 and len(d.get("lines", [])) == 1)

    lst = call("GET", "/api/treatment-orders?owner_type=" + quote("住院"))
    check("按对象过滤", lst.get("total") == 1)
    lst = call("GET", "/api/treatment-orders?status=" + quote("待收费"))
    check("按状态过滤", lst.get("total") == 3)

    call("POST", f"/api/treatment-orders/{o3['id']}/void")
    d = call("GET", f"/api/treatment-orders/{o3['id']}")
    check("作废生效", d.get("status") == "已作废")
    call("POST", f"/api/treatment-orders/{o3['id']}/void", expect=400)
    call("PUT", f"/api/treatment-orders/{o3['id']}", {"owner_type": "散户", "lines": [{"item_id": iid_mass, "qty": 1}]}, expect=400)

    # 停用项目不能再登记
    call("PUT", f"/api/items/{iid_moxa}", {"category": "治疗项目", "name": "艾灸", "unit": "次", "price": 30, "active": False})
    call("POST", "/api/treatment-orders", {"owner_type": "散户", "lines": [{"item_id": iid_moxa, "qty": 1}]}, expect=400)
    call("PUT", f"/api/items/{iid_moxa}", {"category": "治疗项目", "name": "艾灸", "unit": "次", "price": 30, "active": True})

    # ---- 打印 ----
    d = call("GET", f"/api/treatment-orders/{o1['id']}")
    r = call("POST", "/api/print/preview", {"template": "treatment_order", "data": {"order": d, "lines": d["lines"]}})
    html = r.get("html", "")
    check("打印含抬头与患者", "测试诊所A" in html and "张三" in html)
    check("打印含项目与合计", "针灸" in html and "180.00" in html)
    call("POST", "/api/print/preview", {"template": "treatment_order", "data": {}}, expect=400)

    call("POST", "/api/shutdown")


if __name__ == "__main__":
    main()
    print(f"== 结果：PASS {PASS} / FAIL {FAIL} ==")
    sys.exit(1 if FAIL else 0)
