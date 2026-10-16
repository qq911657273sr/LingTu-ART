"""Durable approved plans and a single library-bound scheduler sharing AI slots."""
from __future__ import annotations

import copy
import hashlib
import json
import threading
import time
import os

from fastapi import HTTPException

from . import agent_store as store, ai_edit, library, db

_worker = None
_stop = threading.Event()
_owner = None
_lease = None
_profile_keys = ('id', 'kind', 'model', 'base_url', 'workflow_id', 'max_refs', 'image_nodes',
                 'prompt_node', 'extra_nodes', 'rh_mode', 'rh_version', 'size', 'repeat_main', 'instance_type', 'secret')
BUSY = ('queued', 'running', 'stopping', 'awaiting_sample', 'unknown', 'paused')


def fingerprint(profile):
    return hashlib.sha256(json.dumps({k: profile.get(k) for k in _profile_keys}, sort_keys=True).encode()).hexdigest()


def profiles():
    return [{'id': p['id'], 'name': p['name'], 'kind': p['kind'], 'model': p.get('model') or p.get('workflow_id'),
             'max_refs': p['max_refs'], 'ready': bool(p.get('secret')), 'revision': fingerprint(p)}
            for p in ai_edit.settings()['profiles']]


def _profile(ident):
    p = next((p for p in ai_edit.settings()['profiles'] if p['id'] == ident), None)
    if not p or not p.get('secret'):
        raise ValueError('所选生图服务未配置密钥或已被删除')
    return p


def _asset(ident, allow_deleted=False):
    a = library.get_asset(ai_edit.uid(ident))
    if not a or (a['deleted_at'] and not allow_deleted):
        raise ValueError('素材不存在或已移入回收站')
    return a


def public(plan):
    return {k: v for k, v in plan.items() if k not in ('approval_token', 'consumed_tokens')}


def create(data, session_id):
    """Creation does not execute. The UI owns approval, never the model/MCP."""
    with store.LOCK:
        if data.get('request_id'):
            for p in store.all_records('plan'):
                if p.get('request_id') == data['request_id'] and p['session_id'] == session_id:
                    return public(p)
        kind = data.get('kind', 'generation')
        items = data.get('items')
        if not isinstance(items, list) or not 1 <= len(items) <= 100:
            raise ValueError('计划需要 1～100 个逐项操作')
        p = {'id': store.new_id(), 'library_id': store.library_id(), 'session_id': session_id, 'kind': kind,
             'title': str(data.get('title') or '新任务')[:100], 'revision': 1, 'created': time.time(),
             'request_id': str(data.get('request_id', ''))[:100], 'status': 'awaiting_approval', 'items': [],
             'sample_first': bool(data.get('sample_first', True)), 'sample_approved': False,
             'cost': '费用未知，按生图平台实际计费；Codex 对话消耗另计',
             'approval_token': store.new_id(), 'consumed_tokens': [], 'approval_expires': time.time() + 86400, 'error': ''}
        if kind == 'generation':
            profile = _profile(data.get('profile_id'))
            p.update(profile_id=profile['id'], profile_name=profile['name'], profile_revision=fingerprint(profile),
                     folder_id=data.get('folder_id'))
            library._check_folder(db.connect(), p['folder_id'])
            for i in items:
                prompt = str(i.get('prompt', '')).strip()
                if not 1 <= len(prompt) <= 8000:
                    raise ValueError('每项需要 1～8000 字的指令')
                refs = i.get('references', [])
                if not isinstance(refs, list) or not (0 if profile['max_refs'] == 0 else 1) <= len(refs) <= profile['max_refs']:
                    raise ValueError('参考图数量不符合所选服务能力')
                if profile['kind'] == 'runninghub' and not profile.get('repeat_main') and len(refs) != len(profile['image_nodes']):
                    raise ValueError('该工作流要求填写全部参考图节点')
                clean = []
                for ref in refs:
                    # Agent accepts library assets only; local files must first be imported explicitly.
                    a = _asset(ref.get('id'))
                    if a['kind'] != 'image':
                        raise ValueError('参考素材必须为图片')
                    clean.append({'type': 'asset', 'id': a['id'], 'name': a['name']})
                p['items'].append({'id': store.new_id(), 'job_id': store.new_id(), 'prompt': prompt,
                    'references': clean, 'status': 'pending', 'review': 'pending', 'error': '', 'asset_id': None})
        elif kind == 'organize':
            allowed = {'name', 'folder_id', 'tags', 'favorite', 'deleted_at'}
            for i in items:
                a = _asset(i.get('asset_id'), allow_deleted=True)
                changes = copy.deepcopy(i.get('changes', {}))
                if not changes or set(changes) - allowed:
                    raise ValueError('整理仅支持名称、分类、标签、收藏和回收站')
                if 'name' in changes and (not isinstance(changes['name'], str) or not changes['name'].strip() or len(changes['name']) > 200):
                    raise ValueError('名称需要 1～200 个字符')
                if 'tags' in changes:
                    if not isinstance(changes['tags'], list) or len(changes['tags']) > 100 or not all(isinstance(t, str) for t in changes['tags']):
                        raise ValueError('标签必须是最多 100 项的文字数组')
                    changes['tags'] = sorted(library.clean_tags(changes['tags']))
                if 'favorite' in changes:
                    if not isinstance(changes['favorite'], bool):
                        raise ValueError('收藏值必须是布尔值')
                    changes['favorite'] = int(changes['favorite'])
                if 'deleted_at' in changes:
                    if changes['deleted_at'] not in (True, None):
                        raise ValueError('移入回收站用 true，恢复用 null')
                    changes['deleted_at'] = time.time() if changes['deleted_at'] else None
                if 'folder_id' in changes:
                    library._check_folder(db.connect(), changes['folder_id'])
                if any(j['asset_id'] == a['id'] for j in p['items']):
                    raise ValueError('同一素材请合并为一项修改')
                p['items'].append({'id': store.new_id(), 'asset_id': a['id'], 'name': a['name'], 'changes': changes,
                    'before': {k: a[k] for k in changes}, 'status': 'pending'})
        elif kind == 'create_folder':
            for i in items:
                name = str(i.get('name', '')).strip()
                if not name or len(name) > 80:
                    raise ValueError('分类名称需要 1～80 字')
                library._check_folder(db.connect(), i.get('parent_id'))
                p['items'].append({'id': store.new_id(), 'name': name, 'parent_id': i.get('parent_id'), 'status': 'pending'})
        else:
            raise ValueError('未知计划类型')
        store.put('plan', p)
        store.emit(session_id, 'plan', plan_id=p['id'])
        return public(p)


def _changed(a, fields):
    return any((sorted(a[k]) if k == 'tags' else a[k]) != (sorted(v) if k == 'tags' else v) for k, v in fields.items())


def _apply_many(items, inverse=False):
    conn = db.connect()
    conn.execute('BEGIN IMMEDIATE')
    try:
        for i in items:
            expected, fields = (i['changes'], i['before']) if inverse else (i['before'], i['changes'])
            if _changed(_asset(i['asset_id'], True), expected):
                raise ValueError('相关字段后来已修改，请重新创建计划；未执行任何修改')
            for k, v in fields.items():
                if k == 'tags':
                    conn.execute('DELETE FROM asset_tags WHERE asset_id=?', (i['asset_id'],))
                    for tag in v:
                        conn.execute('INSERT OR IGNORE INTO asset_tags VALUES (?,?)', (i['asset_id'], library._tag_id(conn, tag)))
                else:
                    if k == 'folder_id':
                        library._check_folder(conn, v)
                    conn.execute(f'UPDATE assets SET {k}=? WHERE id=?', (v, i['asset_id']))
            library.refresh_search(conn, [i['asset_id']])
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


def approve(ident, data):
    with store.LOCK, ai_edit.LOCK:
        p = store.get('plan', ident)
        if data.get('token') in p.get('consumed_tokens', []):
            return public(p)
        if (p['library_id'] != store.library_id() or data.get('token') != p['approval_token'] or
                data.get('revision') != p['revision'] or p['approval_expires'] < time.time()):
            raise ValueError('确认已失效，请重新创建计划')
        # Repeated confirmation is a no-op: IDs were persisted at plan creation.
        if p['status'] not in ('awaiting_approval', 'awaiting_sample'):
            return public(p)
        if p['kind'] != 'generation':
            if p['kind'] == 'organize':
                _apply_many(p['items'])
                for item in p['items']:
                    item['status'] = 'completed'
            else:
                conn = db.connect()
                with conn:
                    for item in p['items']:
                        library._check_folder(conn, item['parent_id'])
                        order = conn.execute('SELECT COALESCE(MAX(sort_order)+1,0) FROM folders WHERE parent_id IS ?', (item['parent_id'],)).fetchone()[0]
                        item['folder_id'] = conn.execute('INSERT INTO folders(parent_id,name,sort_order,created_at) VALUES (?,?,?,?)',
                            (item['parent_id'], item['name'], order, time.time())).lastrowid
                        item['status'] = 'completed'
            p['status'] = 'completed'
        else:
            if fingerprint(_profile(p['profile_id'])) != p['profile_revision']:
                raise ValueError('生图配置已改变，请重新创建计划')
            if p['status'] == 'awaiting_sample':
                p['sample_approved'] = True
            p['status'] = 'queued'
        p.setdefault('consumed_tokens', []).append(p['approval_token'])
        store.put('plan', p)
        store.emit(p['session_id'], 'plan', plan_id=p['id'])
        start()
        return public(p)


def undo(ident):
    with store.LOCK, ai_edit.LOCK:
        p = store.get('plan', ident)
        if p['kind'] not in ('organize', 'create_folder') or p['status'] != 'completed':
            raise ValueError('只有已完成的图库整理计划支持撤销')
        if p['kind'] == 'create_folder':
            conn = db.connect()
            for i in p['items']:
                folder = conn.execute('SELECT name,parent_id FROM folders WHERE id=?', (i['folder_id'],)).fetchone()
                used = conn.execute('SELECT 1 FROM assets WHERE folder_id=? UNION SELECT 1 FROM folders WHERE parent_id=?', (i['folder_id'], i['folder_id'])).fetchone()
                if not folder or folder['name'] != i['name'] or folder['parent_id'] != i['parent_id'] or used:
                    raise ValueError('分类已有素材、子分类或后来变更，不能自动撤销')
            with conn:
                for i in p['items']:
                    conn.execute('DELETE FROM folders WHERE id=?', (i['folder_id'],))
            p['status'] = 'undone'
            return public(store.put('plan', p))
        for i in p['items']:
            if _changed(_asset(i['asset_id'], True), i['changes']):
                raise ValueError('相关字段后来又被修改，无法覆盖撤销')
        _apply_many(p['items'], inverse=True)
        p['status'] = 'undone'
        return public(store.put('plan', p))


def cancel(ident):
    with store.LOCK:
        p = store.get('plan', ident)
        for i in p['items']:
            if i['status'] == 'pending':
                i['status'] = 'cancelled'
        p['status'] = 'stopping' if any(i['status'] == 'running' for i in p['items']) else 'cancelled'
        p['error'] = '已停止后续提交；已提交平台的任务仍可能计费，将继续记录结果。' if p['status'] == 'stopping' else ''
        return public(store.put('plan', p))


def retry_local(ident, item_id):
    with store.LOCK:
        p = store.get('plan', ident)
        i = next((i for i in p['items'] if i['id'] == item_id), None)
        if not i or i['status'] not in ('unknown', 'import_failed', 'failed'):
            raise ValueError('此项不需要恢复')
        job = ai_edit.read_job(ai_edit.root(), i['job_id'])
        if job['status'] == 'completed':
            i.update(status='running', error='')
        elif (ai_edit.root() / 'jobs' / i['job_id'] / 'provider-result.json').exists() or (job.get('remote_id') and job['kind'] == 'runninghub'):
            if fingerprint(_profile(p['profile_id'])) != p['profile_revision']:
                raise ValueError('服务配置已改变，请恢复原配置后查询原任务')
            ai_edit.resume_job(i['job_id'])  # query existing task only
            i.update(status='running', error='')
        else:
            raise ValueError('平台结果无法确认，未自动重提。请核对平台记录后创建新计划。')
        p['status'] = 'running'
        store.put('plan', p)
        start()
        return public(p)


def tick(owner=None):
    with store.LOCK, ai_edit.LOCK:
        if owner is not None and store.library_id() != owner:
            return
        for p in store.all_records('plan'):
            if p['kind'] != 'generation' or p['status'] not in ('queued', 'running', 'stopping'):
                continue
            for i in p['items']:
                if i['status'] != 'running':
                    continue
                job = ai_edit.read_job(ai_edit.root(), i['job_id'])
                if job['status'] == 'completed':
                    try:
                        result = ai_edit.import_result(i['job_id'], p['folder_id'])
                        i.update(status='completed', asset_id=result['asset_id'], error='')
                    except Exception:
                        i.update(status='import_failed', error='结果已生成，入库失败；可恢复入库，不会重新生图')
                elif job['status'] in ('failed', 'interrupted'):
                    i.update(status='unknown' if job.get('remote_id') or job['status'] == 'interrupted' else 'failed',
                             error=job.get('error') or '上次运行中断，需查询平台原任务')
                i['remote_id'] = job.get('remote_id')
            statuses = [i['status'] for i in p['items']]
            if any(s in ('unknown', 'import_failed', 'failed') for s in statuses):
                p['status'] = 'paused' if 'running' not in statuses else 'running'
            elif p['status'] == 'stopping':
                if 'running' not in statuses:
                    p['status'] = 'cancelled'
            elif all(s == 'completed' for s in statuses):
                p['status'] = 'completed'
            elif p['sample_first'] and not p['sample_approved'] and statuses[0] == 'completed':
                p['status'] = 'awaiting_sample'
                p['approval_token'] = store.new_id()
                p['approval_expires'] = time.time() + 86400
                store.emit(p['session_id'], 'sample_ready', plan_id=p['id'])
            if p['status'] in ('queued', 'running') and not any(s in ('unknown', 'import_failed', 'failed') for s in statuses):
                candidates = p['items'][:1] if p['sample_first'] and not p['sample_approved'] else p['items']
                for i in candidates:
                    if i['status'] != 'pending' or len(ai_edit.ACTIVE) >= 2:
                        continue
                    try:
                        if fingerprint(_profile(p['profile_id'])) != p['profile_revision']:
                            raise ValueError('生图服务配置已改变，已暂停；请创建新计划')
                        # Persist intent before any remote side effect.
                        i['status'] = 'running'
                        store.put('plan', p)
                        ai_edit.submit_job({'request_id': i['job_id'], 'profile_id': p['profile_id'],
                                            'prompt': i['prompt'], 'references': i['references']})
                        p['status'] = 'running'
                    except Exception as exc:
                        i.update(status='failed', error=str(exc)[:300])
                        p['status'] = 'paused'
                        break
            store.put('plan', p)


def _run(owner):
    global _lease
    lease = _lease
    try:
        recover(start_worker=False)
        while not _stop.wait(.8):
            if store.library_id() != owner:
                return
            try:
                tick(owner)
            except Exception:
                # A temporarily locked record must not kill the only scheduler.
                continue
    finally:
        if lease:
            lease.close()
        if _lease is lease:
            _lease = None


def start():
    global _worker, _owner, _lease
    with store.LOCK:
        owner = store.library_id()
        if _worker and _worker.is_alive() and _owner == owner:
            return True
        lease = open(store.root() / 'executor.lock', 'a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                lease.seek(0); lease.write(b'0'); lease.flush(); lease.seek(0)
                msvcrt.locking(lease.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            lease.close()
            return False  # Another application process owns this library's executor.
        _lease = lease
        _stop.clear()
        _owner = owner
        _worker = threading.Thread(target=_run, args=(owner,), daemon=True, name='LingTu-Agent-queue')
        _worker.start()
        return True


def can_switch():
    return not any(p['status'] in BUSY for p in store.all_records('plan'))


def recover(start_worker=True):
    with store.LOCK:
        for p in store.all_records('plan'):
            changed = False
            for i in p['items']:
                if p['kind'] == 'generation' and i['status'] == 'running':
                    try:
                        job = ai_edit.read_job(ai_edit.root(), i['job_id'])
                    except (ValueError, HTTPException):
                        job = {}
                    if job.get('status') != 'completed':
                        i.update(status='unknown', error='应用重启，请恢复查询原任务；不会自动重新生成')
                        p['status'] = 'paused'
                    changed = True
            if changed:
                store.put('plan', p)
    if start_worker:
        start()
