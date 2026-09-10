"""打包态入口：初始化目录与日志 → 起服务 → 等就绪 → 打开浏览器 → 阻塞至退出。"""
import logging
import logging.handlers
import socket
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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[handler, logging.StreamHandler()],
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


def main() -> None:
    setup_logging()

    existing = find_port()
    if existing is not None and not _port_free(existing):
        logger.info("已有实例在端口 %s 运行，直接打开页面", existing)
        webbrowser.open(f"http://127.0.0.1:{existing}/")
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
    webbrowser.open(url)

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
