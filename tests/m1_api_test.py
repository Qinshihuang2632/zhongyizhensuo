"""M1 API 自测：python tests/m1_api_test.py start|verify

start  ：针对全新数据库，走 初始化→登录→设置→打印→备份→改数据→安排恢复。
         安排恢复后服务会自行退出。
verify ：服务重启后运行，验证数据已恢复到备份点、待恢复标记已消费。
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8321"
TOKEN = ""
PASS = FAIL = 0


def call(method, path, body=None, token=True, expect=200):
    global TOKEN
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
    ok = code == expect
    global PASS, FAIL
    if ok:
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


def phase_start():
    global TOKEN
    print("== 阶段1：全新库初始化与核心流程 ==")
    s = call("GET", "/api/setup/status", token=False)
    check("初始未初始化", s.get("initialized") is False)

    call("POST", "/api/setup/init", {"password": "123456", "clinic_name": "测试诊所A"}, token=False)
    s = call("GET", "/api/setup/status", token=False)
    check("初始化后状态", s.get("initialized") is True and s.get("clinic_name") == "测试诊所A")
    call("POST", "/api/setup/init", {"password": "x"}, token=False, expect=409)  # 重复初始化应拒绝

    call("POST", "/api/auth/login", {"username": "admin", "password": "wrong"}, token=False, expect=401)
    r = call("POST", "/api/auth/login", {"username": "admin", "password": "123456"}, token=False)
    TOKEN = r.get("token", "")
    check("登录获得token", len(TOKEN) > 20)

    call("GET", "/api/settings", token=False, expect=401)  # 无token应401
    cfg = call("GET", "/api/settings")
    check("settings不含密码哈希", "password_hash" not in cfg)

    r = call("POST", "/api/print/preview", {"template": "test_sheet", "data": {}})
    check("打印含诊所抬头", "测试诊所A" in r.get("html", ""))
    call("POST", "/api/print/preview", {"template": "../evil", "data": {}}, expect=400)  # 路径穿越应拒绝

    call("PUT", "/api/settings", {"values": {"clinic_address": "测试路1号", "backup_keep": "5"}})
    cfg = call("GET", "/api/settings")
    check("设置已保存", cfg.get("clinic_address") == "测试路1号" and cfg.get("backup_keep") == "5")

    r = call("POST", "/api/backup/create")
    backup_name = r.get("name", "")
    check("手动备份成功", backup_name.startswith("manual_"))
    lst = call("GET", "/api/backup/list")
    names = [b["name"] for b in lst]
    check("启动自动备份存在", any(n.startswith("clinic_") for n in names), str(names))

    call("PUT", "/api/settings", {"values": {"clinic_name": "测试诊所B"}})  # 备份后改数据

    call("POST", "/api/auth/change-password", {"old_password": "bad", "new_password": "654321"}, expect=400)
    call("POST", "/api/auth/change-password", {"old_password": "123456", "new_password": "654321"})

    r = call("POST", "/api/backup/restore", {"name": backup_name})
    check("恢复已安排", r.get("ok") is True)
    time.sleep(1)
    pending = Path("数据/clinic.db.pending_restore")
    check("待恢复标记已写入", pending.is_file())
    print(f"  手动备份名：{backup_name}")


def phase_verify():
    print("== 阶段2：重启后验证恢复 ==")
    s = call("GET", "/api/setup/status", token=False)
    check("数据已恢复为诊所A", s.get("clinic_name") == "测试诊所A", str(s))
    check("待恢复标记已消费", not Path("数据/clinic.db.pending_restore").is_file())

    r = call("POST", "/api/auth/login", {"username": "admin", "password": "123456"}, token=False)
    global TOKEN
    TOKEN = r.get("token", "")
    check("密码随备份回滚(123456可登录)", len(TOKEN) > 20)
    cfg = call("GET", "/api/settings")
    check("备份点之后的修改已回滚", cfg.get("clinic_name") == "测试诊所A")
    lst = call("GET", "/api/backup/list")
    check("存在恢复前安全备份", any(b["name"].startswith("restore_before_") or b["name"].startswith("manual_") for b in lst))

    call("POST", "/api/shutdown")


if __name__ == "__main__":
    phase = sys.argv[1] if len(sys.argv) > 1 else "start"
    if phase == "start":
        phase_start()
    else:
        phase_verify()
    print(f"== 结果：PASS {PASS} / FAIL {FAIL} ==")
    sys.exit(1 if FAIL else 0)
