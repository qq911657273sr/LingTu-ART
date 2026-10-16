# Ubuntu 私有网页部署（Tailscale）

本指南把灵图 ART 部署为仅你自己的 Tailscale 网络可访问的网页应用。无需购买域名或办理 ICP 备案。Tailscale Serve 在 tailnet 内提供 HTTPS，应用本身只监听 `127.0.0.1:8765`；不要开启 Funnel，也不要在华为云安全组放通网站端口。

应用采用单管理员密码登录，登录 cookie 使用 `Secure`、`HttpOnly`、`SameSite=Strict`，会话 8 小时过期，写入请求校验来源域名。Linux 上的 AI 服务密钥使用独立 Fernet 密钥加密保存。

## 1. 将电脑和服务器加入同一个 Tailscale 网络

在 Windows 电脑上打开 Tailscale 并登录你的账号（当前已安装但尚未登录）。建议在 Tailscale 管理后台开启 MagicDNS 和 HTTPS 证书。

服务器是 Ubuntu 24.04。先在华为云 VNC 黑色终端中输入 root 密码登录，不要把密码发到聊天中。随后安装并登录 Tailscale：

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

`tailscale up` 会显示一个登录链接。在自己浏览器打开并将服务器加入与 Windows 电脑相同的 tailnet。完成后运行：

```bash
tailscale status
```

记下服务器的 MagicDNS 全名，例如 `hcss-ecs-6f53.example-tailnet.ts.net`。这个地址只在你的 tailnet 内可访问。Tailscale 官方安装说明和 Serve 说明见[Linux 安装指南](https://tailscale.com/docs/install/linux)、[Serve CLI](https://tailscale.com/docs/reference/tailscale-cli/serve)。

## 2. 安装灵图 ART

以下命令在服务器终端执行：

```bash
sudo apt update
sudo apt install -y git python3.12-venv ffmpeg
sudo useradd --system --home /var/lib/lingtu-art --create-home --shell /usr/sbin/nologin lingtu-art
sudo install -d -o root -g root -m 755 /opt/lingtu-art
sudo git clone --depth 1 https://github.com/qq911657273sr/LingTu-ART.git /opt/lingtu-art
sudo python3.12 -m venv /opt/lingtu-art/.venv
sudo /opt/lingtu-art/.venv/bin/pip install --upgrade pip
sudo /opt/lingtu-art/.venv/bin/pip install -r /opt/lingtu-art/requirements.txt
sudo install -d -o lingtu-art -g lingtu-art -m 700 /var/lib/lingtu-art
sudo -u lingtu-art tee /var/lib/lingtu-art/config.json >/dev/null <<'JSON'
{
  "host": "127.0.0.1",
  "port": 8765,
  "data_dir": "/var/lib/lingtu-art/data",
  "backup_dir": "/var/lib/lingtu-art/backups",
  "export_dir": "/var/lib/lingtu-art/exports",
  "open_browser": false
}
JSON
sudo /opt/lingtu-art/.venv/bin/python -m artlib.web_setup --env-file /etc/lingtu-art/lingtu.env
```

配置工具会询问 HTTPS 根地址和管理员密码。根地址填写：

```text
https://服务器的MagicDNS全名
```

例如 `https://hcss-ecs-6f53.example-tailnet.ts.net`。管理员密码至少 14 位。配置工具会生成会话和加密密钥，并以权限 `600` 保存到 `/etc/lingtu-art/lingtu.env`。不要公开、上传或发送此文件；不要把密钥直接放进命令行。

## 3. 启动应用并启用私有 HTTPS

```bash
sudo install -m 644 /opt/lingtu-art/deployment/ubuntu/lingtu-art.service /etc/systemd/system/lingtu-art.service
sudo systemctl daemon-reload
sudo systemctl enable --now lingtu-art
sudo systemctl status lingtu-art --no-pager
sudo tailscale serve --bg http://127.0.0.1:8765
sudo tailscale serve status
```

Serve 状态应显示 `https://服务器的MagicDNS全名` 转发到本机 `127.0.0.1:8765`。随后在已登录同一 Tailscale 网络的 Windows 电脑浏览器访问该 HTTPS 地址并输入管理员密码。没有加入你 tailnet 的设备无法访问。

华为云安全组无需为 ART 新开 80、443 或 8765 入站端口。保持 SSH 22 关闭；应用继续只监听回环地址。若以后想公开分享，请先重新评估账号隔离、备案和公网防护。

## 数据与更新

素材、数据库和备份位于 `/var/lib/lingtu-art`。空间会使用服务器磁盘；当前系统盘为 40 GiB，素材较多时需要扩容或挂载数据盘。更新前先备份 `/var/lib/lingtu-art` 和 `/etc/lingtu-art/lingtu.env`。更新时必须保留 `ARTLIB_ENCRYPTION_KEY`，否则现存 AI API 密钥无法解密。

该模式是单管理员应用，不含用户注册、多用户隔离、密码找回或双因素认证。使用强且唯一的管理员密码，并定期备份素材库。
