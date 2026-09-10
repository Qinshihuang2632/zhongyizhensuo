"""FastAPI 应用：健康检查 + 前端静态托管 + 受控关机。"""
import json
import logging
from collections.abc import Callable

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db, paths

logger = logging.getLogger(__name__)
APP_NAME = "中医诊所管理系统"


def read_version() -> str:
    f = paths.version_file()
    if f.exists():
        try:
            return str(json.loads(f.read_text(encoding="utf-8")).get("version", "dev"))
        except Exception:
            logger.warning("版本文件解析失败：%s", f)
    return "dev"


def create_app(on_shutdown: Callable[[], None] | None = None) -> FastAPI:
    app = FastAPI(title=APP_NAME, docs_url=None, redoc_url=None, openapi_url=None)
    db.migrate()

    @app.get("/api/health")
    def health():
        return {
            "ok": True,
            "app": APP_NAME,
            "version": read_version(),
            "data_dir": str(paths.data_dir()),
        }

    @app.post("/api/shutdown")
    def shutdown():
        if on_shutdown is not None:
            on_shutdown()
        return {"ok": True}

    frontend = paths.frontend_dir()
    index_file = frontend / "index.html"

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        candidate = (frontend / full_path).resolve()
        if candidate.is_file() and str(candidate).startswith(str(frontend.resolve())):
            return FileResponse(candidate)
        return FileResponse(index_file)

    return app
