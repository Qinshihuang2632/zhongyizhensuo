"""A4 打印框架：Jinja2 模板 → 制式 HTML → 前端 iframe 预览 / 打印。

所有单据只按 A4 设计；模板放在 server/print_templates/，
base_a4.html 提供统一的抬头（诊所信息）与页面版式，具体单据继承它。
"""
import datetime as dt
import re

import jinja2

from . import db, paths

_NAME_RE = re.compile(r"^[\w-]+$")
_env: jinja2.Environment | None = None


def env() -> jinja2.Environment:
    global _env
    if _env is None:
        _env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(paths.print_templates_dir()),
            autoescape=True,
        )
    return _env


def templates() -> list[str]:
    return sorted(
        p.stem for p in paths.print_templates_dir().glob("*.html") if p.name != "base_a4.html"
    )


def render(template: str, data: dict | None = None) -> str:
    if not _NAME_RE.match(template):
        raise ValueError("非法模板名")
    try:
        tpl = env().get_template(template + ".html")
    except jinja2.TemplateNotFound:
        raise ValueError(f"模板不存在：{template}") from None
    ctx = {
        "clinic_name": db.get_setting("clinic_name") or "",
        "clinic_address": db.get_setting("clinic_address") or "",
        "clinic_phone": db.get_setting("clinic_phone") or "",
        "printed_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    ctx.update(data or {})
    return tpl.render(**ctx)
