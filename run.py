"""开发态入口：python run.py（不弹浏览器，日志走控制台）。"""
import uvicorn

from server.main import create_app

if __name__ == "__main__":
    holder: dict[str, uvicorn.Server] = {}

    def request_shutdown() -> None:
        server = holder.get("server")
        if server is not None:
            server.should_exit = True

    config = uvicorn.Config(
        create_app(on_shutdown=request_shutdown),
        host="127.0.0.1",
        port=8321,
        log_level="info",
    )
    server = uvicorn.Server(config)
    holder["server"] = server
    server.run()
