"""Small bidirectional JSONL app-server client. No shell execution or credential copying."""
from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
from pathlib import Path


def command():
    native = shutil.which('codex.exe' if os.name == 'nt' else 'codex')
    if native:
        return [native]
    if os.name == 'nt':
        npm_root = Path(os.environ.get('APPDATA', '')) / 'npm' / 'node_modules' / '@openai' / 'codex'
        binaries = list(npm_root.glob('node_modules/@openai/codex-win32-*/vendor/*/bin/codex.exe'))
        if binaries:
            return [str(binaries[0])]
        entry = npm_root / 'bin' / 'codex.js'
        if entry.exists() and shutil.which('node'):
            return [shutil.which('node'), str(entry)]
    raise ValueError('未检测到 Codex CLI，请安装并运行 codex login 后重新连接')


class Codex:
    def __init__(self, on_event, on_request):
        self.on_event = on_event
        self.on_request = on_request
        self.process = None
        self.pending = {}
        self.lock = threading.RLock()
        self.write_lock = threading.Lock()
        self.counter = 0
        self.generation = 0
        self.info = {}

    def start(self, workspace):
        if self.process and self.process.poll() is None:
            return self.info
        cmd = command()
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        version = subprocess.run(cmd + ['--version'], capture_output=True, text=True, timeout=10, creationflags=flags)
        self.generation += 1
        generation = self.generation
        self.process = subprocess.Popen(cmd + ['app-server', '--stdio', '-c', 'project_doc_max_bytes=0'],
            cwd=workspace, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding='utf-8', bufsize=1, creationflags=flags)
        process = self.process
        threading.Thread(target=self._read, args=(process, generation), daemon=True, name='LingTu-Codex-rpc').start()
        self.info = {'version': version.stdout.strip()[:100]}
        self.request('initialize', {'clientInfo': {'name': 'lingtu_art', 'title': '灵图 ART', 'version': '1.3.0'},
                                    'capabilities': {'experimentalApi': True}}, timeout=20)
        self.send({'method': 'initialized'})
        account = self.request('account/read', {'refreshToken': False})
        self.info.update(state='connected' if account.get('account') or not account.get('requiresOpenaiAuth', True) else 'not_logged_in',
                         auth_mode=(account.get('account') or {}).get('type'))
        return self.info

    def send(self, msg):
        with self.write_lock:
            if not self.process or self.process.poll() is not None:
                raise ValueError('Codex 已断开，请重新连接')
            self.process.stdin.write(json.dumps(msg, ensure_ascii=False) + '\n')
            self.process.stdin.flush()

    def request(self, method, params=None, timeout=45):
        with self.lock:
            self.counter += 1
            ident = self.counter
            waiter = queue.Queue(maxsize=1)
            self.pending[ident] = waiter
        try:
            self.send({'id': ident, 'method': method, 'params': params or {}})
            try:
                reply = waiter.get(timeout=timeout)
            except queue.Empty:
                raise ValueError('Codex 请求超时，请重连后查看会话状态；未自动重发消息') from None
            if 'error' in reply:
                raise ValueError(str(reply['error'].get('message') or 'Codex 协议错误')[:600])
            return reply.get('result', {})
        finally:
            with self.lock:
                self.pending.pop(ident, None)

    def _serve(self, msg, generation):
        try:
            result = self.on_request(msg['method'], msg.get('params') or {})
        except Exception as exc:
            result = {'contentItems': [{'type': 'inputText', 'text': str(exc)[:500]}], 'success': False}
        try:
            if generation == self.generation:
                self.send({'id': msg['id'], 'result': result})
        except (ValueError, OSError):
            pass

    def _read(self, process, generation):
        try:
            for line in process.stdout:
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if 'method' in msg:
                    if 'id' in msg:
                        threading.Thread(target=self._serve, args=(msg, generation), daemon=True).start()
                    else:
                        self.on_event(msg['method'], msg.get('params') or {})
                else:
                    with self.lock:
                        waiter = self.pending.get(msg.get('id'))
                    if waiter:
                        waiter.put_nowait(msg)
        finally:
            if generation == self.generation:
                self.info['state'] = 'disconnected'
                with self.lock:
                    for q in self.pending.values():
                        if q.empty():
                            q.put_nowait({'error': {'message': 'Codex 进程已退出，请重新连接'}})
                self.on_event('lingtu/disconnected', {})

    def close(self):
        process = self.process
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        self.process = None
        self.info['state'] = 'disconnected'
