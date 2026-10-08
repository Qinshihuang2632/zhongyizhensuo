"""从老版客户端 exe 提取 UTF-16 SQL 语句与表/字段名，重建老系统数据结构线索。"""
import re
from pathlib import Path

f = Path(r"D:\documents\we chat records\xwechat_files\wxid_hwlvdup2v00422_b4af\msg\file\2026-10\中医诊所管理系统客户端.exe")
data = f.read_bytes()

# UTF-16LE 连续可读段（含中文与常见ASCII）
u16 = re.findall(rb"(?:[\x20-\x7e][\x00]|[\x4e-\x9f][\x00]|[\x30-\x4d][\x00]){6,}", data)
sqls, others = [], []
for seg in u16:
    s = seg.decode("utf-16-le", "ignore").strip()
    if len(s) < 6:
        continue
    low = s.lower()
    if any(k in low for k in ("select", "insert", "update ", "delete ", "from ", "where", "order by")):
        sqls.append(s)
    elif re.search(r"[\u4e00-\u9fff]", s) and len(s) >= 4:
        others.append(s)

seen = set()
print(f"== SQL 片段（{len(sqls)} 条，去重展示前 40）==")
for s in sqls:
    key = s[:60]
    if key in seen:
        continue
    seen.add(key)
    print("  ", s[:160].replace("\n", " "))
    if len(seen) >= 40:
        break

print("\n== 疑似表名 ==")
tables = set()
for s in sqls:
    for m in re.finditer(r"(?:from|into|update)\s+([A-Za-z_][A-Za-z0-9_]*)", s, re.I):
        tables.add(m.group(1))
print(sorted(tables))

print("\n== 界面/业务中文串（去重前 50）==")
seen2 = set()
n = 0
for s in others:
    if s in seen2:
        continue
    seen2.add(s)
    print("  ", s[:80])
    n += 1
    if n >= 50:
        break
