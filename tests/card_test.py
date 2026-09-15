"""保健卡 API 自测：python tests/card_test.py

覆盖：授予（默认/指定日期/重复拒绝/未来日期拒绝）、窗口计算（61-90、241-270）、
提醒（生效前7天出现、确认后消失、跨轮次）、开始使用（窗口内合法、越界拒绝、
每轮一次、使用后不再提醒）、过期窗口不提醒、患者列表 has_card。
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


def d(days: int) -> str:
    return (TODAY + dt.timedelta(days=days)).isoformat()


def main():
    global TOKEN
    s = call("GET", "/api/setup/status", token=False)
    if not s.get("initialized"):
        call("POST", "/api/setup/init", {"password": "123456", "clinic_name": "测试诊所A"}, token=False)
    r = call("POST", "/api/auth/login", {"username": "admin", "password": "123456"}, token=False)
    TOKEN = r.get("token", "")

    pid = call("POST", "/api/patients", {"name": "卡农", "gender": "女", "age": 40, "phone": "13100001111"}).get("id")
    lst = call("GET", "/api/patients")
    check("初始无卡", [i for i in lst["items"] if i["id"] == pid][0]["has_card"] is False)
    call("GET", f"/api/cards/{pid}")
    d0 = call("GET", f"/api/cards/{pid}")
    check("无卡详情", d0.get("has_card") is False)

    # --- 授予 ---
    call("POST", f"/api/cards/{pid}/grant", {"since": d(5)}, expect=400)  # 未来日期
    call("POST", f"/api/cards/{pid}/grant", {"since": d(0)})
    lst = call("GET", "/api/patients")
    check("列表显示有卡", [i for i in lst["items"] if i["id"] == pid][0]["has_card"] is True)
    call("POST", f"/api/cards/{pid}/grant", {}, expect=409)  # 重复授予

    # --- 窗口计算（默认今天获卡：第61天 = today+60） ---
    c = call("GET", f"/api/cards/{pid}")
    w = c.get("windows", [])
    check("窗口1起止(+60~+89)", w[0]["start"] == d(60) and w[0]["end"] == d(89), str(w[0]))
    check("窗口2起止(+240~+269)", w[1]["start"] == d(240) and w[1]["end"] == d(269), str(w[1]))
    check("窗口3起止(+420~+449)", w[2]["start"] == d(420) and w[2]["end"] == d(449), str(w[2]))
    check("窗口1状态未生效", w[0]["status"] == "未生效")

    # --- 调整起始日期（老患者用）：窗口全部重算，可再调回 ---
    call("POST", f"/api/cards/{pid}/since", {"since": d(5)}, expect=400)  # 未来日期
    call("POST", f"/api/cards/{pid}/since", {"since": d(-70)})
    c = call("GET", f"/api/cards/{pid}")
    check("调整后获卡日与窗口重算", c.get("since") == d(-70)
          and c["windows"][0]["start"] == d(-10) and c["windows"][0]["end"] == d(19)
          and c["windows"][0]["status"] == "可使用", str(c.get("windows", [{}])[0]))
    call("POST", f"/api/cards/{pid}/since", {"since": d(0)})
    c = call("GET", f"/api/cards/{pid}")
    check("再调回今天获卡", c.get("since") == d(0) and c["windows"][0]["start"] == d(60), str(c.get("windows", [{}])[0]))

    # --- 提醒：获卡于 53 天前 → 窗口1 还差 7 天生效 ---
    pid2 = call("POST", "/api/patients", {"name": "卡友", "gender": "男", "age": 50, "phone": "13100002222"}).get("id")
    call("POST", f"/api/cards/{pid2}/grant", {"since": d(-53)})
    rem = call("GET", "/api/cards/reminders")
    hit = [x for x in rem if x["patient_id"] == pid2]
    check("提前7天出现提醒", len(hit) == 1 and hit[0]["window_index"] == 1
          and hit[0]["days_to_start"] == 7 and hit[0]["effective"] is False, str(hit))
    call("POST", f"/api/cards/{pid2}/reminders/1/confirm")
    rem = call("GET", "/api/cards/reminders")
    check("确认后不再提醒", all(x["patient_id"] != pid2 for x in rem))

    # --- 开始使用：获卡于 70 天前 → 窗口1 = [today-10, today+19] ---
    pid3 = call("POST", "/api/patients", {"name": "卡用", "gender": "女", "age": 60, "phone": "13100003333"}).get("id")
    call("POST", f"/api/cards/{pid3}/grant", {"since": d(-70)})
    rem = call("GET", "/api/cards/reminders")
    hit = [x for x in rem if x["patient_id"] == pid3]
    check("已生效窗口提醒(effective)", len(hit) == 1 and hit[0]["effective"] is True, str(hit))
    c = call("GET", f"/api/cards/{pid3}")
    check("窗口1可使用", c["windows"][0]["status"] == "可使用")

    call("POST", f"/api/cards/{pid3}/start", {"window_index": 1, "start_date": d(-20)}, expect=400)  # 早于窗口
    call("POST", f"/api/cards/{pid3}/start", {"window_index": 1, "start_date": d(14)}, expect=400)   # 7天超出窗口
    call("POST", f"/api/cards/{pid3}/start", {"window_index": 1, "start_date": d(13)})
    c = call("GET", f"/api/cards/{pid3}")
    check("使用期已登记", c["windows"][0]["status"] == "已使用"
          and c["windows"][0]["usage_start"] == d(13) and c["windows"][0]["usage_end"] == d(19), str(c["windows"][0]))
    call("POST", f"/api/cards/{pid3}/start", {"window_index": 1, "start_date": d(0)}, expect=400)  # 每轮一次
    rem = call("GET", "/api/cards/reminders")
    check("使用后不再提醒", all(x["patient_id"] != pid3 for x in rem))
    check("窗口2仍为未生效", c["windows"][1]["status"] == "未生效")

    # --- 过期窗口：获卡于 200 天前 → 窗口1 = [today-140, today-111] 已过期，窗口2 还差40天 ---
    pid4 = call("POST", "/api/patients", {"name": "卡迟", "gender": "男", "age": 45, "phone": "13100004444"}).get("id")
    call("POST", f"/api/cards/{pid4}/grant", {"since": d(-200)})
    c = call("GET", f"/api/cards/{pid4}")
    check("窗口1已过期", c["windows"][0]["status"] == "已过期")
    rem = call("GET", "/api/cards/reminders")
    check("过期不提醒", all(x["patient_id"] != pid4 for x in rem))
    check("窗口2未生效(差40天)", c["windows"][1]["status"] == "未生效" and c["windows"][1]["days_to_start"] == 40,
          str(c["windows"][1]))

    # --- 第二轮可使用：获卡于 250 天前 → 窗口2 = [today-10, today+19] ---
    pid5 = call("POST", "/api/patients", {"name": "卡二轮", "gender": "女", "age": 38, "phone": "13100005555"}).get("id")
    call("POST", f"/api/cards/{pid5}/grant", {"since": d(-250)})
    c = call("GET", f"/api/cards/{pid5}")
    check("窗口2可使用", c["windows"][1]["status"] == "可使用", str(c["windows"][1]))
    call("POST", f"/api/cards/{pid5}/start", {"window_index": 2, "start_date": d(-3)})
    c = call("GET", f"/api/cards/{pid5}")
    check("第二轮使用登记", c["windows"][1]["status"] == "已使用"
          and c["windows"][1]["usage_start"] == d(-3) and c["windows"][1]["usage_end"] == d(3))
    call("POST", f"/api/cards/{pid5}/start", {"window_index": 1, "start_date": d(-160)}, expect=400)  # 第一轮已过期

    # --- 患者信息编辑不影响 card_since ---
    p = call("GET", f"/api/patients/{pid}")
    call("PUT", f"/api/patients/{pid}", {"name": "卡农", "gender": "女", "age": 41, "phone": "13100001111"})
    p = call("GET", f"/api/patients/{pid}")
    check("编辑后持卡信息保留", p.get("has_card") is True)

    call("POST", "/api/shutdown")


if __name__ == "__main__":
    main()
    print(f"== 结果：PASS {PASS} / FAIL {FAIL} ==")
    sys.exit(1 if FAIL else 0)
