"""HTTP and real stdio MCP acceptance. No Codex inference or paid image calls."""
import base64
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
WORK = Path(tempfile.mkdtemp(prefix='lingtu-agent-http-'))
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0)); PORT = sock.getsockname()[1]
BASE = f'http://127.0.0.1:{PORT}'
config = WORK / 'config.json'
config.write_text(json.dumps({'host': '127.0.0.1', 'port': PORT, 'data_dir': str(WORK / 'data'), 'open_browser': False}), 'utf-8')
log = open(WORK / 'server.log', 'w', encoding='utf-8')
server_command = [str(Path(sys.argv[1]).resolve()), '--no-browser'] if len(sys.argv) > 1 else [sys.executable, '-m', 'artlib', '--no-browser']
process = subprocess.Popen(server_command, cwd=ROOT,
    env={**os.environ, 'ARTLIB_CONFIG': str(config), 'LOCALAPPDATA': str(WORK)}, stdout=log, stderr=log,
    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
mcp = None
checks = 0


def http(method, path, data=None, raw=None, headers=None, timeout=20):
    req = Request(BASE + path, data=raw if raw is not None else json.dumps(data).encode() if data is not None else None,
                  method=method, headers={**({'Content-Type': 'application/json'} if data is not None else {}), **(headers or {})})
    try:
        with urlopen(req, timeout=timeout) as response:
            body = response.read()
            return response.status, json.loads(body) if 'json' in response.headers.get('Content-Type', '') else body
    except HTTPError as exc:
        return exc.code, json.loads(exc.read())


def check(condition, label):
    global checks
    if not condition: raise AssertionError(label)
    checks += 1; print('PASS', label, flush=True)


def rpc(method, params=None):
    mcp.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': checks + 100, 'method': method, 'params': params or {}}) + '\n'); mcp.stdin.flush()
    result = json.loads(mcp.stdout.readline())
    if result.get('error'): raise AssertionError(result['error'])
    return result['result']


try:
    for _ in range(180):
        try:
            if http('GET', '/api/ping', timeout=.3)[0] == 200: break
        except OSError: time.sleep(.5)
    else:
        for diagnostic in (WORK / 'server.log', WORK / 'ARTSPACE' / 'desktop.log'):
            if diagnostic.exists(): print(diagnostic.read_text('utf-8', errors='replace')[-12000:], flush=True)
        raise RuntimeError('HTTP server failed: ' + str(WORK))
    check(http('GET', '/api/agent/status')[0] == 200, 'agent status available without starting inference')
    check(http('GET', '/api/update')[1]['current_version'] == '1.4.1', 'shared application version available in source and frozen build')
    check(http('POST', '/api/agent/context', {}, headers={'Origin': 'https://unrelated.example'})[0] == 403, 'cross-site Agent requests rejected')
    check(http('POST', '/api/agent/mcp', {'method': 'tools/list'})[0] == 403, 'MCP rejects missing token')
    image = io.BytesIO(); Image.new('RGB', (80, 120), '#668877').save(image, 'PNG')
    code, imported = http('POST', '/api/import?name=reference.png', raw=image.getvalue())
    aid = imported['asset_id']; check(code == 200, 'isolated test reference imported')
    s = http('POST', '/api/agent/sessions', {})[1]
    view = 'a' * 32
    check(http('POST', '/api/agent/context', {'view_id': view, 'selected_ids': [aid], 'scope': 'all'})[0] == 200, 'selection snapshot stored')
    cfg = http('GET', '/api/agent/mcp-config')[1]['mcpServers']['lingtu-art']
    mcp = subprocess.Popen([cfg['command'], *cfg['args']], cwd=cfg['cwd'], env={**os.environ, **cfg['env']},
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8',
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    check(rpc('initialize', {'protocolVersion': '2025-11-25', 'capabilities': {}, 'clientInfo': {'name': 'test', 'version': '1'}})['serverInfo']['name'] == 'lingtu-art', 'real stdio MCP initialize')
    check(len(rpc('tools/list')['tools']) >= 8, 'real MCP tools discoverable')
    state = json.loads(rpc('tools/call', {'name': 'lingtu_state', 'arguments': {'view_id': view}})['content'][0]['text'])
    check(state['views'][0]['selected_ids'] == [aid], 'external MCP reads same selection and library')
    result = rpc('tools/call', {'name': 'lingtu_preview', 'arguments': {'asset_id': aid}})
    check(result['content'][0]['type'] == 'image', 'MCP preview returns real image content')
    result = rpc('tools/call', {'name': 'lingtu_create_plan', 'arguments': {'request_id': 'http-unique-plan', 'title': 'Favorite test', 'kind': 'organize', 'items': [{'asset_id': aid, 'changes': {'favorite': True}}]}})
    plan = json.loads(result['content'][0]['text'])
    check(plan['status'] == 'awaiting_approval' and 'approval_token' not in plan, 'MCP can propose but receives no approval nonce')
    check(not http('GET', '/api/assets/' + aid)[1]['favorite'], 'proposal has no side effects')
    check(http('POST', f"/api/agent/plans/{plan['id']}/approve", {'token': 'guessed', 'revision': 1})[0] == 400, 'forged plan approval rejected')
    ui_plan = http('GET', '/api/agent/plans')[1][0]
    approval = {'token': ui_plan['approval_token'], 'revision': ui_plan['revision']}
    check(http('POST', f"/api/agent/plans/{plan['id']}/approve", approval)[0] == 200, 'UI approves specific plan')
    check(http('GET', '/api/assets/' + aid)[1]['favorite'] == 1, 'approved operation applied')
    check(http('POST', f"/api/agent/plans/{plan['id']}/approve", approval)[0] == 200, 'repeated approval idempotent')
    check(http('POST', f"/api/agent/plans/{plan['id']}/undo", {})[0] == 200, 'approved organization undo available')
    check(not http('GET', '/api/assets/' + aid)[1]['favorite'], 'undo restores original value')
    skill = b'---\nname: http-skill\ndescription: >\n  Example multiline skill\n  for HTTP tests.\n---\nUse library tools.'
    check(http('POST', '/api/agent/skills/import?name=SKILL.md', raw=skill)[0] == 200, 'standard multiline YAML Skill imports over HTTP')
    check(http('POST', '/api/agent/skills/import?name=SKILL.md', raw=b'invalid')[0] == 400, 'invalid Skill returns clear HTTP error')
    skill = skill.replace(b'http-skill', b'folder-skill')
    check(http('POST', '/api/agent/skills/import-folder', {'files': [{'name': 'folder/SKILL.md', 'data': base64.b64encode(skill).decode()}]})[0] == 200, 'directory Skill imports over HTTP')
    check(http('GET', f"/api/agent/sessions/{s['id']}/events")[0] == 200, 'reconnect event endpoint available')
    result = rpc('tools/call', {'name': 'lingtu_approve', 'arguments': {}})
    check(result.get('isError'), 'external MCP cannot call approval operation')
    print(f'PASS {checks} HTTP/MCP checks; isolated artifacts: {WORK}', flush=True)
finally:
    if mcp:
        mcp.terminate(); mcp.wait(timeout=10)
    process.terminate(); process.wait(timeout=10); log.close()
