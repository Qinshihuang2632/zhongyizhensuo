"""FastAPI 应用：鉴权中间件 + 业务 API + 前端静态托管 + 受控关机。

开放接口（无需登录）：/api/health、/api/setup/status、/api/auth/login；
其余 /api/* 均要求 X-Token 请求头（登录后下发）。
"""
import json
import logging
from collections.abc import Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth, backup, db, paths, patients, printing

logger = logging.getLogger(__name__)
APP_NAME = "中医诊所管理系统"

_OPEN_PATHS = {"/api/health", "/api/setup/status", "/api/setup/init", "/api/auth/login"}
_EDITABLE_SETTINGS = {"clinic_name", "clinic_address", "clinic_phone", "backup_keep"}


class InitBody(BaseModel):
    password: str
    clinic_name: str = ""


class LoginBody(BaseModel):
    username: str = "admin"
    password: str


class ChangePasswordBody(BaseModel):
    old_password: str
    new_password: str


class SettingsBody(BaseModel):
    values: dict[str, str]


class RestoreBody(BaseModel):
    name: str


class PrintBody(BaseModel):
    template: str
    data: dict = {}


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
    backup.auto_backup_if_needed()  # 每日首次启动自动备份（幂等）

    app.include_router(patients.router)

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/") and path not in _OPEN_PATHS:
            if not auth.verify_token(request.headers.get("x-token", "")):
                return JSONResponse({"detail": "未登录或登录已过期"}, status_code=401)
        return await call_next(request)

    @app.get("/api/health")
    def health():
        return {
            "ok": True,
            "app": APP_NAME,
            "version": read_version(),
            "data_dir": str(paths.data_dir()),
        }

    # ---- 初始化与认证 ----

    @app.get("/api/setup/status")
    def setup_status():
        return {
            "initialized": auth.is_initialized(),
            "clinic_name": db.get_setting("clinic_name") or "",
        }

    @app.post("/api/setup/init")
    def setup_init(body: InitBody):
        if auth.is_initialized():
            raise HTTPException(409, "系统已初始化，请直接登录")
        if len(body.password) < 6:
            raise HTTPException(400, "密码至少 6 位")
        auth.set_password(body.password)
        if body.clinic_name.strip():
            db.set_setting("clinic_name", body.clinic_name.strip())
        return {"ok": True}

    @app.post("/api/auth/login")
    def login(body: LoginBody):
        token = auth.login(body.username, body.password)
        if token is None:
            raise HTTPException(401, "密码错误")
        return {"token": token}

    @app.post("/api/auth/change-password")
    def change_password(body: ChangePasswordBody):
        if len(body.new_password) < 6:
            raise HTTPException(400, "新密码至少 6 位")
        try:
            auth.change_password(body.old_password, body.new_password)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        return {"ok": True}

    # ---- 系统设置 ----

    @app.get("/api/settings")
    def get_settings():
        rows = db.query("SELECT key, value FROM settings")
        return {r["key"]: r["value"] for r in rows if r["key"] != "password_hash"}

    @app.put("/api/settings")
    def put_settings(body: SettingsBody):
        for key, value in body.values.items():
            if key == "backup_keep":
                try:
                    if int(value) < 1:
                        raise ValueError
                except ValueError:
                    raise HTTPException(400, "备份保留份数必须是不小于 1 的整数") from None
            if key in _EDITABLE_SETTINGS:
                db.set_setting(key, value)
        return {"ok": True}

    # ---- 备份与恢复 ----

    @app.get("/api/backup/list")
    def backup_list():
        return backup.list_backups()

    @app.post("/api/backup/create")
    def backup_create():
        return {"name": backup.create("manual")}

    @app.post("/api/backup/restore")
    def backup_restore(body: RestoreBody):
        try:
            backup.schedule_restore(body.name)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        if on_shutdown is not None:
            on_shutdown()  # 当前响应返回后服务退出；下次启动自动完成替换
        return {"ok": True, "message": "恢复已安排，程序即将退出；请重新启动程序完成恢复"}

    # ---- 打印 ----

    @app.get("/api/print/templates")
    def print_templates():
        return printing.templates()

    @app.post("/api/print/preview")
    def print_preview(body: PrintBody):
        try:
            html = printing.render(body.template, body.data)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        return {"html": html}

    # ---- 受控关机 ----

    @app.post("/api/shutdown")
    def shutdown():
        if on_shutdown is not None:
            on_shutdown()
        return {"ok": True}

    # ---- 前端静态托管 ----

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
