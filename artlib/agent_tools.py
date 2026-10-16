"""One schema and dispatcher for the sidebar's dynamic tools and external MCP."""
import base64
import io
import json
import time

from PIL import Image, ImageOps

from . import agent_store as store, agent_tasks as tasks, agent_skills as skills, library


def schema(properties=None, required=None):
    return {'type': 'object', 'properties': properties or {}, 'required': required or [], 'additionalProperties': False}


S = {'type': 'string'}
TOOL_DEFS = [
 ('lingtu_state', '读取图库、窗口和当前选择。多窗口时必须传 view_id；不返回磁盘路径或密钥。', schema({'view_id': S})),
 ('lingtu_search', '分页搜索素材，q 匹配名称、标签及元数据。', schema({'q': S, 'scope': S, 'kind': {'type': 'string', 'enum': ['', 'image', 'video']}, 'offset': {'type': 'integer', 'minimum': 0}, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 100}})),
 ('lingtu_asset', '读取素材文字信息。图片内容需调用 lingtu_preview。', schema({'asset_id': S}, ['asset_id'])),
 ('lingtu_preview', '读取图片预览内容，用于逐图分析；不执行图像生成。', schema({'asset_id': S}, ['asset_id'])),
 ('lingtu_services', '列出可用生图服务及参考图限制，无密钥。', schema()),
 ('lingtu_skills', '列出已启用技能；按 skill_id 读取指令，resource 可读取其文本参考资源。', schema({'skill_id': S, 'resource': S})),
 ('lingtu_create_plan', '创建待用户批准的计划；不会直接执行。generation 每项 prompt/references；organize 每项 asset_id/changes；create_folder 每项 name/parent_id。先阅读素材和服务。', schema({
     'request_id': S, 'title': S, 'kind': {'type': 'string', 'enum': ['generation', 'organize', 'create_folder']},
     'profile_id': S, 'folder_id': {'type': ['integer', 'null']}, 'sample_first': {'type': 'boolean'},
     'items': {'type': 'array', 'minItems': 1, 'maxItems': 100, 'items': schema({
         'prompt': S, 'references': {'type': 'array', 'items': schema({'id': S}, ['id'])},
         'asset_id': S, 'changes': schema({'name': S, 'folder_id': {'type': ['integer', 'null']}, 'tags': {'type': 'array', 'items': S}, 'favorite': {'type': 'boolean'}, 'deleted_at': {'type': ['boolean', 'null']}}),
         'name': S, 'parent_id': {'type': ['integer', 'null']}})}}, ['kind', 'title', 'items'])),
 ('lingtu_plans', '读取计划、任务状态和待审核结果。', schema({'plan_id': S})),
 ('lingtu_cancel', '立即停止后续任务；已提交平台的任务可能仍会完成并计费。', schema({'plan_id': S}, ['plan_id'])),
]


def definitions():
    return [{'type': 'function', 'name': n, 'description': d, 'inputSchema': s} for n, d, s in TOOL_DEFS]


def clean_asset(a):
    return {k: a.get(k) for k in ('id', 'name', 'kind', 'ext', 'width', 'height', 'size', 'folder_id', 'favorite', 'tags', 'note', 'manual_prompt', 'deleted_at') if k in a}


def _validate(args, spec):
    # Schemas also serve external MCP; enforce them server-side, not only in the model.
    if spec.get('type') == 'object':
        if not isinstance(args, dict) or set(args) - set(spec['properties']) or any(k not in args for k in spec['required']):
            raise ValueError('工具参数字段无效或缺少必填项')
        for k, v in args.items():
            _validate(v, spec['properties'][k])
    elif spec.get('type') == 'array':
        if not isinstance(args, list) or not spec.get('minItems', 0) <= len(args) <= spec.get('maxItems', 1000):
            raise ValueError('工具数组参数无效')
        for v in args:
            _validate(v, spec['items'])
    else:
        types = spec.get('type', [])
        types = [types] if isinstance(types, str) else types
        valid = any((t == 'string' and isinstance(args, str) and len(args) <= 8000) or
                    (t == 'integer' and type(args) is int) or (t == 'boolean' and type(args) is bool) or
                    (t == 'null' and args is None) for t in types)
        if not valid or ('enum' in spec and args not in spec['enum']):
            raise ValueError('工具参数类型无效')
        if type(args) is int and not spec.get('minimum', -10**12) <= args <= spec.get('maximum', 10**12):
            raise ValueError('工具数值超出范围')


def call(name, args, session_id='external', view_id=None):
    spec = next((s for n, d, s in TOOL_DEFS if n == name), None)
    if spec is None:
        raise ValueError('未知工具')
    _validate(args, spec)
    with store.LOCK:
        if name == 'lingtu_state':
            views = [v for v in store.all_records('view') if time.time() - v['updated'] < 90]
            target = args.get('view_id') or view_id
            if target:
                views = [v for v in views if v['id'] == target]
                if not views:
                    raise ValueError('目标窗口已关闭或选择已过期')
            elif len(views) > 1:
                return {'library_id': store.library_id(), 'choose_view': [{'view_id': v['id'], 'scope': v['scope']} for v in views]}
            return {'library_id': store.library_id(), 'sidebar': library.sidebar(), 'views': views}
        if name == 'lingtu_search':
            result = library.query_assets(**args)
            return {**result, 'items': [clean_asset(a) for a in result['items']]}
        if name in ('lingtu_asset', 'lingtu_preview'):
            a = tasks._asset(args['asset_id'], allow_deleted=True)
            if name == 'lingtu_asset':
                return clean_asset(a)
            if a['kind'] != 'image':
                raise ValueError('只能预览图片')
            with Image.open(a['path']) as im:
                im = ImageOps.exif_transpose(im).convert('RGB')
                im.thumbnail((1280, 1280))
                out = io.BytesIO()
                im.save(out, 'JPEG', quality=85)
            return {'asset_id': a['id'], 'image_url': 'data:image/jpeg;base64,' + base64.b64encode(out.getvalue()).decode()}
        if name == 'lingtu_services':
            return {'services': tasks.profiles()}
        if name == 'lingtu_skills':
            all_skills = [s for s in skills.listing() if s['enabled'] and s['compatible']]
            if args.get('skill_id'):
                found = next((s for s in all_skills if s['id'] == args['skill_id']), None)
                if not found:
                    return {'error': '技能未启用'}
                if args.get('resource'):
                    base = (skills.directory() / found['id']).resolve()
                    path = (base / args['resource']).resolve()
                    if not path.is_relative_to(base) or not path.is_file() or path.stat().st_size > 128 * 1024 or path.suffix.lower() not in ('.md', '.txt', '.json', '.yaml', '.yml', '.csv'):
                        raise ValueError('资源不存在、格式不支持、路径越界或超过 128 KB')
                    return {'resource': args['resource'], 'text': path.read_text('utf-8')}
                return {'id': found['id'], 'text': found['text'], 'resources': found.get('resources', [])}
            return {'skills': [{'id': s['id'], 'description': s['description']} for s in all_skills]}
        if name == 'lingtu_create_plan':
            return tasks.create(args, session_id)
        if name == 'lingtu_plans':
            return tasks.public(store.get('plan', args['plan_id'])) if args.get('plan_id') else [tasks.public(p) for p in store.all_records('plan')]
        if name == 'lingtu_cancel':
            return tasks.cancel(args['plan_id'])


def content(result):
    if isinstance(result, dict) and result.get('image_url'):
        return [{'type': 'inputImage', 'imageUrl': result['image_url']}]
    return [{'type': 'inputText', 'text': json.dumps(result, ensure_ascii=False)}]
