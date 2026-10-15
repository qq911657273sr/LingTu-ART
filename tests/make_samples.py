"""生成临时测试素材到 tests/samples/（中文路径、同名不同内容、损坏文件、带生成参数的图、视频）。"""
import json, shutil, subprocess, sys
from pathlib import Path
from PIL import Image, PngImagePlugin

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from artlib.vendor.feral.tools import find_binary

root = Path(__file__).resolve().parent / "samples" / "测试 素材"
shutil.rmtree(root.parent, ignore_errors=True)
(root / "批次A").mkdir(parents=True)
(root / "批次B").mkdir(parents=True)

a1111 = ("masterpiece, 沈青, white robe, <lora:hanfu_v2:0.8>\nNegative prompt: lowres, bad hands\n"
         "Steps: 28, Sampler: DPM++ 2M, Schedule type: Karras, CFG scale: 6.5, Seed: 123456789, "
         "Size: 512x768, Model hash: abc123, Model: sdxl_base_1.0")
info = PngImagePlugin.PngInfo(); info.add_text("parameters", a1111)
Image.new("RGB", (512, 768), (200, 60, 60)).save(root / "批次A" / "沈青 白衣造型.png", pnginfo=info)

prompt = {"3": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 20, "cfg": 7.0, "sampler_name": "euler",
          "scheduler": "normal", "denoise": 1.0, "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0]}},
          "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "dreamshaper_8.safetensors"}},
          "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "古风庭院，夜景，灯笼", "clip": ["4", 1]}},
          "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry", "clip": ["4", 1]}}}
workflow = {"last_node_id": 7, "nodes": [{"id": 3, "type": "KSampler"}], "links": [], "version": 0.4}
info = PngImagePlugin.PngInfo(); info.add_itxt("prompt", json.dumps(prompt)); info.add_itxt("workflow", json.dumps(workflow))
Image.new("RGB", (768, 512), (40, 80, 160)).save(root / "批次A" / "庭院 夜景.png", pnginfo=info)

# 同名不同内容
Image.new("RGB", (300, 300), (10, 200, 10)).save(root / "批次A" / "道具 灯笼.jpg", quality=90)
Image.new("RGB", (300, 300), (200, 200, 10)).save(root / "批次B" / "道具 灯笼.jpg", quality=90)
# 完全重复（与 批次A/沈青 白衣造型.png 字节相同）
shutil.copy(root / "批次A" / "沈青 白衣造型.png", root / "批次B" / "沈青 白衣造型 副本.png")
Image.new("RGBA", (256, 256), (255, 0, 255, 128)).save(root / "批次B" / "场景 透明.webp")
frames = [Image.new("P", (64, 64), i * 40) for i in range(5)]
frames[0].save(root / "批次B" / "动图.gif", save_all=True, append_images=frames[1:], duration=100, loop=0)
# 伪造的生成参数（异常）
info = PngImagePlugin.PngInfo(); info.add_text("parameters", "Steps: abc, Seed: , Model"); info.add_itxt("workflow", "{not json")
Image.new("RGB", (64, 64)).save(root / "批次B" / "异常参数.png", pnginfo=info)
# 损坏文件
(root / "批次B" / "损坏图片.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
(root / "批次B" / "不是图片.jpg").write_bytes(b"hello world, not an image")

ff = find_binary("ffmpeg")
if ff:
    for name, args in (("角色 动作 测试.mp4", ["-c:v", "libx264", "-pix_fmt", "yuv420p"]),
                       ("场景 环境.webm", ["-c:v", "libvpx-vp9", "-b:v", "200k"]),
                       ("ProRes 母版.mov", ["-c:v", "prores_ks"])):
        subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=24:duration=3",
                        *args, str(root / "批次B" / name)], check=True)
    (root / "批次B" / "损坏视频.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 100)
print(root)
for p in sorted(root.rglob("*")):
    if p.is_file():
        print(" ", p.relative_to(root), p.stat().st_size)
