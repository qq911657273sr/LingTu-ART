"""Windows portable executable entry point."""
import multiprocessing
import os
import sys
from pathlib import Path

if __name__ == "__main__":
    multiprocessing.freeze_support()
    if getattr(sys, "frozen", False):
        resource_dir = Path(sys._MEIPASS)
        os.environ["PATH"] = str(resource_dir / "bin") + os.pathsep + os.environ.get("PATH", "")
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    from artlib.__main__ import main
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        if getattr(sys, "frozen", False):
            input("启动失败，按回车关闭窗口…")
        raise
