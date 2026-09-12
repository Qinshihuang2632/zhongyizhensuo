"""M8 自测：python tests/m8_test.py

覆盖：更新包校验（非 zip/缺文件/版本不高于）、暂存与应用（含 .old 让位与数据不动）、
数据包导出/导入往返、迁移导入后的恢复流程。
前置：服务已启动且数据库为全新（未初始化）。
"""
import io
import json
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

BASE = "http://127.0.0.1:8321"
ROOT = Path(__file__).resolve().parent.parent
TOKEN = ""
PASS = FAIL = 0


def call(method, path, body=None, token=True, expect=200, raw=None):
    req = urllib.request.Request(BASE + path, method=method)
    if token and TOKEN:
        req.add_header("X-Token", TOKEN)
    data = raw
    if body is not None:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(body).encode("utf-8")
    if raw is not None:
        req.add_header("Content-Type", "application/octet-stream")
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as r:
            if path.endswith("/export"):
                return r.status, r.read()
            code, payload = r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        code = e.code
        payload = e.read()
        if path.endswith("/export"):
            return code, payload
        try:
            payload = json.loads(payload.decode("utf-8"))
        except Exception:
            payload = {"raw": payload.decode("utf-8", "replace")}
    global PASS, FAIL
    if code == expect:
        PASS += 1
        print(f"  PASS  {method} {path} -> {code}")
    else:
        FAIL += 1
        print(f"  FAIL  {method} {path} -> got {code}, want {expect}: {str(payload)[:160]}")
    return code, payload


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} {detail}")


def make_zip(path: Path, version: str, with_exe=True):
    with zipfile.ZipFile(path, "w") as z:
        if with_exe:
            z.writestr("zhongyizhensuo.exe", "NEW_EXE")
            z.writestr("_internal/new.dll", "DLL")
        z.writestr("版本.json", json.dumps({"name": "x", "version": version}, ensure_ascii=False))


def main():
    global TOKEN
    _, s = call("GET", "/api/setup/status", token=False)
    if not s.get("initialized"):
        call("POST", "/api/setup/init", {"password": "123456", "clinic_name": "测试诊所A"}, token=False)
    _, r = call("POST", "/api/auth/login", {"username": "admin", "password": "123456"}, token=False)
    TOKEN = r.get("token", "")
    check("登录", len(TOKEN) > 20)

    _, cur = call("GET", "/api/update/current")
    check("当前版本可读", bool(cur.get("version")))

    app_root = ROOT
    stage = app_root / "更新暂存"
    marker = app_root / "数据" / "update_pending.json"

    # --- 更新包校验 ---
    _, p = call("POST", "/api/update/upload", raw=b"not a zip", expect=400)
    check("非zip拒绝", "zip" in str(p) or "有效的" in str(p), str(p))
    z_low = Path("测试_低版本.zip")
    make_zip(z_low, "0.0.1")
    _, p = call("POST", "/api/update/upload", raw=z_low.read_bytes(), expect=400)
    check("低版本拒绝", "不高于" in str(p), str(p))
    z_bad = Path("测试_缺文件.zip")
    with zipfile.ZipFile(z_bad, "w") as z:
        z.writestr("版本.json", json.dumps({"version": "9.9.9"}))
    call("POST", "/api/update/upload", raw=z_bad.read_bytes(), expect=400)
    z_ok = Path("测试_更新包.zip")
    make_zip(z_ok, "9.9.9")
    _, p = call("POST", "/api/update/upload", raw=z_ok.read_bytes())
    check("高版本暂存成功", p.get("version") == "9.9.9", str(p))
    check("暂存目录生成", (stage / "zhongyizhensuo.exe").is_file())
    check("标记生成", marker.is_file())

    # --- 应用逻辑（直连函数，用临时目录模拟完整程序目录） ---
    script = r'''
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, r"{root}")
from server import updater
tmp = Path(tempfile.mkdtemp())
app = tmp / "app"; data = app / "数据"
data.mkdir(parents=True)
(app / "zhongyizhensuo.exe").write_bytes(b"OLD")
internal = app / "_internal"; internal.mkdir(); (internal / "old.dll").write_bytes(b"OLD")
(data / "clinic.db").write_bytes(b"DB")
(data / "update_pending.json").write_text(json.dumps({"version": "9.9.9"}), encoding="utf-8")
stage = app / "更新暂存"; stage.mkdir()
(stage / "zhongyizhensuo.exe").write_bytes(b"NEW")
si = stage / "_internal"; si.mkdir(); (si / "new.dll").write_bytes(b"NEW")
(stage / "使用说明.txt").write_text("NEW", encoding="utf-8")
junk = app / "_internal.old"; junk.mkdir(); (junk / "junk").write_bytes(b"J")
v = updater.apply_pending_update(app_root=app)
result = {
    "version": v,
    "exe": (app / "zhongyizhensuo.exe").read_bytes().decode(),
    "dll": (app / "_internal" / "new.dll").read_bytes().decode(),
    "note": (app / "使用说明.txt").read_text(encoding="utf-8"),
    "db": (data / "clinic.db").read_bytes().decode(),
    "marker_gone": not (data / "update_pending.json").exists(),
    "stage_gone": not stage.exists(),
    "junk_cleaned": not junk.exists(),
}
print(json.dumps(result))
'''.replace("{root}", str(ROOT))
    out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                         cwd=ROOT, timeout=60)
    try:
        res = json.loads(out.stdout.strip().splitlines()[-1])
    except Exception:
        res = {}
        check("应用更新脚本执行", False, out.stdout[-300:] + out.stderr[-300:])
    if res:
        check("应用返回新版本", res.get("version") == "9.9.9", str(res))
        check("exe已替换", res.get("exe") == "NEW")
        check("_internal已替换", res.get("dll") == "NEW")
        check("新文件落位", res.get("note") == "NEW")
        check("数据未被触碰", res.get("db") == "DB")
        check("标记已消费", res.get("marker_gone"))
        check("暂存已清理", res.get("stage_gone"))
        check("旧.junk已清理", res.get("junk_cleaned"))

    # 清理真实暂存（不应用，避免污染项目根目录）
    import shutil as _sh
    if stage.exists():
        _sh.rmtree(stage, ignore_errors=True)
    marker.unlink(missing_ok=True)
    z_low.unlink(missing_ok=True)
    z_bad.unlink(missing_ok=True)
    z_ok.unlink(missing_ok=True)

    # --- 数据迁移：导出/导入往返 ---
    _, blob = call("GET", "/api/migration/export")
    check("数据包zip头", blob[:2] == b"PK")
    zf = zipfile.ZipFile(io.BytesIO(blob))
    check("数据包含clinic.db", "clinic.db" in zf.namelist())
    db_bytes = zf.read("clinic.db")
    tmp_db = Path("测试_导入校验.db")
    tmp_db.write_bytes(db_bytes)
    conn = sqlite3.connect(str(tmp_db))
    ok = conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    conn.close()
    tmp_db.unlink(missing_ok=True)
    check("clinic.db可打开", ok)

    _, p = call("POST", "/api/migration/import", raw=b"junk", expect=400)
    bad = Path("测试_坏数据包.zip")
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("meta.txt", "x")
    call("POST", "/api/migration/import", raw=bad.read_bytes(), expect=400)
    bad.unlink(missing_ok=True)
    good = Path("测试_数据包.zip")
    with zipfile.ZipFile(good, "w") as z:
        z.writestr("clinic.db", db_bytes)
    _, p = call("POST", "/api/migration/import", raw=good.read_bytes())
    check("导入已安排", p.get("ok") is True and "退出" in p.get("message", ""), str(p))
    pending = ROOT / "数据" / "clinic.db.pending_restore"
    check("恢复标记已写入", pending.is_file())
    good.unlink(missing_ok=True)

    call("POST", "/api/shutdown")


if __name__ == "__main__":
    main()
    print(f"== 结果：PASS {PASS} / FAIL {FAIL} ==")
    sys.exit(1 if FAIL else 0)
