"""Public GitHub Releases discovery. Never sends user/provider credentials."""
from __future__ import annotations

import configparser
import json
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, unquote
from urllib.request import Request, urlopen

from fastapi import APIRouter
from .config import RESOURCE_DIR

_ini = configparser.ConfigParser()
_ini.read(RESOURCE_DIR / 'version.ini', encoding='utf-8-sig')
VERSION = _ini.get('app', 'version')
REPOSITORY = 'qq911657273sr/LingTu-ART'
RELEASES_URL = f'https://github.com/{REPOSITORY}/releases'
LATEST_API = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
router = APIRouter(prefix='/api/update')
_lock = threading.Lock()
_cached = None
_cached_at = 0.0


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'v?\d+\.\d+\.\d+', value):
        raise ValueError('GitHub 发布版本号无效，请到发布页面查看')
    return tuple(int(v) for v in value.removeprefix('v').split('.'))


@router.get('')
def info():
    return {'current_version': VERSION, 'repository': REPOSITORY, 'releases_url': RELEASES_URL}


def release_info(data):
    latest = str(data.get('tag_name', ''))
    version_tuple(latest)
    if data.get('draft') or data.get('prerelease'):
        raise ValueError('尚无可用的正式更新，请到 GitHub 发布页面查看')
    version = latest.removeprefix('v')
    newer = version_tuple(latest) > version_tuple(VERSION)
    name = f'LingTu-ART-Setup-{version}.exe'
    asset = next((a for a in data.get('assets', []) if a.get('name') == name and a.get('state') == 'uploaded'), None)
    url = asset.get('browser_download_url', '') if asset else ''
    if url:
        parsed = urlsplit(url)
        expected = f'/{REPOSITORY}/releases/download/{latest}/{name}'
        if parsed.scheme != 'https' or parsed.netloc != 'github.com' or unquote(parsed.path) != expected or parsed.query or parsed.fragment:
            raise ValueError('安装包地址与官方仓库不一致，请到 GitHub 发布页面查看')
    digest = (asset or {}).get('digest', '') or ''
    sha256 = digest.removeprefix('sha256:') if re.fullmatch(r'sha256:[a-fA-F0-9]{64}', digest) else ''
    state = 'available' if newer and url else 'preparing' if newer else 'ahead' if version_tuple(latest) < version_tuple(VERSION) else 'current'
    return {**info(), 'state': state,
            'latest_version': version, 'update_available': newer, 'download_url': url,
            'release_url': RELEASES_URL + '/tag/' + latest,
            'notes': str(data.get('body') or '此版本未提供更新说明。')[:20000],
            'published_at': data.get('published_at'), 'size': (asset or {}).get('size'),
            'sha256': sha256, 'checked_at': time.time()}


@router.post('/check')
def check():
    global _cached, _cached_at
    with _lock:
        if _cached and time.monotonic() - _cached_at < 60:
            return _cached
        request = Request(LATEST_API, headers={'Accept': 'application/vnd.github+json',
            'User-Agent': 'LingTu-ART/' + VERSION, 'X-GitHub-Api-Version': '2022-11-28'})
        try:
            with urlopen(request, timeout=12) as response:
                raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError('GitHub 更新信息过大，请到发布页面查看')
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError('GitHub 更新信息格式无效，请稍后重试')
            result = release_info(data)
        except HTTPError as exc:
            if exc.code == 404:
                result = {**info(), 'state': 'unpublished', 'update_available': False,
                          'message': 'GitHub 尚未发布正式版本，请稍后再检查。', 'checked_at': time.time()}
            elif exc.code in (403, 429):
                raise ValueError('GitHub 请求暂时受限，请稍后重试，或直接打开发布页面') from None
            else:
                raise ValueError(f'GitHub 更新服务暂时不可用（{exc.code}），请稍后重试') from None
        except (URLError, OSError, TimeoutError):
            raise ValueError('无法连接 GitHub，请检查网络后重试，或直接打开发布页面') from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError('GitHub 更新信息格式无效，请稍后重试') from None
        _cached, _cached_at = result, time.monotonic()
        return result
