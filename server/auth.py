"""认证：单管理员（admin）+ PBKDF2 密码哈希 + 内存 token 会话。

- 密码只存哈希（PBKDF2-SHA256，12 万次迭代 + 随机盐），不存明文。
- token 保存在内存中：程序重启后需重新登录，单机场景可接受。
"""
import hashlib
import hmac
import secrets
import time

from . import db

ADMIN_USER = "admin"
_ITERATIONS = 120_000
_TOKEN_TTL = 12 * 3600  # 12 小时，滑动续期

_tokens: dict[str, float] = {}


def _hash(password: str, salt_hex: str | None = None, iterations: int = _ITERATIONS) -> str:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2${iterations}${salt.hex()}${dk.hex()}"


def _verify(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2":
            return False
        calc = _hash(password, salt_hex, int(iters))
        return hmac.compare_digest(calc.split("$")[3], hash_hex)
    except Exception:
        return False


def is_initialized() -> bool:
    return db.get_setting("password_hash") is not None


def set_password(password: str) -> None:
    db.set_setting("password_hash", _hash(password))


def change_password(old: str, new: str) -> None:
    stored = db.get_setting("password_hash") or ""
    if not _verify(old, stored):
        raise ValueError("原密码不正确")
    set_password(new)


def login(username: str, password: str) -> str | None:
    stored = db.get_setting("password_hash") or ""
    if username != ADMIN_USER or not _verify(password, stored):
        return None
    token = secrets.token_hex(32)
    _tokens[token] = time.time() + _TOKEN_TTL
    return token


def verify_token(token: str) -> bool:
    exp = _tokens.get(token)
    if exp is None:
        return False
    if time.time() > exp:
        _tokens.pop(token, None)
        return False
    _tokens[token] = time.time() + _TOKEN_TTL
    return True
