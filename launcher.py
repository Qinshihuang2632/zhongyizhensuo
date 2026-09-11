"""打包态入口：初始化目录与日志 → 起服务 → 等就绪 → 打开独立应用窗口 → 阻塞至退出。

界面窗口优先用 Edge/Chrome 的应用模式（无地址栏、无标签页，观感即独立桌面应用），
找不到时退回默认浏览器。设置环境变量 ZYZS_NO_UI=1 可只起服务不开窗口（自动化测试用）。
"""
import logging
import logging.handlers
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

import uvicorn

from server import paths
from server.main import create_app

logger = logging.getLogger("zyzs")

PORT_FIRST = 8321
PORT_TRIES = 20


def setup_logging() -> None:
    paths.ensure_dirs()
    handler = logging.handlers.RotatingFileHandler(
        paths.log_dir() / "app.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    handlers = [handler]
    if sys.stderr is not None:  # --windowed 打包下无控制台
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) != 0


def _health_ok(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


def find_port() -> int | None:
    """找一个空闲端口。若已有本系统实例在运行，返回该端口。"""
    for port in range(PORT_FIRST, PORT_FIRST + PORT_TRIES):
        if not _port_free(port) and _health_ok(port):
            return port  # 已有实例
        if _port_free(port):
            return port
    return None


def find_app_browser() -> str | None:
    """优先 Edge，其次 Chrome（Windows 注册表 App Paths + 常见安装路径）。"""
    candidates: list[str] = []
    try:
        import winreg

        for name in ("msedge.exe", "chrome.exe"):
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(
                        hive, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{name}"
                    ) as k:
                        value = winreg.QueryValueEx(k, "")[0]
                        if value:
                            candidates.append(value)
                except OSError:
                    continue
    except ImportError:
        pass
    candidates += [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def open_app_window(url: str) -> None:
    exe = find_app_browser()
    if exe:
        try:
            subprocess.Popen([
                exe,
                f"--app={url}",
                "--window-size=1280,860",
                "--no-first-run",
                "--no-default-browser-check",
            ])
            logger.info("已打开应用窗口：%s", exe)
            return
        except OSError as e:
            logger.warning("应用窗口启动失败（%s），回退浏览器：%s", exe, e)
    logger.info("使用默认浏览器打开")
    webbrowser.open(url)


def main() -> None:
    setup_logging()

    existing = find_port()
    if existing is not None and not _port_free(existing):
        logger.info("已有实例在端口 %s 运行，直接打开页面", existing)
        if not os.environ.get("ZYZS_NO_UI"):
            open_app_window(f"http://127.0.0.1:{existing}/")
        return

    port = find_port()
    if port is None:
        logger.error("8321~8340 端口均被占用，无法启动")
        return

    holder: dict[str, uvicorn.Server] = {}

    def request_shutdown() -> None:
        server = holder.get("server")
        if server is not None:
            server.should_exit = True

    app = create_app(on_shutdown=request_shutdown)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    holder["server"] = server
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(100):
        if _health_ok(port):
            break
        time.sleep(0.1)

    url = f"http://127.0.0.1:{port}/"
    logger.info("服务已就绪：%s", url)
    if not os.environ.get("ZYZS_NO_UI"):
        open_app_window(url)

    try:
        while thread.is_alive() and not server.should_exit:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        logger.info("已退出")


if __name__ == "__main__":
    main()
