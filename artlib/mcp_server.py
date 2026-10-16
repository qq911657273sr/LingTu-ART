"""MCP stdio transport forwarding to the already-running library process.

No database, provider credentials or worker are opened by this process.
"""
import json
import os
import sys
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def forward(method, params):
    base = os.environ.get('LINGTU_AGENT_URL', '').rstrip('/')
    token = os.environ.get('LINGTU_AGENT_TOKEN', '')
    u = urlsplit(base)
    if u.scheme != 'http' or u.hostname not in ('127.0.0.1', 'localhost', '::1') or not token:
        raise ValueError('请在已运行的灵图助手连接页复制 MCP 配置；仅支持本机连接')
    req = Request(base + '/api/agent/mcp', data=json.dumps({'method': method, 'params': params}).encode(),
                  headers={'Content-Type': 'application/json', 'x-lingtu-agent-token': token})
    try:
        with urlopen(req, timeout=45) as response:
            return json.load(response)
    except HTTPError as exc:
        if exc.code == 400:
            try:
                detail = json.loads(exc.read()).get('detail', '工具参数无效')
            except ValueError:
                detail = '工具参数无效'
            raise ValueError(str(detail)[:300]) from None
        raise ValueError('灵图拒绝连接，请重新复制 MCP 配置') from exc
    except OSError as exc:
        raise ValueError('无法连接灵图，请先启动桌面应用') from exc


def handle(message):
    ident = message.get('id')
    method = message.get('method')
    if ident is None:
        return None
    try:
        if method == 'initialize':
            requested = (message.get('params') or {}).get('protocolVersion')
            version = requested if requested in ('2025-11-25', '2025-06-18', '2025-03-26', '2024-11-05') else '2025-11-25'
            result = {'protocolVersion': version, 'capabilities': {'tools': {}},
                      'serverInfo': {'name': 'lingtu-art', 'version': '1.3.0'},
                      'instructions': '先读取 lingtu_state 确认图库和窗口。工具只能创建计划，执行须由用户在灵图确认。'}
        elif method == 'ping':
            result = {}
        elif method in ('tools/list', 'tools/call'):
            try:
                result = forward(method, message.get('params') or {})
            except ValueError as exc:
                if method != 'tools/call':
                    raise
                result = {'isError': True, 'content': [{'type': 'text', 'text': str(exc)}]}
        else:
            return {'jsonrpc': '2.0', 'id': ident, 'error': {'code': -32601, 'message': 'Method not found'}}
        return {'jsonrpc': '2.0', 'id': ident, 'result': result}
    except Exception as exc:
        return {'jsonrpc': '2.0', 'id': ident, 'error': {'code': -32603, 'message': str(exc)[:300]}}


def main():
    for line in sys.stdin.buffer:
        try:
            request = json.loads(line)
            reply = handle(request) if isinstance(request, dict) else {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': 'Invalid request'}}
        except ValueError:
            reply = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Parse error'}}
        if reply is not None:
            sys.stdout.buffer.write((json.dumps(reply, ensure_ascii=False) + '\n').encode())
            sys.stdout.buffer.flush()


if __name__ == '__main__':
    main()
