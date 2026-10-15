# 第三方组件与许可证声明

## 复用的源代码

### FML — Feral Media Library
- 来源：<https://github.com/Feral-Strawberry/fml>，提交 `1149e2f916b256404dfbe9b4755d8780dec4c640`（2026-09-25）
- 许可证：MIT，Copyright (c) 2026 Feral Strawberry（全文见 `artlib/vendor/feral/LICENSE`）
- 使用范围：`artlib/vendor/feral/` 下的 `extract/`（第 1 层：PNG/JPEG/WebP/GIF/视频元数据原样提取）、`interpret/`（第 2 层：ComfyUI、A1111、XMP、C2PA、Topaz、视频编码等解析器）和 `tools.py`（FFmpeg 查找）。
- 修改：删除 `interpret/reparse.py` 与 `interpret/__main__.py`（依赖 FML 自身数据库），并相应精简 `interpret/__init__.py`；其余文件未改动。上游完整仓库保存在工作区 `_upstream/fml`，仅用于评估，未被程序引用。

### 设计参考
- 配色与组件样式参考 shadcn/ui（MIT，<https://ui.shadcn.com>）的 zinc 深色主题；未复制其源码文件，以 Tailwind 类重新实现。
- 弹层、提示、批量栏的入场动效参考 transitions.dev 的交互风格，用纯 CSS 关键帧自行编写，未复制其代码。
- Beautiful UI、BeUI、Rare UI 仅作为视觉参考，未使用其代码或资源。

## 运行时依赖（Python，由 `安装.bat` 安装）

| 包 | 版本 | 许可证 |
|---|---|---|
| fastapi | 0.141.1 | MIT |
| starlette | 1.x | BSD-3-Clause |
| uvicorn | 0.53.0 | BSD-3-Clause |
| pydantic / pydantic-core | 2.x | MIT |
| anyio | 4.x | MIT |
| h11 | 0.16 | MIT |
| click | 8.x | BSD-3-Clause |
| idna | 3.x | BSD-3-Clause |
| typing-extensions, typing-inspection, annotated-types, annotated-doc | — | PSF-2.0 / MIT |
| Pillow | 12.3.0 | MIT-CMU（HPND） |

## 外部程序

- FFmpeg / ffprobe（Gyan.dev Windows full build）：源码运行时从本机查找；Windows exe 便携版内置，作为独立进程读取视频信息和截取封面帧。此构建启用了 GPL 与 version3，随附许可证和构建信息见 `packaging/FFmpeg-LICENSE.txt`、`packaging/FFmpeg-README.txt`。项目与构建来源：https://ffmpeg.org/ 、https://www.gyan.dev/ffmpeg/builds/ 。
- Python（PSF License）。

## 前端（构建时打包进 `web/dist`）

| 包 | 版本 | 许可证 |
|---|---|---|
| react / react-dom | 19.3.0 | MIT |
| lucide-react（图标） | 0.500.0 | ISC |
| tailwindcss / @tailwindcss/vite | 4.3.3 | MIT |
| vite / @vitejs/plugin-react（仅构建） | 7.3.6 / 5.2.0 | MIT |
