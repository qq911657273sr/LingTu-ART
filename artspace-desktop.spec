from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules
from artlib.vendor.feral.tools import find_binary

root = Path(SPECPATH)
tools = []
for name in ("ffmpeg", "ffprobe"):
    path = find_binary(name)
    if not path:
        raise RuntimeError(f"Missing {name}")
    tools.append((path, "bin"))
a = Analysis([str(root / "native_entry.py")], pathex=[str(root)], binaries=tools,
    datas=[(str(root / "web" / "dist"), "web/dist"), (str(root / "packaging" / "artspace.ico"), "."),
           (str(root / "THIRD_PARTY_NOTICES.md"), "."), (str(root / "packaging" / "FFmpeg-LICENSE.txt"), "licenses"),
           (str(root / "packaging" / "FFmpeg-README.txt"), "licenses"), (str(root / "artlib" / "vendor" / "feral" / "LICENSE"), "licenses/feral")],
    hiddenimports=collect_submodules("uvicorn") + collect_submodules("artlib.vendor.feral"),
    excludes=["tkinter", "pytest", "PyInstaller", "PyQt5", "PyQt6", "PySide2", "PySide6"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ARTSPACE", icon=str(root / "packaging" / "artspace.ico"), console=False, upx=False)
collect = COLLECT(exe, a.binaries, a.datas, name="ARTSPACE", upx=False)
