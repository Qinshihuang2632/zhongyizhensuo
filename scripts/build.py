"""打包脚本：PyInstaller 构建，并组装发布文件夹 dist/中医诊所管理系统/。

用法：
  python scripts/build.py                # 调试版（带控制台窗口，便于排错）
  python scripts/build.py --release      # 发布版（无控制台窗口）
  python scripts/build.py --release --installer
                                         # 发布版 + 生成一键安装包 zip（dist/）
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_NAME = "中医诊所管理系统"
EXE_NAME = "zhongyizhensuo"


def build_installer(ver: str) -> Path:
    """构建「一键安装.exe」并组装安装包文件夹与 zip。返回 zip 路径。"""
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
         "--onefile", "--windowed", "--name", "一键安装",
         "--icon", str(ROOT / "assets" / "app.ico"),
         str(ROOT / "scripts" / "installer.py")],
        check=True, cwd=ROOT,
    )
    pkg_dir = ROOT / "dist" / f"{APP_NAME}-安装包-v{ver}"
    if pkg_dir.exists():
        shutil.rmtree(pkg_dir)
    content = pkg_dir / "安装内容"
    content.mkdir(parents=True)
    # 程序文件（不含「数据」）
    for item in (ROOT / "dist" / APP_NAME).iterdir():
        if item.name == "数据":
            continue
        dest = content / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)
    shutil.copy2(ROOT / "dist" / "一键安装.exe", pkg_dir / "一键安装.exe")
    zip_path = shutil.make_archive(str(pkg_dir), "zip", pkg_dir)
    return Path(zip_path)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("--release", action="store_true", help="无控制台窗口")
    parser.add_argument("--installer", action="store_true", help="同时生成一键安装包")
    args = parser.parse_args()

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--name", EXE_NAME,
        "--icon", str(ROOT / "assets" / "app.ico"),
        "--add-data", str(ROOT / "server" / "migrations") + ";server/migrations",
        "--add-data", str(ROOT / "server" / "print_templates") + ";server/print_templates",
        "--add-data", str(ROOT / "frontend" / "dist") + ";frontend/dist",
        str(ROOT / "launcher.py"),
    ]
    if args.release:
        cmd.append("--windowed")
    print(">>", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)

    # 打包前检查：系统正在运行时，数据目录会被占用，且可能把数据搬出造成混乱
    probe = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {EXE_NAME}.exe"],
        capture_output=True, text=True,
    )
    if EXE_NAME.lower() in (probe.stdout or "").lower():
        raise SystemExit(
            "检测到「中医诊所管理系统」正在运行。\n"
            "请先完全退出系统（退出后确认任务栏无该图标），再重新打包。\n"
            "（运行中打包会导致数据目录被占用，发布内容也无法与其分离）"
        )

    src = ROOT / "dist" / EXE_NAME
    out = ROOT / "dist" / APP_NAME
    # 重新打包时保留「数据」目录（里面是真实业务数据，绝不随更新丢失）
    keep = None
    if out.exists():
        data = out / "数据"
        if data.is_dir():
            keep = out.parent / f".数据保留_{int(time.time())}"
            try:
                shutil.move(str(data), str(keep))
            except PermissionError:
                raise SystemExit(
                    f"无法移动 {data}：发布目录正在被占用（系统可能正在运行，"
                    "或终端/资源管理器停留在该目录中）。\n"
                    "请先完全退出「中医诊所管理系统」并关闭占用该目录的窗口后重新打包。"
                )
        try:
            shutil.rmtree(out)
        except PermissionError:
            if keep is not None:
                shutil.move(str(keep), str(out / "数据"))
            raise SystemExit(
                f"无法删除 {out}：发布目录正在被占用（系统可能正在运行，"
                "或终端/资源管理器停留在该目录中）。\n"
                "请先完全退出「中医诊所管理系统」并关闭占用该目录的窗口后重新打包。"
            )
    shutil.copytree(src, out)
    if keep is not None:
        shutil.move(str(keep), str(out / "数据"))
    shutil.copy2(ROOT / "版本.json", out / "版本.json")
    shutil.copy2(ROOT / "使用说明.txt", out / "使用说明.txt")
    print(f"\n打包完成：{out}")
    print(f"启动程序：{out / (EXE_NAME + '.exe')}")

    if args.installer:
        ver = json.loads((ROOT / "版本.json").read_text(encoding="utf-8")).get("version", "0.0.0")
        zip_path = build_installer(ver)
        print(f"安装包已生成：{zip_path}")


if __name__ == "__main__":
    main()
