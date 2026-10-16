"""Single-admin cookie authentication for the optional Linux web deployment."""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import os
import secrets
import threading
import time
from collections import OrderedDict
from urllib.parse import urlsplit

from fastapi import APIRouter, Body, HTTPException, Request, Response

router = APIRouter(prefix="/api/auth")
ENABLED = os.environ.get("ARTLIB_WEB_MODE") == "1"
PUBLIC_ORIGIN = os.environ.get("ARTLIB_PUBLIC_ORIGIN", "").rstrip("/")
PASSWORD_HASH = os.environ.get("ARTLIB_ADMIN_PASSWORD_HASH", "")
SESSION_SECRET = os.environ.get("ARTLIB_SESSION_SECRET", "")
COOKIE_NAME = "lingtu_session"
SESSION_SECONDS = 8 * 60 * 60
_lock = threading.Lock()
_sessions: dict[str, float] = {}
_attempts: OrderedDict[str, list[float]] = OrderedDict()


def validate_config() -> None:
    if not ENABLED:
        return
    parsed = urlsplit(PUBLIC_ORIGIN)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
        raise RuntimeError("ARTLIB_PUBLIC_ORIGIN 必须是 HTTPS 根域名，例如 https://art.example.com")
    if not SESSION_SECRET or len(SESSION_SECRET) < 32:
        raise RuntimeError("ARTLIB_SESSION_SECRET 至少需要 32 个字符")
    if not PASSWORD_HASH.startswith("pbkdf2_sha256$"):
        raise RuntimeError("ARTLIB_ADMIN_PASSWORD_HASH 格式无效；请运行 python -m artlib.web_setup")
    encryption_key = os.environ.get("ARTLIB_ENCRYPTION_KEY", "")
    try:
        from cryptography.fernet import Fernet
        Fernet(encryption_key.encode())
    except (ImportError, ValueError) as exc:
        raise RuntimeError("ARTLIB_ENCRYPTION_KEY 无效；请检查私有环境变量文件") from exc


def _signature(message: str) -> str:
    return hmac.new(SESSION_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()


def _issue_cookie(sid: str, issued: int) -> str:
    message = f"{sid}.{issued}"
    return base64.urlsafe_b64encode(f"{message}.{_signature(message)}".encode()).decode().rstrip("=")


def _read_cookie(token: str) -> tuple[str, int] | None:
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode()
        sid, issued_text, signature = raw.split(".", 2)
        issued = int(issued_text)
        message = f"{sid}.{issued}"
    except (ValueError, UnicodeError):
        return None
    if not hmac.compare_digest(_signature(message), signature) or issued > time.time() + 60:
        return None
    if time.time() - issued > SESSION_SECONDS:
        return None
    return sid, issued


def authenticated(request: Request) -> bool:
    if not ENABLED:
        return True
    token = request.cookies.get(COOKIE_NAME, "")
    if not token:
        return False
    payload = _read_cookie(token)
    if not payload:
        return False
    sid, _ = payload
    now = time.time()
    with _lock:
        expiry = _sessions.get(sid, 0)
        if expiry <= now:
            _sessions.pop(sid, None)
            return False
    return True


def _client_key(request: Request) -> str:
    client = request.client.host if request.client else "unknown"
    if client in ("127.0.0.1", "::1"):
        forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        try:
            return str(ipaddress.ip_address(forwarded))
        except ValueError:
            pass
    return client[:64]


def _check_login_rate(request: Request) -> str:
    key, now = _client_key(request), time.time()
    with _lock:
        recent = [t for t in _attempts.get(key, []) if t > now - 900]
        if len(recent) >= 10:
            _attempts[key] = recent
            raise HTTPException(429, "登录尝试过多，请 15 分钟后再试", headers={"Retry-After": "900"})
        recent.append(now)
        _attempts[key] = recent
        _attempts.move_to_end(key)
        while len(_attempts) > 2000:
            _attempts.popitem(last=False)
    return key


def _verify_password(password: str) -> bool:
    try:
        _, salt, expected = PASSWORD_HASH.split("$", 2)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 310_000).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


@router.get("/status")
def status(request: Request):
    return {"required": ENABLED, "authenticated": authenticated(request)}


@router.post("/login")
def login(request: Request, response: Response, data: dict = Body(...)):
    if not ENABLED:
        return {"authenticated": True}
    _check_login_rate(request)
    password = data.get("password")
    if not isinstance(password, str) or len(password) > 1024 or not _verify_password(password):
        raise HTTPException(401, "密码不正确")
    sid = secrets.token_urlsafe(32)
    with _lock:
        _sessions[sid] = time.time() + SESSION_SECONDS
        if len(_sessions) > 10_000:
            expired = [key for key, expiry in _sessions.items() if expiry <= time.time()]
            for key in expired:
                _sessions.pop(key, None)
    response.set_cookie(COOKIE_NAME, _issue_cookie(sid, int(time.time())), max_age=SESSION_SECONDS,
                        httponly=True, secure=True, samesite="strict", path="/")
    response.headers["Cache-Control"] = "no-store"
    return {"authenticated": True}


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE_NAME, "")
    payload = _read_cookie(token)
    if payload:
        sid, _ = payload
        with _lock:
            _sessions.pop(sid, None)
    response.delete_cookie(COOKIE_NAME, httponly=True, secure=True, samesite="strict", path="/")
    response.headers["Cache-Control"] = "no-store"
    return {"authenticated": False}
