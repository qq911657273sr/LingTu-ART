"""媒体识别、元数据提取（复用 FML）和缩略图生成。"""

from __future__ import annotations

import base64
import io
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageOps

from .vendor.feral.extract import extract as fml_extract
from .vendor.feral.extract.types import RawMetadataItem
from .vendor.feral.interpret import interpret_items
from .vendor.feral.interpret.video import browser_support, video_stream_facts
from .vendor.feral.tools import NO_WINDOW, find_binary, media_input

Image.MAX_IMAGE_PIXELS = 400_000_000

IMAGE_CONTAINERS = {"png", "jpeg", "webp", "gif", "bmp"}
VIDEO_CONTAINERS = {"isobmff", "matroska"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".m4v", ".mkv"}
BROWSER_VIDEO_EXTS = {".mp4", ".webm", ".m4v"}
THUMB_PX = 480


class MediaError(Exception):
    """文件无法作为素材入库（用户可读的中文原因）。"""


def _exif_user_comment(path: Path) -> RawMetadataItem | None:
    """A1111/Forge 保存 JPEG/WebP 时把生成参数写在 EXIF UserComment（Exif 子 IFD），
    FML 只解码主 IFD 的字符串标签，这里补上，交给 FML 的 a1111 解析器。"""
    try:
        with Image.open(path) as img:
            raw = img.getexif().get_ifd(0x8769).get(0x9286)
    except Exception:
        return None
    if isinstance(raw, str):
        text = raw
    elif isinstance(raw, bytes) and len(raw) > 8:
        head, body = raw[:8], raw[8:]
        if head.startswith(b"UNICODE"):
            # piexif 写 UTF-16BE；个别工具写 LE —— 取解码后可打印字符更多的一种
            cands = [body.decode(enc, "ignore") for enc in ("utf-16-be", "utf-16-le")]
            text = max(cands, key=lambda s: sum(c.isprintable() for c in s))
        else:
            text = body.decode("utf-8", "ignore")
    else:
        return None
    text = text.strip("\x00").strip()
    if not text:
        return None
    return RawMetadataItem(source="exif:UserComment", keyword="parameters", text=text, data=None, encoding="utf-8")


def _raw_to_json(items: list[RawMetadataItem]) -> list[dict]:
    out = []
    for i in items:
        d = {"source": i.source, "keyword": i.keyword, "encoding": i.encoding, "compressed": i.compressed}
        if i.text is not None:
            d["text"] = i.text
        else:
            d["base64"] = base64.b64encode(i.data).decode("ascii")
        out.append(d)
    return out


def probe(path: Path, ext: str) -> dict:
    """识别素材并提取信息。无法识别/损坏抛 MediaError；元数据解析失败只记警告。"""
    try:
        with open(path, "rb") as fh:
            head = fh.read(16)
    except OSError as e:
        raise MediaError(f"无法读取文件：{e}")
    if not head:
        raise MediaError("文件为空")

    warnings: list[str] = []
    try:
        extraction = fml_extract(path)
    except Exception as e:
        raise MediaError(f"无法识别的文件格式或文件已损坏（{e.__class__.__name__}）")

    container = extraction.container
    if container in IMAGE_CONTAINERS:
        kind = "image"
        try:
            with Image.open(path) as img:
                img.load()
                width, height = img.size
        except Exception as e:
            raise MediaError(f"图片无法解码，文件可能已损坏（{e.__class__.__name__}）")
    elif container in VIDEO_CONTAINERS:
        kind = "video"
        width, height = extraction.width, extraction.height
    else:
        raise MediaError(f"不支持的格式：{container}")

    items = list(extraction.items)
    warnings.extend(extraction.warnings)
    if kind == "image" and not any(i.keyword == "parameters" for i in items):
        uc = _exif_user_comment(path)
        if uc:
            items.append(uc)

    fields: list[dict] = []
    try:
        for interp in interpret_items(items):
            fields.extend({"parser": interp.parser, "field": f.field, "value": f.value} for f in interp.fields)
    except Exception as e:  # 解析失败不能阻止入库
        warnings.append(f"生成信息解析失败：{e.__class__.__name__}: {e}")

    playable = None
    if kind == "video":
        if find_binary("ffprobe") is None:
            warnings.append("未安装 FFmpeg/ffprobe，无法读取视频时长、尺寸和编码")
        elif not extraction.width:
            raise MediaError("视频无法解析，文件可能已损坏")
        facts = {f["field"]: f["value"] for f in fields if f["parser"] == "video"}
        verdict = browser_support(facts.get("video_codec"), facts.get("video_profile"), facts.get("pixel_format"))
        playable = verdict if ext in BROWSER_VIDEO_EXTS else ("limited" if verdict == "ok" else verdict)

    return {
        "kind": kind,
        "container": container,
        "width": width,
        "height": height,
        "duration": extraction.duration,
        "fps": extraction.fps,
        "playable": playable,
        "raw_json": json.dumps(_raw_to_json(items), ensure_ascii=False),
        "fields_json": json.dumps(fields, ensure_ascii=False),
        "warnings_json": json.dumps(warnings, ensure_ascii=False),
    }


def make_thumb(src: Path, dst: Path, kind: str, duration: float | None) -> None:
    """生成 webp 缩略图/视频封面；失败抛 MediaError。"""
    if kind == "video":
        ffmpeg = find_binary("ffmpeg")
        if ffmpeg is None:
            raise MediaError("未安装 FFmpeg，无法生成视频封面")
        at = min(1.0, (duration or 0) * 0.1)
        proc = subprocess.run(
            [ffmpeg, "-v", "error", "-ss", f"{at:.2f}", *media_input(src), "-frames:v", "1",
             "-vf", f"scale='min({THUMB_PX},iw)':-2", "-f", "image2pipe", "-c:v", "png", "-"],
            capture_output=True, timeout=60, **NO_WINDOW,
        )
        if proc.returncode != 0 or not proc.stdout:
            raise MediaError("视频封面生成失败：" + proc.stderr.decode("utf-8", "ignore")[-200:])
        img = Image.open(io.BytesIO(proc.stdout))
    else:
        img = Image.open(src)
    try:
        img = ImageOps.exif_transpose(img)
        img.thumbnail((THUMB_PX, THUMB_PX))
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if "transparency" in img.info or img.mode in ("LA", "PA") else "RGB")
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_suffix(".tmp")
        img.save(tmp, "WEBP", quality=82)
        tmp.replace(dst)
    except Exception as e:
        raise MediaError(f"缩略图生成失败：{e}")


def ffmpeg_status() -> dict:
    return {"ffmpeg": find_binary("ffmpeg"), "ffprobe": find_binary("ffprobe")}
