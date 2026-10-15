"""Real HTTP integration with local fake providers; never contacts paid services."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import uuid

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
WORK = Path(tempfile.mkdtemp(prefix='artspace-ai-test-'))
CALLS = []
KEY = 'mock-local-key-only'


def image(color, label):
    im = Image.new('RGB', (960, 720), color)
    d = ImageDraw.Draw(im)
    d.polygon([(0, 570), (330, 140), (530, 440), (710, 210), (960, 570)], fill='#95a8a9')
    d.rectangle((360, 280, 590, 580), fill='#dce3d4')
    d.rectangle((430, 410, 520, 580), fill='#527478')
    d.text((50, 50), label, fill='white', font_size=40)
    b = io.BytesIO(); im.save(b, 'PNG'); return b.getvalue()


ORIGINAL = image('#304d4b', 'Reference / Original')
RESULT = image('#768fa6', 'AI / Local simulation')
B64 = base64.b64encode(RESULT).decode()


class Mock(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, data, status=200, mime='application/json'):
        raw = json.dumps(data).encode() if mime == 'application/json' else data
        self.send_response(status); self.send_header('Content-Type', mime); self.end_headers(); self.wfile.write(raw)

    def do_GET(self):
        CALLS.append((self.path, dict(self.headers), b''))
        self.send(RESULT, mime='image/png')

    def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))
        CALLS.append((self.path, dict(self.headers), body))
        if self.path.startswith('/fail/'):
            return self.send({'error': {'message': KEY}}, 401)
        if self.path.startswith('/empty/'):
            return self.send({'data': []})
        if self.path.startswith('/slow/'):
            time.sleep(10)
        if self.path.endswith('/images/edits'):
            return self.send({'data': [{'b64_json': B64}]})
        if self.path.endswith(':generateContent'):
            return self.send({'candidates': [{'content': {'parts': [{'inlineData': {'mimeType': 'image/png', 'data': B64}}]}}]})
        if self.path.endswith('/chat/completions'):
            return self.send({'choices': [{'message': {'content': f'![image](http://127.0.0.1:{self.server.server_port}/image.png)'}}]})
        if self.path.endswith('/upload'):
            return self.send({'code': 0, 'data': {'fileName': 'input/mock.png'}})
        if self.path.endswith(('/create', '/ai-app/run')):
            return self.send({'code': 0, 'data': {'taskId': 'mock-task'}})
        if self.path.endswith('/outputs'):
            return self.send({'code': 0, 'data': [{'fileType': 'png', 'fileUrl': f'http://127.0.0.1:{self.server.server_port}/image.png'}]})
        self.send({'error': 'unknown mock path'}, 404)


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0)); return s.getsockname()[1]


PORT = free_port()
BASE = f'http://127.0.0.1:{PORT}'
mock = ThreadingHTTPServer(('127.0.0.1', 0), Mock)
threading.Thread(target=mock.serve_forever, daemon=True).start()
MOCK = f'http://127.0.0.1:{mock.server_port}'
config = WORK / 'config.json'
config.write_text(json.dumps({'port': PORT, 'data_dir': str(WORK / 'data'), 'backup_dir': str(WORK / 'backups'), 'export_dir': str(WORK / 'exports'), 'open_browser': False}), 'utf-8')
process = None
checks = []


def http(method, path, data=None, raw=None):
    body = raw if raw is not None else json.dumps(data).encode() if data is not None else None
    headers = {'Content-Type': 'application/json'} if data is not None else {}
    try:
        with urlopen(Request(BASE + path, data=body, headers=headers, method=method), timeout=30) as response:
            raw = response.read()
            return response.status, json.loads(raw) if 'json' in response.headers.get('Content-Type', '') else raw
    except HTTPError as e:
        return e.code, json.loads(e.read())


def check(condition, label):
    if not condition:
        raise AssertionError(label)
    checks.append(label); print('PASS', label, flush=True)


def start():
    global process
    args = [sys.executable, '-m', 'artlib', '--no-browser']
    if '--exe' in sys.argv:
        args = [sys.argv[sys.argv.index('--exe') + 1], '--no-browser']
    log = open(WORK / 'server.log', 'a', encoding='utf-8')
    process = subprocess.Popen(args, cwd=ROOT, env={**os.environ, 'ARTLIB_CONFIG': str(config)}, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(100):
        try:
            if http('GET', '/api/ping')[0] == 200:
                return
        except OSError:
            pass
        time.sleep(.2)
    raise RuntimeError('server did not start: ' + (WORK / 'server.log').read_text('utf-8'))


def stop():
    if process and process.poll() is None:
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
        process.wait(10)


def profile(kind, base=None, **extra):
    p = {'name': '模拟 ' + kind, 'kind': kind, 'base_url': base or MOCK + ('/v1beta' if kind == 'gemini' else '/v1'),
         'model': 'test-image-model', 'api_key': KEY, 'max_refs': 2}
    if kind == 'runninghub':
        p.update(base_url=MOCK, workflow_id='123456', rh_mode='workflow', prompt_node={'nodeId': '6', 'fieldName': 'text'}, image_nodes=[{'nodeId': '8', 'fieldName': 'image'}])
    p.update(extra)
    status, data = http('POST', '/api/ai/profiles', p)
    assert status == 200, data
    return data['profiles'][-1]


def submit(p, refs, prompt='把图 1 改为冬日，保持建筑结构', request_id=None):
    data = {'profile_id': p['id'], 'references': refs, 'prompt': prompt, 'request_id': request_id or uuid.uuid4().hex}
    status, job = http('POST', '/api/ai/jobs', data)
    assert status == 200, job
    return job, data


def completed(job):
    for _ in range(100):
        value = http('GET', '/api/ai/jobs/' + job['id'])[1]
        if value['status'] != 'running':
            return value
        time.sleep(.15)
    raise AssertionError('job timeout')


try:
    start()
    _, a = http('POST', '/api/import?name=reference.png', raw=ORIGINAL)
    aid = a['asset_id']; refs = [{'type': 'asset', 'id': aid, 'name': '庭院参考'}]
    check(http('GET', '/file/' + aid)[1] == ORIGINAL, 'original imported intact')
    check(http('POST', '/api/ai/references', raw=b'not an image')[0] == 400, 'invalid image rejected')
    p = profile('openai')
    check(p['has_key'] and 'secret' not in p and 'api_key' not in p, 'settings redact credentials')
    settings_file = WORK / 'data/ai-edit/settings.json'
    check(KEY not in settings_file.read_text(), 'DPAPI encrypts credential on disk')
    p = profile('openai', id=p['id'], api_key='')
    check(p['has_key'], 'blank key preserves encrypted secret')
    _, uploaded = http('POST', '/api/ai/references', raw=RESULT)
    check(uploaded['type'] == 'upload', 'local reference upload stays outside library')
    check(http('GET', '/api/assets')[1]['total'] == 1, 'reference upload does not import an asset')
    request_id = uuid.uuid4().hex
    job, payload = submit(p, refs + [uploaded], request_id=request_id)
    same = http('POST', '/api/ai/jobs', payload)[1]
    check(same['id'] == job['id'], 'duplicate request id is idempotent')
    polling = threading.Event()
    def read_during_completion():
        while not polling.is_set():
            http('GET', '/api/ai/jobs/' + job['id'])
            http('GET', '/api/ai/jobs/' + job['id'] + '/input/0')
    readers = [threading.Thread(target=read_during_completion) for _ in range(4)]
    for reader in readers: reader.start()
    try:
        job = completed(job)
    finally:
        polling.set()
        for reader in readers: reader.join()
    check(job['status'] == 'completed', 'OpenAI multipart edit completes')
    bodies = [b for path, h, b in CALLS if path == '/v1/images/edits']
    check(len(bodies) == 1 and bodies[0].count(b'name="image[]"') == 2, 'reference order and multi-image multipart are preserved')
    check(http('GET', '/api/assets')[1]['total'] == 1, 'generation does not auto-import')
    result = http('GET', f'/api/ai/jobs/{job["id"]}/result')[1]
    Image.open(io.BytesIO(result)).verify()
    _, saved = http('POST', f'/api/ai/jobs/{job["id"]}/save')
    saved2 = http('POST', f'/api/ai/jobs/{job["id"]}/save')[1]
    check(saved['asset_id'] == saved2['asset_id'] and http('GET', '/api/assets')[1]['total'] == 2, 'save is idempotent and creates one asset')
    detail = http('GET', '/api/assets/' + saved['asset_id'])[1]
    check(detail['manual_prompt'] == job['prompt'] and aid in detail['note'], 'prompt and lineage stored in asset details')
    check(http('GET', '/file/' + aid)[1] == ORIGINAL, 'source asset never overwritten')
    for kind in ('gemini', 'chat', 'runninghub'):
        p2 = profile(kind)
        next_job, _ = submit(p2, [{'type': 'job', 'id': job['id'], 'name': '上一轮结果'}])
        next_job = completed(next_job)
        check(next_job['status'] == 'completed', kind + ' adapter and continued editing')
    papp = profile('runninghub', rh_mode='app', name='模拟 RunningHub 应用')
    check(completed(submit(papp, refs)[0])['status'] == 'completed', 'RunningHub AI application adapter')
    check(all('Authorization' not in h for path, h, b in CALLS if path == '/image.png'), 'result downloads do not forward API keys')
    bad = profile('openai', MOCK + '/fail')
    failed = completed(submit(bad, refs)[0])
    check(failed['status'] == 'failed' and '401' in failed['error'] and KEY not in json.dumps(failed), 'auth failures readable with no secret leakage')
    empty = profile('openai', MOCK + '/empty')
    check(completed(submit(empty, refs)[0])['status'] == 'failed', 'missing image response fails explicitly')
    missing = profile('openai', api_key='')
    code, _ = http('POST', '/api/ai/jobs', {'profile_id': missing['id'], 'references': refs, 'prompt': 'test', 'request_id': uuid.uuid4().hex})
    check(code == 400, 'missing credentials block submission')
    code, _ = http('POST', '/api/ai/jobs', {**payload, 'request_id': uuid.uuid4().hex, 'references': refs * 3})
    check(code == 400, 'too many references rejected instead of silently dropping')
    _, presets = http('POST', '/api/ai/presets', {'presets': [{'name': '冬日', 'text': '改为冬日雪景'}]})
    check(len(presets['presets']) == 1, 'prompt presets saved')
    slow = profile('openai', MOCK + '/slow')
    running, _ = submit(slow, refs)
    check(http('DELETE', '/api/ai/jobs/' + running['id'])[0] == 409, 'running jobs cannot be deleted')
    switch_code = http('POST', '/api/library/switch', {'dir': str(WORK / 'data')})[0]
    check(switch_code == 400, 'library switching blocked while a job is running')
    stop(); start()
    restored = http('GET', '/api/ai/jobs')[1]
    check(any(j['id'] == job['id'] and j['status'] == 'completed' for j in restored), 'completed jobs persist after restart')
    check(any(j['id'] == running['id'] and j['status'] == 'interrupted' for j in restored), 'interrupted tasks do not resubmit on restart')
    check(http('GET', '/api/ai/settings')[1]['presets'][0]['name'] == '冬日', 'presets persist after restart')
    http('POST', '/api/backup')
    for _ in range(100):
        task = http('GET', '/api/settings')[1]['task']
        if not task['running']: break
        time.sleep(.1)
    assert not task.get('error'), task
    backup_path = task['result']['path']
    target = WORK / 'restored'
    http('POST', '/api/restore', {'path': backup_path, 'target': str(target)})
    for _ in range(100):
        task = http('GET', '/api/settings')[1]['task']
        if not task['running']: break
        time.sleep(.1)
    assert not task.get('error'), task
    check((target / 'ai-edit/jobs' / job['id'] / 'result.png').read_bytes() == result, 'backup restores generated results and job metadata')
    check(KEY not in (target / 'ai-edit/settings.json').read_text('utf-8'), 'backup preserves encrypted settings without plaintext key')
    check(http('DELETE', '/api/ai/jobs/' + job['id'])[0] == 200, 'completed job can be deleted')
    check(http('GET', '/api/ai/jobs/' + job['id'])[0] == 404 and http('GET', '/file/' + saved['asset_id'])[0] == 200, 'deleting a saved job preserves its library asset')
    print(f'PASS {len(checks)} checks. Work: {WORK}', flush=True)
    (ROOT / 'output/ai-test-latest.json').write_text(json.dumps({'base': BASE, 'work': str(WORK), 'mock': MOCK, 'checks': checks, 'asset_id': aid, 'job_id': job['id']}, ensure_ascii=False, indent=2), 'utf-8')
    if '--serve' in sys.argv:
        print('UI test server: ' + BASE, flush=True)
        while True:
            time.sleep(1)
finally:
    stop(); mock.shutdown()
