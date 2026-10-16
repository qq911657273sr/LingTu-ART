"""Create the private environment file required by a public web deployment."""
from __future__ import annotations

import argparse
import getpass
import hashlib
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import urlsplit


def main() -> None:
    parser = argparse.ArgumentParser(description="配置灵图 ART 单管理员网页部署")
    parser.add_argument("--env-file", default="/etc/lingtu-art/lingtu.env", help="秘密环境变量文件路径")
    args = parser.parse_args()
    if os.name != "posix":
        raise SystemExit("此配置工具不支持当前操作系统")
    origin = input("网站 HTTPS 根地址（例如 https://art.example.com）: ").strip().rstrip("/")
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
        raise SystemExit("请输入 HTTPS 根地址，不要包含路径、查询参数或结尾斜杠")
    password = getpass.getpass("设置管理员密码（至少 14 位）: ")
    if len(password) < 14:
        raise SystemExit("管理员密码至少需要 14 位")
    if password != getpass.getpass("再次输入管理员密码: "):
        raise SystemExit("两次输入不一致")

    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000).hex()
    password_hash = f"pbkdf2_sha256${salt.hex()}${digest}"
    from cryptography.fernet import Fernet
    lines = [
        "ARTLIB_WEB_MODE=1",
        f"ARTLIB_PUBLIC_ORIGIN={origin}",
        f"ARTLIB_ADMIN_PASSWORD_HASH={password_hash}",
        f"ARTLIB_SESSION_SECRET={secrets.token_urlsafe(48)}",
        f"ARTLIB_ENCRYPTION_KEY={Fernet.generate_key().decode()}",
        "ARTLIB_CONFIG=/var/lib/lingtu-art/config.json",
        "ARTLIB_PORT=8765",
    ]
    target = Path(args.env_file).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise SystemExit(f"文件已存在，为避免覆盖现有密钥而停止：{target}")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if os.name == "posix":
        target.chmod(0o600)
    print(f"已写入 {target}（权限 600）。请勿公开、上传或发送此文件。")


if __name__ == "__main__":
    main()
