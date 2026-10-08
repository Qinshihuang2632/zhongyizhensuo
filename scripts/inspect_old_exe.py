"""静态检查两个老版系统 exe：打包方式、内部结构、可提取数据线索。只读，不运行。"""
import re
from pathlib import Path

FILES = [
    Path(r"D:\documents\we chat records\xwechat_files\wxid_hwlvdup2v00422_b4af\msg\file\2026-10\中医诊所管理系统客户端.exe"),
    Path(r"D:\documents\we chat records\xwechat_files\wxid_hwlvdup2v00422_b4af\msg\file\2026-10\中医诊所服务器-内网版.exe"),
]

SIGNATURES = {
    "PyInstaller(MEI)": b"MEI\x0c\x0b\x0a\x0b\x0e",
    "PyInstaller字样": b"PyInstaller",
    "_MEIPASS": b"_MEIPASS",
    "python3x.dll": b"python3",
    "Nuitka": b"Nuitka",
    ".NET(BSJB)": b"BSJB",
    "InnoSetup": b"Inno Setup",
    "NullsoftNSIS": b"Nullsoft",
    "InstallShield": b"InstallShield",
    "UPX": b"UPX!",
    "Enigma虚拟壳": b"Enigma",
    "Electron": b"electron",
    "asar归档": b"app.asar",
    "Go语言": b"Go build ID",
    "SQLite库文件": b"SQLite format 3",
    "Access数据库": b"Standard Jet DB",
    "MySQL引用": b"mysql",
    "SQLServer引用": b"SQL Server",
    "Delphi/BDE": b"Borland",
    "VFPODBC": b"Visual FoxPro",
    "zip片段": b"PK\x03\x04",
}

GBK_KEYWORDS = ["药品", "患者", "处方", "中医", "收费", "参合", "病历", "库存", "针灸", "推拿", "医保", " sqlite", "127.0.0.1"]
UTF16_KEYWORDS = ["药品", "患者", "处方"]


def pe_info(data: bytes) -> str:
    if data[:2] != b"MZ":
        return "非PE文件"
    try:
        pe_off = int.from_bytes(data[0x3C:0x40], "little")
        machine = int.from_bytes(data[pe_off + 4:pe_off + 6], "little")
        return {0x8664: "x64", 0x14C: "x86(32位)"}.get(machine, hex(machine))
    except Exception:
        return "PE解析失败"


def ctx(data: bytes, pos: int, back=60, fwd=140) -> str:
    seg = data[max(0, pos - back):pos + fwd]
    txt = seg.decode("gbk", "ignore")
    return re.sub(r"[^\x20-\x7e\u4e00-\u9fff，。：；（）、．]", " ", txt)


for f in FILES:
    print("=" * 30, f.name, "=" * 30)
    data = f.read_bytes()
    print(f"大小: {len(data):,} 字节 | 类型: {pe_info(data)}")
    for name, sig in SIGNATURES.items():
        positions = [m.start() for m in re.finditer(re.escape(sig), data)]
        if positions:
            print(f"[命中] {name}: {len(positions)} 处 @ {positions[:3]}")
            if name in ("SQLite库文件", "Access数据库", "PyInstaller(MEI)"):
                print("        上下文:", ctx(data, positions[0], 40, 120))

    # 中文关键词（GBK 编码扫描，商用老系统常见）
    print("-- GBK 关键词 --")
    for kw in GBK_KEYWORDS:
        b = kw.encode("gbk")
        n = data.count(b)
        if n:
            first = data.find(b)
            print(f"  {kw}: {n} 处 | 示例: {ctx(data, first, 30, 80)}")
    # UTF-16LE 关键词（.NET/Delphi 常见）
    for kw in UTF16_KEYWORDS:
        b = kw.encode("utf-16-le")
        n = data.count(b)
        if n:
            seg = data[data.find(b) - 20:data.find(b) + 80].decode("utf-16-le", "ignore")
            print(f"  [UTF16] {kw}: {n} 处 | 示例: {seg[:60]}")
    # 可读 ASCII 字符串抽样（配置线索）
    strs = re.findall(rb"[\x20-\x7e]{8,}", data)
    interesting = [s.decode() for s in strs if re.search(
        rb"(?i)(\.db|\.sqlite|\.mdb|\.mdf|\.ini|\.json|\.config|\.udl|odbc|dsn|192\.168|127\.0\.0\.1|server=|database=|provider=)", s)]
    print("-- 配置类字符串(前15) --")
    for s in interesting[:15]:
        print("  ", s[:110])
    print()
