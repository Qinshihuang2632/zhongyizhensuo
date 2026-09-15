"""病情标签与统计自测：python tests/conditions_test.py

覆盖：标签字典 CRUD/去重、患者病情必填校验与字典校验、入院/收费/用卡三处快照、
跨次住院归属（A 入院→用卡→改标签 B→再入院→新用卡归 B）、汇总统计
by_condition/treated_count、保健卡使用统计、权益范围配置保存。
前置：服务已启动且数据库为全新（未初始化）。
"""
import datetime as dt
import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8321"
TOKEN = ""
PASS = FAIL = 0
TODAY = dt.date.today()


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


def d(days: int) -> str:
    return (TODAY + dt.timedelta(days=days)).isoformat()


def main():
    global TOKEN
    s = call("GET", "/api/setup/status", token=False)
    if not s.get("initialized"):
        call("POST", "/api/setup/init", {"password": "123456", "clinic_name": "测试诊所A"}, token=False)
    r = call("POST", "/api/auth/login", {"username": "admin", "password": "123456"}, token=False)
    TOKEN = r.get("token", "")

    # --- 标签字典 ---
    t_a = call("POST", "/api/conditions", {"name": "颈椎病"}).get("id")
    t_b = call("POST", "/api/conditions", {"name": "腰椎间盘突出"}).get("id")
    call("POST", "/api/conditions", {"name": "颈椎病"}, expect=409)
    call("POST", "/api/conditions", {"name": ""}, expect=400)
    call("PUT", f"/api/conditions/{t_b}", {"name": "腰突症"})
    call("POST", f"/api/conditions/{t_a}/toggle")
    tags = call("GET", "/api/conditions?active=1")
    check("停用后不在active列表", all(x["id"] != t_a for x in tags))
    call("POST", f"/api/conditions/{t_a}/toggle")

    # --- 患者：标签校验（空标签向后兼容，界面强制必选；未知标签拒绝） ---
    call("POST", "/api/patients", {"name": "错标签", "gender": "男", "age": 30, "phone": "1",
                                   "condition_tags": ["不存在的病"]}, expect=400)
    pid = call("POST", "/api/patients", {"name": "甲", "gender": "男", "age": 40, "phone": "1",
                                         "condition_tags": ["颈椎病", "腰突症"]}).get("id")
    p = call("GET", f"/api/patients/{pid}")
    check("患者标签保存", p.get("condition_tags") == ["颈椎病", "腰突症"])

    # --- 患者编辑保留/更新标签 ---
    call("PUT", f"/api/patients/{pid}", {"name": "甲", "gender": "男", "age": 41, "phone": "1",
                                         "condition_tags": ["颈椎病"]})
    p = call("GET", f"/api/patients/{pid}")
    check("编辑更新标签", p.get("condition_tags") == ["颈椎病"])

    # --- 入院快照（甲：颈椎病） ---
    adm1 = call("POST", "/api/admissions", {"patient_id": pid})
    a1 = call("GET", f"/api/admissions/{adm1['id']}")
    # 详情不直接回 tags，用收费记录验证；先造住院治疗单并出院结算
    t1 = call("POST", "/api/items", {"category": "治疗项目", "name": "针灸", "unit": "次", "price": 50}).get("id")
    call("POST", "/api/treatment-orders", {"owner_type": "住院", "patient_id": pid,
                                           "lines": [{"item_id": t1, "qty": 1}]})
    call("POST", f"/api/admissions/{adm1['id']}/discharge", {"method": "现金"})
    rep = call("GET", f"/api/reports/daily?start={d(0)}&end={d(0)}")
    check("汇总含住院收费人次", rep.get("treated_count") == 1, str(rep.get("treated_count")))
    check("汇总按标签-颈椎病1", rep.get("by_condition", {}).get("颈椎病") == 1, str(rep.get("by_condition")))

    # --- 用卡归属：获卡于 70 天前（W1=[today-10, today+19]），最近一次入院=甲（颈椎病快照） ---
    call("POST", f"/api/cards/{pid}/grant", {"since": d(-70)})
    call("POST", f"/api/cards/{pid}/start", {"window_index": 1, "start_date": d(0)})
    cu = call("GET", "/api/reports/card-usage")
    check("用卡统计-总次数1", cu.get("total_usage") == 1)
    check("用卡按标签-颈椎病1", cu.get("by_condition", {}).get("颈椎病") == 1
          and cu.get("by_condition", {}).get("腰突症") is None, str(cu))

    # --- 用卡归属：甲改标签后再入院（B=腰突症快照）；W1 已用不可重复，W2 未生效 ---
    # （二次住院：改标签为腰突症 → 新入院快照 B，统计上即"又治好了一个腰突症病人"）
    call("PUT", f"/api/patients/{pid}", {"name": "甲", "gender": "男", "age": 41, "phone": "1",
                                         "condition_tags": ["腰突症"]})
    adm2 = call("POST", "/api/admissions", {"patient_id": pid})
    call("POST", "/api/treatment-orders", {"owner_type": "住院", "patient_id": pid,
                                           "lines": [{"item_id": t1, "qty": 2}]})
    call("POST", f"/api/admissions/{adm2['id']}/discharge", {"method": "现金"})
    rep = call("GET", f"/api/reports/daily?start={d(0)}&end={d(0)}")
    check("治疗人次累计2", rep.get("treated_count") == 2, str(rep.get("treated_count")))
    check("按标签-颈椎病1腰突1", rep.get("by_condition", {}).get("颈椎病") == 1
          and rep.get("by_condition", {}).get("腰突症") == 1, str(rep.get("by_condition")))
    call("POST", f"/api/cards/{pid}/start", {"window_index": 1, "start_date": d(0)}, expect=400)  # W1每轮限一次
    call("POST", f"/api/cards/{pid}/start", {"window_index": 2, "start_date": d(0)}, expect=400)  # W2未生效
    cu = call("GET", "/api/reports/card-usage")
    check("用卡总量仍1", cu.get("total_usage") == 1)

    # --- 无住院患者：归属当前标签（颈椎病） ---
    pid2 = call("POST", "/api/patients", {"name": "乙", "gender": "女", "age": 35, "phone": "2",
                                          "condition_tags": ["颈椎病"]}).get("id")
    call("POST", f"/api/cards/{pid2}/grant", {"since": d(-70)})
    call("POST", f"/api/cards/{pid2}/start", {"window_index": 1, "start_date": d(0)})
    cu = call("GET", "/api/reports/card-usage")
    check("无住院归属当前标签", cu.get("total_usage") == 2
          and cu.get("by_condition", {}).get("颈椎病") == 2
          and cu.get("by_condition", {}).get("腰突症") is None, str(cu))
    check("使用人数2", cu.get("patient_count") == 2)

    # --- 有住院患者：归属最近入院标签（腰突症） ---
    pid3 = call("POST", "/api/patients", {"name": "丙", "gender": "女", "age": 38, "phone": "3",
                                          "condition_tags": ["腰突症"]}).get("id")
    call("POST", f"/api/cards/{pid3}/grant", {"since": d(-70)})
    call("POST", "/api/admissions", {"patient_id": pid3})
    call("POST", f"/api/cards/{pid3}/start", {"window_index": 1, "start_date": d(0)})
    cu = call("GET", "/api/reports/card-usage")
    check("住院归属最近入院标签", cu.get("total_usage") == 3
          and cu.get("by_condition", {}).get("腰突症") == 1
          and cu.get("by_condition", {}).get("颈椎病") == 2, str(cu))

    # --- 散户收费也计入人次与标签 ---
    call("PUT", f"/api/patients/{pid}", {"name": "甲", "gender": "男", "age": 41, "phone": "1",
                                         "condition_tags": ["腰突症", "颈椎病"]})
    sale = call("POST", "/api/sales", {"owner_type": "散户", "patient_id": pid, "lines": []}, expect=400)
    it_c = call("POST", "/api/items", {"category": "中成药", "name": "感冒灵", "unit": "盒", "price": 12}).get("id")
    call("POST", "/api/stock/in", {"lines": [{"item_id": it_c, "qty": 10, "cost": 8}]})
    sale = call("POST", "/api/sales", {"owner_type": "散户", "patient_id": pid,
                                       "lines": [{"line_type": "item", "ref_id": it_c, "qty": 1}]})
    call("POST", "/api/charges/settle", {"source_type": "sale", "source_id": sale["id"], "method": "现金"})
    rep = call("GET", f"/api/reports/daily?start={d(0)}&end={d(0)}")
    check("散户收费计入人次3", rep.get("treated_count") == 3, str(rep.get("treated_count")))
    check("双标签各+1", rep.get("by_condition", {}).get("腰突症") == 2
          and rep.get("by_condition", {}).get("颈椎病") == 2, str(rep.get("by_condition")))

    # --- 月结/年结接口仍正常（结束周期） ---
    prev_m = (TODAY.replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")
    rep3 = call("GET", f"/api/reports/monthly?month={prev_m}")
    check("上月月结为空", rep3.get("income") == 0)

    # --- 保健卡权益配置 ---
    call("PUT", "/api/settings", {"values": {"card_benefits": json.dumps({
        "items": [{"item_id": t1, "type": "free"},
                  {"item_id": it_c, "type": "discount", "discount": 80}]}, ensure_ascii=False)}})
    cfg = call("GET", "/api/settings")
    saved = json.loads(cfg.get("card_benefits") or "{}")
    check("权益配置保存", len(saved.get("items", [])) == 2
          and saved["items"][1]["discount"] == 80, str(saved))
    call("PUT", "/api/settings", {"values": {"card_benefits": "not-json"}}, expect=400)

    # --- 病情进患者信息表打印 ---
    p = call("GET", f"/api/patients/{pid}")
    r = call("POST", "/api/print/preview", {"template": "patient_info", "data": {
        "p": {**p, "tags": "、".join(p.get("condition_tags", []))}}})
    check("信息表含病情", "腰突症" in r.get("html", ""))

    call("POST", "/api/shutdown")


if __name__ == "__main__":
    main()
    print(f"== 结果：PASS {PASS} / FAIL {FAIL} ==")
    sys.exit(1 if FAIL else 0)
