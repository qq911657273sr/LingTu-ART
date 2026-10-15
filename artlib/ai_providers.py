"""Image editing transports. No automatic submission retries or provider SDKs."""
from __future__ import annotations

import base64
import json
import re
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

MAX_BYTES = 40 * 1024 * 1024


def valid_url(url):
    parts = urlsplit(url)
    if parts.scheme not in ('https', 'http') or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError('接口地址必须是完整 HTTP(S) 地址，不能包含密钥、查询参数或片段')
    return url.rstrip('/')


def error_message(message, key=''):
    message = str(message)
    if key:
        message = message.replace(key, '[密钥已隐藏]')
    message = re.sub(r'(?i)(bearer\s+|api[_-]?key[\s:=\"\x27]+)[^\s,\"\x27}]+', r'\1[已隐藏]', message)
    return message[:350]


def request(url, payload=None, headers=None, raw=None, timeout=180):
    headers = dict(headers or {})
    if payload is not None:
        raw = json.dumps(payload).encode()
        headers['Content-Type'] = 'application/json'
    try:
        with urlopen(Request(url, data=raw, headers=headers), timeout=timeout) as response:
            data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError('服务返回内容超过 40 MB，请降低输出分辨率')
            return data
    except HTTPError as e:
        labels = {401: '鉴权失败，请检查 API Key', 403: '接口拒绝访问，请检查模型权限',
                  402: '余额不足', 429: '请求受限或额度不足，请稍后手动重试', 404: '接口或模型不存在，请检查地址和模型名称'}
        # Do not persist upstream bodies: gateways may echo headers, keys or images.
        raise ValueError(f'HTTP {e.code}：{labels.get(e.code, "服务请求失败，请检查接口配置或稍后手动重试")}') from None
    except (URLError, TimeoutError):
        raise ValueError('连接失败或等待超时；服务可能已受理，请先查看平台任务记录，避免重复计费') from None


def json_request(url, payload=None, headers=None, raw=None, timeout=180):
    try:
        return json.loads(request(url, payload, headers, raw, timeout=timeout))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError('服务返回的不是 JSON，请检查接口类型和地址') from None


def multipart(fields, images, file_field='image[]'):
    boundary = 'artspace-' + uuid.uuid4().hex
    chunks = []
    for name, value in fields.items():
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    for i, data in enumerate(images):
        chunks.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="reference-{i+1}.png"\r\nContent-Type: image/png\r\n\r\n'.encode(), data, b'\r\n'])
    chunks.append(f'--{boundary}--\r\n'.encode())
    return b''.join(chunks), f'multipart/form-data; boundary={boundary}'


def read_image(value):
    if not isinstance(value, str):
        raise ValueError('服务没有返回有效图片')
    if value.startswith('data:image/'):
        value = value.split(',', 1)[1]
    elif value.startswith(('https://', 'http://')):
        # Never forward API credentials to the result storage host.
        return request(value)
    try:
        raw = base64.b64decode(value, validate=True)
        if len(raw) > MAX_BYTES:
            raise ValueError()
        return raw
    except (ValueError, TypeError):
        raise ValueError('返回图片的 Base64 数据无效或超过大小限制') from None


def generate(config, key, prompt, images, update):
    base = config['base_url'].rstrip('/')
    model = config.get('model', '')
    kind = config['kind']
    headers = {'Authorization': f'Bearer {key}'}
    urls = ['data:image/png;base64,' + base64.b64encode(i).decode() for i in images]
    update(stage='正在发送参考图与提示词')
    if kind == 'openai':
        fields = {'model': model, 'prompt': prompt, 'n': '1'}
        if config.get('size'):
            fields['size'] = config['size']
        body, content_type = multipart(fields, images, 'image' if len(images) == 1 else 'image[]')
        result = json_request(base + '/images/edits', headers={**headers, 'Content-Type': content_type}, raw=body)
        item = (result.get('data') or [{}])[0]
        value = item.get('b64_json') or item.get('url')
    elif kind == 'gemini':
        parts = [{'text': prompt}] + [{'inlineData': {'mimeType': 'image/png', 'data': u.split(',', 1)[1]}} for u in urls]
        result = json_request(base + '/models/' + quote(model, safe='-._') + ':generateContent',
                              {'contents': [{'role': 'user', 'parts': parts}], 'generationConfig': {'responseModalities': ['TEXT', 'IMAGE']}},
                              {'x-goog-api-key': key})
        value = None
        for candidate in result.get('candidates', []):
            for part in candidate.get('content', {}).get('parts', []):
                image = part.get('inlineData') or part.get('inline_data') or {}
                if image.get('data'):
                    value = image['data']
                    break
            if value:
                break
    elif kind == 'chat':
        content = [{'type': 'text', 'text': prompt}] + [{'type': 'image_url', 'image_url': {'url': u}} for u in urls]
        result = json_request(base + '/chat/completions', {'model': model, 'messages': [{'role': 'user', 'content': content}], 'stream': False}, headers)
        message = (result.get('choices') or [{}])[0].get('message', {})
        content = message.get('content', '')
        value = None
        for part in (content if isinstance(content, list) else []) + message.get('images', []):
            image = part.get('image_url') or {}
            value = image.get('url') if isinstance(image, dict) else image
            if value:
                break
        if not value and isinstance(content, str):
            match = re.search(r'data:image/[\w.+-]+;base64,[A-Za-z0-9+/=]+|!\[[^\]]*\]\((https?://[^\s)]+)\)', content)
            if match:
                value = match.group(1) or match.group(0)
    elif kind == 'runninghub':
        return runninghub(config, key, prompt, images, update)
    else:
        raise ValueError('不支持的接口类型')
    if not value:
        raise ValueError('服务未返回图片，请确认所选模型支持图像编辑与图片输出')
    update(stage='正在下载并校验结果')
    return read_image(value)


def runninghub(config, key, prompt, images, update):
    base = config['base_url'].rstrip('/')
    headers = {'Authorization': f'Bearer {key}'}
    mappings = config['image_nodes']
    nodes = list(config.get('extra_nodes', []))
    v2 = config.get('rh_version') == 'v2'
    uploaded = []
    for image in images:
        body, content_type = multipart({'apiKey': key, 'fileType': 'input'}, [image], 'file')
        endpoint = '/openapi/v2/media/upload/binary' if v2 else '/task/openapi/upload'
        if v2:
            body, content_type = multipart({}, [image], 'file')
        result = json_request(base + endpoint, headers={**headers, 'Content-Type': content_type}, raw=body)
        name = (result.get('data') or {}).get('fileName')
        if result.get('code') != 0 or not name:
            raise ValueError('RunningHub 上传失败：' + error_message(result.get('msg', '未返回文件名'), key))
        uploaded.append(name)
    if config.get('repeat_main') and uploaded:
        uploaded += [uploaded[0]] * (len(mappings) - len(uploaded))
    nodes.extend({**mapping, 'fieldValue': name} for mapping, name in zip(mappings, uploaded))
    nodes.append({**config['prompt_node'], 'fieldValue': prompt})
    app_mode = config.get('rh_mode') == 'app'
    if v2:
        route = 'ai-app' if app_mode else 'workflow'
        result = json_request(base + '/openapi/v2/run/' + route + '/' + config['workflow_id'],
                              {'nodeInfoList': nodes, 'instanceType': config.get('instance_type', 'default'), 'usePersonalQueue': False}, headers)
        task_id = result.get('taskId')
        if not task_id:
            raise ValueError('RunningHub 提交失败：' + error_message(result.get('errorMessage') or result.get('message') or '未返回任务 ID', key))
        update(remote_id=str(task_id), stage='RunningHub 排队 / 生成中')
        for _ in range(240):
            status = result.get('status')
            if status == 'SUCCESS':
                candidates = [o for o in (result.get('results') or []) if o.get('outputType', '').lower() in ('png', 'jpg', 'jpeg', 'webp', 'image') and o.get('url')]
                if not candidates:
                    raise ValueError('RunningHub 工作流未输出图片')
                update(stage='正在下载并校验结果')
                return read_image(candidates[0]['url'])
            if status == 'FAILED' or result.get('errorCode'):
                raise ValueError('RunningHub 任务失败：' + error_message(result.get('errorMessage') or '请查看平台任务记录', key))
            if status not in ('QUEUED', 'RUNNING'):
                raise ValueError('RunningHub 返回未知状态；请查看已保存的任务 ID，勿重复提交')
            time.sleep(5)
            result = json_request(base + '/openapi/v2/query', {'taskId': task_id}, headers)
        raise ValueError('RunningHub 等待超过 20 分钟；任务 ID 已保留，请到平台查看，勿重复提交')
    payload = {'apiKey': key, 'webappId' if app_mode else 'workflowId': config['workflow_id'], 'nodeInfoList': nodes}
    payload['instanceType'] = config.get('instance_type', 'default')
    result = json_request(base + ('/task/openapi/ai-app/run' if app_mode else '/task/openapi/create'), payload, headers)
    task_id = (result.get('data') or {}).get('taskId')
    if result.get('code') != 0 or not task_id:
        raise ValueError('RunningHub 提交失败：' + error_message(result.get('msg', '未返回任务 ID'), key))
    update(remote_id=str(task_id), stage='RunningHub 排队 / 生成中')
    for _ in range(240):
        time.sleep(5)
        result = json_request(base + '/task/openapi/outputs', {'apiKey': key, 'taskId': task_id}, headers)
        if result.get('code') in (804, 813):
            continue
        if result.get('code') != 0:
            raise ValueError('RunningHub 任务失败：' + error_message(result.get('msg', '请在平台查看任务记录'), key))
        outputs = result.get('data') or []
        if not isinstance(outputs, list):
            raise ValueError('RunningHub 返回了无法识别的任务结果')
        candidates = [o for o in outputs if o.get('fileType', '').lower() in ('png', 'jpg', 'jpeg', 'webp', 'image')]
        if not candidates:
            candidates = [o for o in outputs if re.search(r'\.(png|jpe?g|webp)(\?|$)', o.get('fileUrl', ''), re.I)]
        if not candidates:
            raise ValueError('RunningHub 工作流未输出图片，请检查输出节点')
        update(stage='正在下载并校验结果')
        return read_image(candidates[0]['fileUrl'])
    raise ValueError('RunningHub 等待超过 20 分钟；任务 ID 已保留，请到平台查看，勿直接重复提交')
