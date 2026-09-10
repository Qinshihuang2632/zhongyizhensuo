"""打包脚本：PyInstaller 构建，并组装发布文件夹 dist/中医诊所管理系统/。

用法：
  python scripts/build.py            # 调试版（带控制台窗口，便于排错）
  python scripts/build.py --release  # 发布版（无控制台窗口）
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_NAME = "中医诊所管理系统"
EXE_NAME = "zhongyizhensuo"


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("--release", action="store_true", help="无控制台窗口")
    args = parser.parse_args()

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--name", EXE_NAME,
        "--add-data", str(ROOT / "server" / "migrations") + ";server/migrations",
        "--add-data", str(ROOT / "frontend" / "dist") + ";frontend/dist",
        str(ROOT / "launcher.py"),
    ]
    if args.release:
        cmd.append("--windowed")
    print(">>", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)

    src = ROOT / "dist" / EXE_NAME
    out = ROOT / "dist" / APP_NAME
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(src, out)
    shutil.copy2(ROOT / "版本.json", out / "版本.json")
    shutil.copy2(ROOT / "使用说明.txt", out / "使用说明.txt")
    print(f"\n打包完成：{out}")
    print(f"启动程序：{out / (EXE_NAME + '.exe')}")


if __name__ == "__main__":
    main()
