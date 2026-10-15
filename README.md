# 灵图 ART · LingTu ART

**A local-first asset library for AI artists.** Organize, preview, search, and reuse images and videos on Windows, with optional AI image editing through providers you configure.

灵图 ART 是面向个人创作者的本地美术素材库。素材、数据库和服务配置默认保存在本机；应用只在本机回环地址提供界面。使用 AI 修图时，参考图和提示词会发送到你选择并配置的服务商。

## Features

- Import and organize images and videos with folders, tags, favorites, notes, and fast search.
- Preview, compare, zoom, and navigate assets; inspect image dimensions and generation metadata.
- Read metadata from common ComfyUI, A1111/Forge, XMP, and video workflows.
- Use the optional AI image editor with OpenAI-compatible, Gemini, and RunningHub providers.
- Keep originals untouched; save generated results to the library only when you choose.
- Back up and restore the library to a separate folder.
- Run as a browser-based local app or as a standalone Windows desktop app.

## Quick start (Windows)

1. Download the latest installer from the [GitHub Releases](https://github.com/qq911657273sr/LingTu-ART/releases) page.
2. Run `LingTu-ART-Setup-*.exe` and launch **灵图 ART** from the desktop or Start menu.
3. Import images or videos into the library. Configure AI providers in **Settings → AI image editing** if needed.

The desktop installer bundles the app runtime and FFmpeg. WebView2 is installed by the setup program if it is missing.

## Run from source

Requirements: Windows 10/11 x64, Python 3.12, FFmpeg/ffprobe, and Node.js 22 (only needed to rebuild the frontend).

```powershell
git clone https://github.com/qq911657273sr/LingTu-ART.git
cd LingTu-ART
.\安装.bat
.\启动素材库.bat
```

The first-run script creates `.venv`, installs Python dependencies, and checks for FFmpeg. The checked-in `web/dist` lets you run without Node.js; to change the UI, run `cd web`, `npm ci`, and `npm run build` first.

The browser interface opens at `http://127.0.0.1:8765`. Close the console window to stop the local service. Local settings are created on first launch; never commit your `config.json` or `data/` directory.

## Build the Windows desktop installer

Install Python 3.12, Node.js 22, FFmpeg, and [Inno Setup 6](https://jrsoftware.org/isinfo.php). Then run PowerShell from the repository root:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\packaging\build-windows.ps1
```

The script builds the frontend and PyInstaller app, then creates an installer in `output/installer/`. The build uses the FFmpeg executable found on your machine; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for third-party licenses.

## AI image editing and privacy

AI editing is optional. Add your provider endpoint, model/workflow, and API key in the app settings. Credentials are protected with Windows DPAPI. On generation, selected reference images and prompts are sent to the provider you configured, subject to that provider's terms and privacy policy. This project does not include API credentials or provide AI service access.

See [AI image editing guide (Chinese)](packaging/AI图生图使用说明.md) for setup details.

## Tests

On Windows, with Python dependencies installed:

```powershell
.\.venv\Scripts\python.exe tests\acceptance.py
.\.venv\Scripts\python.exe tests\ai_acceptance.py
```

The acceptance suites use temporary data and local mock providers; they do not call paid AI services or modify your library.

## Project structure

```text
artlib/                 Python/FastAPI backend
artlib/vendor/feral/    FML metadata parsing code (see its MIT license)
web/src/                React frontend source
web/dist/               Frontend assets used by the Python app
tests/                  Local acceptance tests
packaging/              Windows installer, icon, build script, and docs
```

## License

LingTu ART is distributed under the MIT License. Third-party components retain their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

