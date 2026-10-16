"""HTTP-level acceptance for the optional authenticated web deployment."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parent.parent
ORIGIN = "https://art.example.test"
PASSWORD = "local-test-password-only"


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def http(port, method, path, *, data=None, cookie=None, origin=ORIGIN):
    headers = {"Host": "art.example.test"}
    if origin:
        headers["Origin"] = origin
    if data is not None:
        headers["Content-Type"] = "application/json"
    if cookie:
        headers["Cookie"] = cookie
    body = json.dumps(data).encode() if data is not None else None
    request = Request(f"http://127.0.0.1:{port}{path}", data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=4) as response:
            raw = response.read()
            value = json.loads(raw) if raw and "json" in response.headers.get("Content-Type", "") else raw.decode("utf-8") if raw else None
            return response.status, response.headers, value
    except HTTPError as error:
        raw = error.read()
        value = json.loads(raw) if raw and "json" in error.headers.get("Content-Type", "") else raw.decode("utf-8") if raw else None
        return error.code, error.headers, value


def main():
    with tempfile.TemporaryDirectory(prefix="lingtu-web-auth-") as temp:
        work = Path(temp)
        salt = secrets.token_bytes(16)
        password_hash = hashlib.pbkdf2_hmac("sha256", PASSWORD.encode(), salt, 310_000).hex()
        config = work / "config.json"
        config.write_text(json.dumps({"data_dir": str(work / "data"), "backup_dir": str(work / "backups"),
                                      "export_dir": str(work / "exports"), "open_browser": False}), "utf-8")
        port = free_port()
        env = {**os.environ, "ARTLIB_CONFIG": str(config), "ARTLIB_PORT": str(port), "ARTLIB_WEB_MODE": "1",
               "ARTLIB_PUBLIC_ORIGIN": ORIGIN,
               "ARTLIB_ADMIN_PASSWORD_HASH": f"pbkdf2_sha256${salt.hex()}${password_hash}",
               "ARTLIB_SESSION_SECRET": secrets.token_urlsafe(48),
               "ARTLIB_ENCRYPTION_KEY": Fernet.generate_key().decode()}
        proc = subprocess.Popen([sys.executable, "-m", "artlib", "--no-browser"], cwd=ROOT, env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                if proc.poll() is not None:
                    raise AssertionError("web server exited during startup")
                try:
                    if http(port, "GET", "/api/auth/status")[0] == 200:
                        break
                except OSError:
                    pass
                time.sleep(.1)
            else:
                raise AssertionError("web server did not start")

            assert http(port, "GET", "/")[0] == 200
            assert http(port, "GET", "/api/sidebar")[0] == 401
            assert http(port, "GET", "/api/auth/status")[2] == {"required": True, "authenticated": False}
            assert http(port, "POST", "/api/auth/login", data={"password": "wrong"})[0] == 401
            status, headers, body = http(port, "POST", "/api/auth/login", data={"password": PASSWORD})
            assert status == 200 and body["authenticated"]
            set_cookie = headers.get("Set-Cookie", "")
            assert "Secure" in set_cookie and "HttpOnly" in set_cookie and "SameSite=strict" in set_cookie
            cookie = set_cookie.split(";", 1)[0]
            assert http(port, "GET", "/api/sidebar", cookie=cookie)[0] == 200
            secret = "fake-linux-test-key-never-live"
            status, _, saved = http(port, "POST", "/api/ai/profiles", cookie=cookie,
                                   data={"kind": "openai", "name": "local test", "base_url": "https://api.example.test/v1",
                                         "model": "image-test", "api_key": secret})
            assert status == 200 and saved["profiles"][0]["has_key"] and "secret" not in saved["profiles"][0]
            disk_settings = work / "data" / "ai-edit" / "settings.json"
            assert secret not in disk_settings.read_text("utf-8")
            assert http(port, "POST", "/api/folders", data={"name": "x"}, cookie=cookie,
                        origin="https://attacker.example")[0] == 403
            assert http(port, "POST", "/api/auth/logout", data={}, cookie=cookie)[0] == 200
            assert http(port, "GET", "/api/sidebar", cookie=cookie)[0] == 401
            print("PASS public web auth, secure cookie, protected API, CSRF origin check, logout")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait()


if __name__ == "__main__":
    main()
