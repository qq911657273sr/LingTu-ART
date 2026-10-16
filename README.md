<div align="center">

<img src="web/public/lingtu-art.png" alt="灵图 ART 图标" width="96">

# 灵图 ART

### 为 AI 创作者打造的本地美术素材库与图像编辑工作台

整理、检索、预览和复用你的图片与视频，也可以从素材库直接发起 AI 图像编辑。

[![Latest release](https://img.shields.io/github/v/release/qq911657273sr/LingTu-ART?label=%E6%9C%80%E6%96%B0%E7%89%88%E6%9C%AC)](https://github.com/qq911657273sr/LingTu-ART/releases/latest)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-4c8bf5)](https://github.com/qq911657273sr/LingTu-ART/releases/latest)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/github/license/qq911657273sr/LingTu-ART)](LICENSE)

[下载 Windows 版](https://github.com/qq911657273sr/LingTu-ART/releases/latest) · [功能与隐私](#ai-图像编辑与隐私) · [从源码运行](#从源码运行)

</div>

---

## 项目简介

灵图 ART 是一款以本地素材管理为核心的美术素材工具。它把素材整理、生成信息查看和 AI 图像编辑放在同一个工作台里，适合插画、游戏美术、概念设计和其他 AI 创作流程。提供 Windows 桌面版，也可按说明部署为带单管理员登录的 Ubuntu 网页版。

素材库支持管理图片与视频、分类文件夹、标签、收藏、备注和组合搜索；查看图片时可以放大、适应窗口并浏览完整画面。需要修改素材时，可以从库中选择一张或多张参考图，描述想要的改动，再把结果与原图对照、继续编辑，或保存为新的素材。

应用默认在本机运行，素材和数据库保存在你选择的本地目录。AI 编辑和提示词助手均为可选功能，需要时再配置自己的服务。

## 界面预览

### AI 图像编辑

<p align="center"><img src="docs/screenshots/ai-image-editing.png" alt="灵图 ART AI 图像编辑界面，展示参考图、编辑结果和生成记录" width="100%"></p>

### 本地素材库

<p align="center"><img src="docs/screenshots/asset-library.png" alt="灵图 ART 素材库界面，展示素材网格、分类和详情面板" width="100%"></p>

## 功能特点

- **本地素材管理**：导入图片和视频，使用分类、子文件夹、标签、收藏与备注整理素材。
- **快速查找与预览**：组合搜索素材名称、标签和生成信息；支持网格浏览、全图预览、缩放和前后切换。
- **生成信息识别**：读取常见 ComfyUI、A1111/Forge、XMP 和视频工作流元数据。
- **AI 图像编辑**：从素材库或本地添加参考图，按顺序组织多张参考图，描述局部修改、换背景、调整风格或姿势等需求。
- **提示词助手与预设**：可选接入 LLM，把自然语言修改需求整理成适合所选生图服务的提示词；支持导入和管理自定义提示词预设。
- **生成记录与对照**：查看任务记录、对比原图和结果、继续编辑；按需下载结果或另存到素材库，源素材不会被覆盖。
- **备份与恢复**：将素材和库数据备份到独立目录，并在需要时恢复。
- **Windows 桌面版**：提供安装程序，也可以从源码启动本地 Web 界面。
- **应用内更新**：在「设置与备份」顶部检查本仓库 GitHub 正式版，查看中文更新说明并下载新安装包。
- **灵图助手**：连接本机 Codex，分析图片、规划批量修图/生图、提出图库整理计划；支持样图确认、Skill 管理和外部 MCP，详见 [助手使用说明](packaging/Agent助手使用说明.md)。
- **Ubuntu 网页版**：可部署在自有服务器上，通过 HTTPS 和管理员登录远程访问；部署步骤见 [Ubuntu 网页部署指南](deployment/ubuntu/README.md)。

## 下载与安装

前往 **[GitHub Releases 下载最新 Windows 安装包](https://github.com/qq911657273sr/LingTu-ART/releases/latest)**，运行 `LingTu-ART-Setup-*.exe`，然后从桌面或开始菜单启动灵图 ART。

安装程序包含应用运行环境和 FFmpeg；如果系统缺少 WebView2，安装程序会提示安装。首次启动后，选择素材库目录并导入图片或视频即可使用基础素材管理功能。

## AI 图像编辑与隐私

AI 图像编辑不是使用素材库的前提。你可以在应用设置中自行配置 OpenAI 兼容接口、Gemini 或 RunningHub 服务，以及相应的模型、工作流和 API Key。提示词助手可单独配置兼容 OpenAI 的 LLM 接口。

项目源码和公开发行包不包含个人 API Key，也不预置个人的生图或 LLM 服务地址。Windows 桌面版使用 DPAPI 加密保存服务凭据；Ubuntu 网页版使用独立 Fernet 密钥加密，并要求管理员登录。提交生成任务时，所选参考图和提示词会发送给你配置的服务提供方，并受其服务条款与隐私政策约束；未配置服务时，AI 功能不可用。

更多配置步骤见[AI 图生图使用说明](packaging/AI图生图使用说明.md)。

## 从源码运行

需要 Windows 10/11 x64、Python 3.12 和 FFmpeg/ffprobe。Node.js 22 仅在修改或重新构建前端时需要。

```powershell
git clone https://github.com/qq911657273sr/LingTu-ART.git
cd LingTu-ART
.\安装.bat
.\启动素材库.bat
```

首次安装脚本会创建 Python 虚拟环境并安装依赖。浏览器界面默认运行在 `http://127.0.0.1:8765`；关闭启动窗口即可停止本地服务。前端源码位于 `web/src/`，修改后在 `web/` 目录运行 `npm ci` 和 `npm run build`。

## 从源码构建 Windows 安装包

版本号统一保存在根目录 `version.ini`。维护者更新版本与 `docs/RELEASE_NOTES.md` 并同步到 `main` 后，GitHub Actions 会自动测试、构建并创建对应 Release；已经发布的相同版本不会自动覆盖。程序的更新按钮从 GitHub 最新正式 Release 获取版本与安装包链接。

安装 Python 3.12、Node.js 22、FFmpeg 和 [Inno Setup 6](https://jrsoftware.org/isinfo.php)，然后在仓库根目录运行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\packaging\build-windows.ps1
```

安装包会生成在 `output/installer/`。第三方组件许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 验收测试

在 Windows 且已安装项目依赖的环境中运行：

```powershell
.\.venv\Scripts\python.exe tests\acceptance.py
.\.venv\Scripts\python.exe tests\ai_acceptance.py
```

验收使用临时素材目录和本地模拟服务，不会调用付费 AI 服务，也不会修改现有素材库。

## 许可证

灵图 ART 使用 MIT 许可证。第三方组件保留各自许可证，详情见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

<div align="center">

**LingTu ART** — a local-first art asset library and AI image editing workspace for Windows.

</div>


