"""端到端验收：在临时目录启动真实服务，通过 HTTP 走完整流程。

用法：python tests/acceptance.py      （会先生成 tests/samples 测试素材）
不会触碰你的正式素材库。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "tests" / "samples" / "测试 素材"
PORT = 8799
BASE = f"http://127.0.0.1:{PORT}"
results: list[tuple[bool, str]] = []


def check(cond, msg):
    results.append((bool(cond), msg))
    print(("  ✔ " if cond else "  ✘ ") + msg)
    return cond


def http(method, path, body=None, raw=None, headers=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    h = dict(headers or {})
    if body is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            content = r.read()
            ctype = r.headers.get("content-type", "")
            return r.status, (json.loads(content) if "json" in ctype else content), r.headers
    except urllib.error.HTTPError as e:
        content = e.read()
        try:
            return e.code, json.loads(content), e.headers
        except ValueError:
            return e.code, content, e.headers


def upload(p: Path, folder_id=None):
    q = urllib.parse.urlencode({"name": p.name, **({"folder_id": folder_id} if folder_id else {})})
    return http("POST", f"/api/import?{q}", raw=p.read_bytes())[1]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class Server:
    def __init__(self, cfg_path: Path):
        self.cfg_path = cfg_path
        self.proc = None

    def start(self):
        env = {**os.environ, "ARTLIB_CONFIG": str(self.cfg_path), "PYTHONIOENCODING": "utf-8"}
        self.proc = subprocess.Popen([sys.executable, "-m", "artlib", "--no-browser"], cwd=ROOT, env=env)
        for _ in range(100):
            try:
                if http("GET", "/api/sidebar")[0] == 200:
                    return
            except OSError:
                pass
            time.sleep(0.2)
        raise RuntimeError("服务启动失败")

    def stop(self):
        # venv 的 python.exe 是启动器，真正的解释器是子进程：按进程树结束，并等端口释放
        subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"], capture_output=True)
        self.proc.wait(10)
        for _ in range(100):
            try:
                http("GET", "/api/sidebar")
            except OSError:
                return
            time.sleep(0.1)
        raise RuntimeError("服务未能停止")


def wait_thumbs(timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if http("GET", "/api/sidebar")[1]["pending_thumbs"] == 0:
            return True
        time.sleep(0.3)
    return False


def all_assets(scope="all", **kw):
    q = urllib.parse.urlencode({"scope": scope, "limit": 500, **kw})
    return http("GET", f"/api/assets?{q}")[1]


def main():
    subprocess.run([sys.executable, str(ROOT / "tests" / "make_samples.py")], check=True, stdout=subprocess.DEVNULL)
    work = Path(tempfile.mkdtemp(prefix="素材库验收 "))
    cfg_path = work / "config.json"
    export_dir = work / "导出 目录"
    cfg_path.write_text(json.dumps({"port": PORT, "data_dir": str(work / "数据"), "backup_dir": str(work / "备份"),
                                    "export_dir": str(export_dir), "open_browser": False}, ensure_ascii=False), "utf-8")
    print(f"临时目录：{work}")
    srv = Server(cfg_path)
    srv.start()
    data = work / "数据"
    try:
        files = sorted(p for p in SAMPLES.rglob("*") if p.is_file())
        src_hashes = {p: sha(p) for p in files}

        print("\n[1] 批量导入图片和视频（含损坏文件）")
        res = {p.relative_to(SAMPLES).as_posix(): upload(p) for p in files}
        for k, v in res.items():
            print(f"     {k:28} {v['status']:9} {v.get('message', '')[:60]}")
        ok = [k for k, v in res.items() if v["status"] == "ok"]
        check(len(ok) == 10, f"成功导入 10 个（实际 {len(ok)}）")
        check(res["批次B/沈青 白衣造型 副本.png"]["status"] == "duplicate", "内容相同的副本被识别为已存在")
        for bad in ("批次B/损坏图片.png", "批次B/不是图片.jpg", "批次B/损坏视频.mp4"):
            check(res[bad]["status"] == "failed", f"损坏文件 {bad} 单独失败并给出原因：{res[bad].get('message')}")
        check(res["批次B/异常参数.png"]["status"] == "ok", "异常/残缺生成参数不影响入库")
        check(all(sha(p) == h for p, h in src_hashes.items()), "外部原文件保持不变")

        print("\n[2] 重复导入")
        n_before = len(list((data / "originals").rglob("*.*")))
        again = [upload(p)["status"] for p in files]
        n_after = len(list((data / "originals").rglob("*.*")))
        check(again.count("ok") == 0 and again.count("duplicate") == 11, f"再次导入全部识别为已存在（{again.count('duplicate')} 个）")
        check(n_before == n_after == 10, f"原文件数量不变（{n_before} → {n_after}）")

        print("\n[3] 同名不同内容、中文与空格")
        lanterns = [a for a in all_assets()["items"] if a["name"] == "道具 灯笼"]
        check(len(lanterns) == 2, "两个“道具 灯笼.jpg”都已保存")
        stored = [p.name for p in (data / "originals").rglob("*.*")]
        check("沈青 白衣造型.png" in stored and "庭院 夜景.png" in stored, "库内保留中文、空格原文件名")

        print("\n[4] 缩略图与视频封面")
        check(wait_thumbs(), "后台缩略图全部处理完毕")
        items = {a["name"]: a for a in all_assets()["items"]}
        check(all(a["thumb_state"] == 1 for a in items.values()), "所有素材（含 ProRes/WebM 视频）都有缩略图/封面")
        mp4 = items["角色 动作 测试"]
        check(mp4["kind"] == "video" and abs(mp4["duration"] - 3) < 0.2 and (mp4["width"], mp4["height"]) == (640, 360),
              f"视频尺寸/时长：{mp4['width']}x{mp4['height']} {mp4['duration']}s")
        check(items["ProRes 母版"]["playable"] == "none", "ProRes MOV 被标记为浏览器无法播放")
        check(items["场景 环境"]["playable"] == "ok", "WebM(VP9) 标记为可播放")
        check((items["沈青 白衣造型"]["width"], items["沈青 白衣造型"]["height"]) == (512, 768), "图片尺寸正确")

        print("\n[5] 生成信息")
        a1 = http("GET", f"/api/assets/{items['沈青 白衣造型']['id']}")[1]
        f1 = {f["field"]: f["value"] for f in a1["fields"]}
        check(f1.get("seed") == "123456789" and f1.get("model") == "sdxl_base_1.0" and f1.get("negative_prompt") == "lowres, bad hands",
              f"A1111：seed={f1.get('seed')} model={f1.get('model')}")
        check(f1.get("prompt", "").startswith("masterpiece, 沈青"), "A1111 中文提示词")
        c1 = http("GET", f"/api/assets/{items['庭院 夜景']['id']}")[1]
        fc = {f["field"]: f["value"] for f in c1["fields"]}
        check(fc.get("prompt") == "古风庭院，夜景，灯笼" and fc.get("seed") == "42" and fc.get("model") == "dreamshaper_8.safetensors",
              f"ComfyUI：prompt={fc.get('prompt')} seed={fc.get('seed')}")
        st, wf, hdr = http("GET", f"/api/assets/{c1['id']}/workflow?key=workflow")
        check(st == 200 and wf["last_node_id"] == 7 and "attachment" in hdr.get("content-disposition", ""), "导出 ComfyUI 工作流 JSON")
        bad = http("GET", f"/api/assets/{items['异常参数']['id']}")[1]
        fb = {f["field"]: f["value"] for f in bad["fields"]}
        check("seed" not in fb and "model" not in fb, f"异常参数缺失项留空，不猜测（解析出：{fb}）")
        check(http("GET", f"/api/assets/{bad['id']}/workflow?key=workflow")[0] == 404, "非法工作流 JSON 不提供导出")
        raw_before = http("GET", f"/api/assets/{a1['id']}/raw")[1]

        print("\n[6] 分类 / 子文件夹 / 标签 / 收藏 / 备注")
        side = http("GET", "/api/sidebar")[1]
        people = next(f for f in side["folders"] if f["name"] == "人物")
        check([f["name"] for f in side["folders"] if f["parent_id"] is None] == ["人物", "场景", "道具", "其他"], "默认分类")
        shen = http("POST", "/api/folders", {"name": "沈青", "parent_id": people["id"]})[1]["id"]
        white = http("POST", "/api/folders", {"name": "白衣造型", "parent_id": shen})[1]["id"]
        scene = next(f for f in side["folders"] if f["name"] == "场景")["id"]
        props = next(f for f in side["folders"] if f["name"] == "道具")["id"]
        http("PATCH", f"/api/folders/{props}", {"name": "道具库"})
        http("PATCH", f"/api/folders/{props}", {"move": -1})
        http("POST", "/api/batch", {"ids": [a1["id"]], "action": "move", "folder_id": white})
        http("POST", "/api/batch", {"ids": [c1["id"], items["场景 环境"]["id"]], "action": "move", "folder_id": scene})
        http("POST", "/api/batch", {"ids": [l["id"] for l in lanterns], "action": "move", "folder_id": props})
        http("POST", "/api/batch", {"ids": [a1["id"], mp4["id"]], "action": "tag_add", "tags": ["沈青", "白衣", "主角"]})
        http("POST", "/api/batch", {"ids": [mp4["id"]], "action": "tag_remove", "tags": ["白衣"]})
        http("PATCH", f"/api/assets/{a1['id']}", {"favorite": True, "note": "第三集 定妆照", "manual_platform": "即梦"})
        http("PATCH", f"/api/assets/{mp4['id']}", {"name": "沈青 走路 v2", "manual_prompt": "少女在竹林中行走"})
        fid = http("POST", "/api/folders", {"name": "临时分类"})[1]["id"]
        http("POST", "/api/batch", {"ids": [items["动图"]["id"]], "action": "move", "folder_id": fid})
        st, body, _ = http("DELETE", f"/api/folders/{fid}")
        check(st == 400, "删除非空文件夹未确认时被拒绝")
        http("DELETE", f"/api/folders/{fid}?move_to_inbox=true")
        gif = http("GET", f"/api/assets/{items['动图']['id']}")[1]
        check(gif["folder_id"] is None and gif["deleted_at"] is None, "删除文件夹后素材移入待整理，未被删除")
        check(all_assets(f"folder:{people['id']}")["total"] == 1, "父分类包含子文件夹中的素材")
        check(http("GET", f"/api/assets/{a1['id']}/raw")[1] == raw_before, "手动编辑后原始元数据不变")

        print("\n[7] 重启后数据仍在")
        srv.stop()
        srv.start()
        a1r = http("GET", f"/api/assets/{a1['id']}")[1]
        check(a1r["folder_path"] == "人物 / 沈青 / 白衣造型", f"文件夹路径：{a1r['folder_path']}")
        check(sorted(a1r["tags"]) == sorted(["主角", "白衣", "沈青"]) and a1r["favorite"] == 1 and a1r["note"] == "第三集 定妆照", "标签、收藏、备注保留")
        tops = [f["name"] for f in sorted((f for f in http("GET", "/api/sidebar")[1]["folders"] if f["parent_id"] is None), key=lambda f: f["sort_order"])]
        check(tops == ["人物", "道具库", "场景", "其他"], f"分类改名与顺序保留：{tops}")

        print("\n[8] 组合搜索")
        def ids(**kw):
            return {a["name"] for a in all_assets(**kw)["items"]}
        check(ids(q="沈青") >= {"沈青 白衣造型", "沈青 走路 v2"}, "按标签/提示词搜索“沈青”")
        check(ids(q="竹林") == {"沈青 走路 v2"}, "搜索手动补充的提示词")
        check(ids(q="庭院 灯笼") == {"庭院 夜景"}, "多个关键词同时匹配（提示词）")
        check(ids(q="定妆") == {"沈青 白衣造型"}, "搜索备注")
        check(ids(q="沈青", kind="video") == {"沈青 走路 v2"}, "搜索 + 视频筛选")
        check(ids(q="沈青", favorite="true") == {"沈青 白衣造型"}, "搜索 + 收藏筛选")
        check(ids(scope=f"folder:{people['id']}", q="沈青", kind="image") == {"沈青 白衣造型"}, "文件夹 + 搜索 + 图片")
        check(ids(scope="inbox", q="dreamshaper") == set(), "待整理范围不含已分类素材")
        check(ids(q="DREAMSHAPER") == {"庭院 夜景"}, "搜索模型名，不区分大小写")
        names = [a["name"] for a in all_assets(sort="size", order="asc")["items"]]
        sizes = [a["size"] for a in all_assets(sort="size", order="asc")["items"]]
        check(sizes == sorted(sizes), "按文件大小排序")
        check([a["name"] for a in all_assets(sort="name", order="asc")["items"]] == sorted(names, key=str.lower), "按名称排序")

        print("\n[9] 预览：原文件与视频 Range")
        st, body, hdr = http("GET", f"/file/{a1['id']}")
        check(st == 200 and hashlib.sha256(body).hexdigest() == a1["sha256"], "图片原文件字节一致")
        st, body, hdr = http("GET", f"/file/{mp4['id']}", headers={"Range": "bytes=100-199"})
        check(st == 206 and len(body) == 100, "视频支持 Range 请求（可拖动进度）")
        check(hdr.get("content-type", "").startswith("video/mp4"), f"视频 MIME：{hdr.get('content-type')}")
        st, _, hdr = http("GET", f"/file/{a1['id']}?download=1")
        check("attachment" in hdr.get("content-disposition", ""), "浏览器下载使用 attachment")

        print("\n[10] 导出")
        r = http("POST", "/api/export", {"ids": [a1["id"]]})[1]
        check(r["exported"] == ["沈青 白衣造型.png"] and sha(export_dir / r["exported"][0]) == a1["sha256"], "单个导出，哈希一致")
        r = http("POST", "/api/export", {"ids": [l["id"] for l in lanterns] + [a1["id"], mp4["id"]]})[1]
        check(len(r["exported"]) == 4 and not r["failed"], f"批量导出：{r['exported']}")
        exported = sorted(p.name for p in export_dir.iterdir())
        check("道具 灯笼.jpg" in exported and "道具 灯笼 (2).jpg" in exported and "沈青 白衣造型 (2).png" in exported, "同名文件自动编号，不互相覆盖")
        exp_hashes = sorted(sha(p) for p in export_dir.glob("道具 灯笼*.jpg"))
        check(exp_hashes == sorted(l_["sha256"] for l_ in (http("GET", f"/api/assets/{l['id']}")[1] for l in lanterns)), "导出内容与库内原文件一致")

        print("\n[11] 回收站")
        victim = items["场景 透明"]["id"]
        http("POST", "/api/batch", {"ids": [victim], "action": "trash"})
        check(victim not in {a["id"] for a in all_assets()["items"]} and victim in {a["id"] for a in all_assets("trash")["items"]}, "删除后进入回收站")
        http("POST", "/api/batch", {"ids": [victim], "action": "restore"})
        check(victim in {a["id"] for a in all_assets()["items"]}, "从回收站恢复")
        g = items["动图"]
        http("POST", "/api/batch", {"ids": [a1["id"]], "action": "purge"})
        check(http("GET", f"/api/assets/{a1['id']}")[0] == 200, "未进回收站的素材不能被彻底删除")
        http("POST", "/api/batch", {"ids": [g["id"]], "action": "trash"})
        gpath = Path(http("GET", f"/api/assets/{g['id']}")[1]["path"])
        http("POST", "/api/batch", {"ids": [g["id"]], "action": "purge"})
        check(http("GET", f"/api/assets/{g['id']}")[0] == 404 and not gpath.exists(), "彻底删除移除记录与原文件")
        check(upload(SAMPLES / "批次B" / "动图.gif")["status"] == "ok", "彻底删除后可重新导入")

        print("\n[12] 备份与恢复（独立目录）")
        http("POST", "/api/backup")
        for _ in range(200):
            task = http("GET", "/api/settings")[1]["task"]
            if not task["running"]:
                break
            time.sleep(0.2)
        check(task["result"] and not task["error"], f"备份完成：{task['result']}")
        zip_path = Path(task["result"]["path"])
        restore_dir = work / "恢复 测试"
        http("POST", "/api/restore", {"path": str(zip_path), "target": str(restore_dir)})
        for _ in range(200):
            task = http("GET", "/api/settings")[1]["task"]
            if not task["running"]:
                break
            time.sleep(0.2)
        check(task["result"] and task["result"]["assets"] == 10, f"恢复完成：{task['result'] or task['error']}")
        st, body, _ = http("POST", "/api/restore", {"path": str(zip_path), "target": str(restore_dir)})
        time.sleep(0.5)
        check("不为空" in (http("GET", "/api/settings")[1]["task"]["error"] or ""), "恢复到非空目录被拒绝（不覆盖）")
        st, _, _ = http("POST", "/api/restore", {"path": str(zip_path), "target": str(data)})
        check(st == 400, "不允许恢复到当前素材库目录")
        rc = sqlite3.connect(restore_dir / "library.db")
        rows = rc.execute("SELECT rel_path, sha256, name FROM assets").fetchall()
        tags = rc.execute("SELECT COUNT(*) FROM asset_tags").fetchone()[0]
        rc.close()
        check(all(sha(restore_dir / r[0]) == r[1] for r in rows), f"恢复目录中 {len(rows)} 个原文件哈希全部一致")
        check(tags == 5, f"标签关联已恢复（{tags} 条）")
        check(len(list(data.rglob("originals/*/*/*"))) == 10, "原素材库未被改动")
        # 在恢复出的目录上独立启动一次服务
        cfg2 = work / "config-restored.json"
        cfg2.write_text(json.dumps({"port": PORT, "data_dir": str(restore_dir), "backup_dir": str(work / "备份2"),
                                    "export_dir": str(work / "导出2"), "open_browser": False}, ensure_ascii=False), "utf-8")
        srv.stop()
        srv2 = Server(cfg2)
        srv2.start()
        try:
            check(wait_thumbs(), "恢复出的库自动重建缩略图")
            r2list = all_assets()["items"]
            r2 = {a["name"]: a for a in r2list}
            check(len(r2list) == 10 and r2["沈青 白衣造型"]["favorite"] == 1, "恢复出的库可正常浏览，收藏等信息完整")
            check(http("GET", "/api/assets?q=" + urllib.parse.quote("竹林"))[1]["total"] == 1, "恢复出的库搜索正常")
        finally:
            srv2.stop()
        srv.start()

        print("\n[13] 一万条记录分页（模拟记录，不含真实文件处理）")
        srv.stop()
        conn = sqlite3.connect(data / "library.db")
        tmpl = conn.execute("SELECT * FROM assets WHERE name='庭院 夜景'").fetchone()
        cols = [d[0] for d in conn.execute("SELECT * FROM assets LIMIT 0").description]
        rows = []
        for i in range(10_000):
            d = dict(zip(cols, tmpl))
            d.update(id=uuid.uuid4().hex, sha256=f"sim{i:08d}", name=f"模拟素材 {i:05d}", imported_at=time.time() - i,
                     search_text=f"模拟素材 {i:05d} 标签{i % 50}", size=1000 + i, kind="video" if i % 5 == 0 else "image",
                     favorite=1 if i % 17 == 0 else 0)
            rows.append(tuple(d[c] for c in cols))
        with conn:
            conn.executemany(f"INSERT INTO assets VALUES ({','.join('?' * len(cols))})", rows)
        conn.close()
        srv.start()
        timings = {}
        for label, q in (("首页", "limit=120"), ("第 50 页", "limit=120&offset=6000"), ("搜索", "q=标签7&limit=120"),
                         ("组合", "q=模拟&kind=video&favorite=true&sort=name&order=asc&limit=120"),
                         ("按大小排序末页", "sort=size&order=asc&limit=120&offset=9900")):
            t0 = time.perf_counter()
            st, body, _ = http("GET", "/api/assets?" + urllib.parse.quote(q, safe="=&"))
            timings[label] = (time.perf_counter() - t0) * 1000, body["total"], len(body["items"])
        for k, (ms, total, n) in timings.items():
            print(f"     {k:10} {ms:6.1f} ms  total={total} 返回={n}")
        check(timings["首页"][1] == 10_010 and timings["首页"][2] == 120, "总数 10010（10 真实 + 10000 模拟），单页只返回 120 条")
        check(timings["搜索"][1] == 200, f"“标签7”精确命中 200 条（{timings['搜索'][1]}）")
        check(max(ms for ms, *_ in timings.values()) < 500, "所有分页/搜索请求 < 500 ms")
        t0 = time.perf_counter()
        http("GET", "/api/sidebar")
        check((time.perf_counter() - t0) * 1000 < 500, "左栏统计 < 500 ms")
    finally:
        try:
            srv.stop()
        except Exception:
            pass

    bad = [m for ok, m in results if not ok]
    print(f"\n结果：{len(results) - len(bad)}/{len(results)} 通过")
    for m in bad:
        print("  失败：", m)
    if not bad:
        shutil.rmtree(work, ignore_errors=True)
    else:
        print(f"保留临时目录供排查：{work}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
