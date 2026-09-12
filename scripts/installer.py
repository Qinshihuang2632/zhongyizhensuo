"""一键安装向导：把「安装内容」复制到目标目录，创建桌面快捷方式，可立即启动。

静默模式（自动化测试）：一键安装.exe --dir 目标目录 --silent
"""
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

APP = "中医诊所管理系统"
EXE = "zhongyizhensuo.exe"
DETACHED = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def src_dir() -> Path:
    return base_dir() / "安装内容"


def make_shortcut(target: Path) -> None:
    desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
    ps = (
        "$s=(New-Object -COM WScript.Shell).CreateShortcut("
        f"[Environment]::GetFolderPath('Desktop')+'\\{APP}.lnk');"
        f"$s.TargetPath='{target / EXE}';"
        f"$s.WorkingDirectory='{target}';"
        "$s.Save()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                   check=False, creationflags=DETACHED)


def install(target: Path, with_shortcut: bool = True) -> None:
    src = src_dir()
    if not (src / EXE).exists():
        raise FileNotFoundError(f"安装内容缺失（{EXE}），安装包不完整")
    target.mkdir(parents=True, exist_ok=True)
    # 已有安装：只覆盖程序文件，绝不动「数据」目录（安装内容里本就不含数据）
    for item in src.iterdir():
        dest = target / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)
    if with_shortcut:
        make_shortcut(target)


def gui() -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox

    root = tk.Tk()
    root.title(f"{APP} 安装向导")
    root.geometry("560x260")
    root.resizable(False, False)

    default_target = (Path("D:/") if os.path.exists("D:/") else Path.home()) / APP

    tk.Label(root, text=f"欢迎使用{APP}", font=("Microsoft YaHei", 14, "bold")).pack(pady=(18, 4))
    tk.Label(root, text="选择安装位置后点击「开始安装」，桌面将创建启动快捷方式。\n"
                        "重新安装或升级不会影响已有的「数据」文件夹。").pack(pady=4)

    row = tk.Frame(root)
    row.pack(pady=8, padx=24, fill="x")
    tk.Label(row, text="安装位置：").pack(side="left")
    var = tk.StringVar(value=str(default_target))
    entry = tk.Entry(row, textvariable=var)
    entry.pack(side="left", fill="x", expand=True, padx=6)

    def browse():
        d = filedialog.askdirectory(initialdir=var.get() or "D:/")
        if d:
            var.set(os.path.join(d, APP))

    tk.Button(row, text="浏览…", command=browse).pack(side="left")

    status = tk.Label(root, text="", fg="#0a7d43")
    status.pack(pady=4)

    def do_install():
        target = Path(var.get().strip())
        try:
            status.config(text="正在安装…", fg="#555")
            root.update()
            install(target)
            status.config(text=f"安装完成：{target}", fg="#0a7d43")
            btn_launch.config(state="normal")
        except Exception as e:
            messagebox.showerror("安装失败", str(e))
            status.config(text="安装失败", fg="#c0392b")

    def do_launch():
        target = Path(var.get().strip())
        subprocess.Popen([str(target / EXE)], cwd=str(target))

    btn_install = tk.Button(root, text="开始安装", width=14, command=do_install)
    btn_install.pack(pady=8)
    btn_launch = tk.Button(root, text="立即启动系统", width=14, state="disabled", command=do_launch)
    btn_launch.pack()

    root.mainloop()


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--dir" in args:
        i = args.index("--dir")
        target = Path(args[i + 1])
        silent = "--silent" in args
        install(target, with_shortcut=not silent)
        print("INSTALL_OK:", target)
    else:
        gui()
