# 美术素材库 Windows 便携版

双击项目目录中的「美术素材库.exe」，浏览器会自动打开素材库。
无需安装 Python、Node.js 或 FFmpeg。窗口显示本地服务地址；关闭该窗口即可停止服务。

当前 exe 放在原项目目录，沿用旁边的 config.json 和 data 文件夹，继续使用现有素材。
单独复制 exe 到新的可写文件夹时，会在该文件夹新建 config.json 和 data 素材库。
搬迁已有素材时，一起复制 config.json 和 data 文件夹；自定义了绝对路径的库，请同步调整配置。
关闭浏览器页面不会停止服务。程序已在运行时再次双击，只打开现有素材库。

前端、Python 运行时及 FFmpeg/ffprobe 都包含在 exe 内。
首次启动需要解包内部运行文件，可能需要数秒；素材数据库和原文件保存在 exe 外部。

## 重新构建

先在 web 目录运行 `npm run build`，然后在项目根目录运行：

```powershell
.venv\Scripts\python.exe -m pip install pyinstaller==6.22.3
.venv\Scripts\python.exe -m PyInstaller art-library.spec --noconfirm --distpath output\exe --workpath output\pyinstaller-build
.venv\Scripts\python.exe -X utf8 tests\exe_smoke.py output\exe\美术素材库.exe
```

构建机需要 FFmpeg 和 ffprobe；测试素材可通过 tests/make_samples.py 生成。
打包配置不会把个人素材、数据库或私人配置嵌入 exe。
第三方说明见项目根目录 THIRD_PARTY_NOTICES.md，以及本目录的 FFmpeg 许可证与构建说明。
