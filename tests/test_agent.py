"""Agent reliability/permission tests, isolated data and mocked generation only."""
import base64
import io
import json
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from artlib import library, ai_edit, agent_store as store, agent_tasks as tasks, agent_tools as tools, agent_skills as skills
from artlib import agent_service as service, ai_providers
from artlib.config import Paths
from artlib.mcp_server import handle


def png(color):
    out = io.BytesIO(); Image.new('RGB', (160, 240), color).save(out, 'PNG'); return out.getvalue()


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.work = Path(tempfile.mkdtemp(prefix='lingtu-agent-test-'))
        library.start(Paths(self.work))
        self.assets = []
        for n, color in enumerate(('red', 'green', 'blue')):
            p = library.PATHS.tmp / f'{n}.png'; p.write_bytes(png(color))
            self.assets.append(library.import_file(p, library.sha256_file(p), f'Reference-{n}.png', None, None)['asset_id'])
        profile = ai_edit.save_profile({'kind': 'runninghub', 'name': 'Local mock', 'base_url': 'https://example.invalid',
            'workflow_id': '123', 'image_nodes': [{'nodeId': '1', 'fieldName': 'image'}], 'prompt_node': {'nodeId': '2', 'fieldName': 'text'},
            'api_key': 'mock-local-only'})['profiles'][0]
        self.profile = profile['id']
        self.session = service.new_session()
        self.no_worker = patch.object(tasks, 'start'); self.no_worker.start()
        self.count = 0

    def tearDown(self):
        self.no_worker.stop()
        for _ in range(100):
            if not ai_edit.ACTIVE: break
            time.sleep(.02)

    def plan(self, count=3):
        return tasks.create({'kind': 'generation', 'profile_id': self.profile, 'title': 'Batch test',
            'items': [{'prompt': f'Change background {n}', 'references': [{'id': self.assets[n % 3]}]} for n in range(count)]}, self.session['id'])

    def approve(self, p):
        p = store.get('plan', p['id'])
        return tasks.approve(p['id'], {'token': p['approval_token'], 'revision': p['revision']})

    def generate(self, *args):
        self.count += 1
        return png((self.count * 30, 80, 120))

    def until(self, ident, status):
        for _ in range(200):
            tasks.tick()
            p = store.get('plan', ident)
            if p['status'] == status: return p
            time.sleep(.015)
        self.fail(f"expected {status}, got {p['status']}: {p}")

    def test_sample_gate_idempotency_and_import(self):
        with patch.object(ai_providers, 'generate', side_effect=self.generate):
            p = self.plan(); first = store.get('plan', p['id'])
            self.approve(p); self.approve(p)
            p = self.until(p['id'], 'awaiting_sample')
            self.assertEqual(self.count, 1)
            self.assertTrue(p['items'][0]['asset_id'])
            # Late duplicated first approval must never approve the remaining batch.
            tasks.approve(p['id'], {'token': first['approval_token'], 'revision': 1})
            tasks.tick(); self.assertEqual(self.count, 1)
            self.approve(p)
            p = self.until(p['id'], 'completed')
            self.assertEqual(self.count, 3)
            self.assertEqual(len({i['asset_id'] for i in p['items']}), 3)
            self.assertTrue(all(i['review'] == 'pending' for i in p['items']))
            self.assertEqual(library.sidebar()['counts']['all'], 6)

    def test_import_retry_does_not_regenerate(self):
        with patch.object(ai_providers, 'generate', side_effect=self.generate):
            p = self.plan(1); self.approve(p)
            with patch.object(ai_edit, 'import_result', side_effect=OSError('disk full')):
                p = self.until(p['id'], 'paused')
            self.assertEqual(p['items'][0]['status'], 'import_failed')
            tasks.retry_local(p['id'], p['items'][0]['id'])
            p = self.until(p['id'], 'completed')
            self.assertEqual(self.count, 1)

    def test_cancel_stops_queued_items(self):
        gate = threading.Event()
        def generate(*args): gate.wait(3); return self.generate()
        with patch.object(ai_providers, 'generate', side_effect=generate):
            p = self.plan(); self.approve(p); tasks.tick()
            tasks.cancel(p['id']); gate.set()
            p = self.until(p['id'], 'cancelled')
            self.assertEqual(self.count, 1)
            self.assertEqual([i['status'] for i in p['items']].count('cancelled'), 2)

    def test_shared_manual_capacity(self):
        p = self.plan(); self.approve(p)
        with patch.object(ai_edit, 'ACTIVE', {'manual1', 'manual2'}), patch.object(ai_edit, 'submit_job') as submit:
            tasks.tick(); submit.assert_not_called()
        self.assertEqual(store.get('plan', p['id'])['items'][0]['status'], 'pending')

    def test_restart_unknown_never_resubmits(self):
        p = self.plan(); p = store.get('plan', p['id'])
        p.update(status='running'); p['items'][0]['status'] = 'running'; store.put('plan', p)
        with patch.object(ai_edit, 'submit_job') as submit:
            tasks.recover(); tasks.tick(); submit.assert_not_called()
        self.assertEqual(store.get('plan', p['id'])['items'][0]['status'], 'unknown')

    def test_plan_change_invalidates_approval(self):
        p = self.plan()
        settings = ai_edit.settings(); settings['profiles'][0]['size'] = 'changed'
        ai_edit.write_json(ai_edit.root() / 'settings.json', settings)
        with self.assertRaisesRegex(ValueError, '配置已改变'): self.approve(p)
        with self.assertRaises(ValueError): tasks.approve(p['id'], {'token': 'fake', 'revision': 1})

    def test_organize_preview_apply_undo_and_conflict(self):
        aid = self.assets[0]
        p = tasks.create({'kind': 'organize', 'title': 'Rename', 'items': [{'asset_id': aid, 'changes': {'name': 'new', 'tags': ['scene'], 'favorite': True}}]}, self.session['id'])
        self.assertNotEqual(library.get_asset(aid)['name'], 'new')
        self.approve(p); self.assertEqual(library.get_asset(aid)['name'], 'new')
        # An unrelated note must survive undo.
        library.update_asset(aid, {'note': 'later note'})
        tasks.undo(p['id']); self.assertEqual(library.get_asset(aid)['note'], 'later note')
        p = tasks.create({'kind': 'organize', 'items': [{'asset_id': aid, 'changes': {'name': 'new'}}]}, self.session['id'])
        self.approve(p); library.update_asset(aid, {'name': 'newer'})
        with self.assertRaisesRegex(ValueError, '后来'): tasks.undo(p['id'])

    def test_tools_no_secrets_no_approval_no_paths(self):
        raw = json.dumps(tools.call('lingtu_services', {})) + json.dumps(tools.call('lingtu_asset', {'asset_id': self.assets[0]}))
        self.assertNotIn('secret', raw); self.assertNotIn(str(self.work), raw)
        p = tools.call('lingtu_create_plan', {'kind': 'organize', 'title': 'test', 'items': [{'asset_id': self.assets[0], 'changes': {'favorite': True}}]})
        self.assertNotIn('approval_token', p)
        with self.assertRaises(ValueError): tools.call('lingtu_approve', {'plan_id': p['id']})
        with self.assertRaises(ValueError): tools.call('lingtu_search', {'limit': 50000})
        with self.assertRaises(ValueError): tools.call('lingtu_search', {'path': 'x'})

    def test_selection_multi_window_explicit(self):
        a, b = store.new_id(), store.new_id()
        service.context({'view_id': a, 'selected_ids': [self.assets[0]], 'scope': 'all'})
        service.context({'view_id': b, 'selected_ids': [self.assets[1]], 'scope': 'all'})
        self.assertIn('choose_view', tools.call('lingtu_state', {}))
        self.assertEqual(tools.call('lingtu_state', {'view_id': a})['views'][0]['selected_ids'], [self.assets[0]])
        self.assertEqual(tools.content(tools.call('lingtu_preview', {'asset_id': self.assets[0]}))[0]['type'], 'inputImage')

    def test_skills_import_edit_revision_path_and_scripts(self):
        text = '---\nname: custom-edit\ndescription: custom editing instructions\n---\nKeep original images.'
        s = skills.import_skill(text.encode(), 'SKILL.md')
        self.assertFalse(s['enabled'])
        s = skills.save(s['id'], {'enabled': True, 'revision': 1})
        self.assertTrue((skills.directory() / s['id'] / 'SKILL.md').is_file())
        with self.assertRaisesRegex(ValueError, '更新'): skills.save(s['id'], {'enabled': False, 'revision': 1})
        with self.assertRaises(ValueError): skills.import_skill(b'invalid', 'SKILL.md')
        def archive(files):
            out = io.BytesIO()
            with zipfile.ZipFile(out, 'w') as z:
                for name, data in files.items(): z.writestr(name, data)
            return out.getvalue()
        with self.assertRaisesRegex(ValueError, '越界'): skills.import_skill(archive({'../SKILL.md': text}), 'bad.zip')
        bad = text.replace('custom-edit', 'script-edit')
        s = skills.import_skill(archive({'skill/SKILL.md': bad, 'skill/scripts/x.py': 'print(1)'}), 'script.zip')
        self.assertFalse(s['compatible'])
        with self.assertRaises(ValueError): skills.save(s['id'], {'enabled': True, 'revision': 1})

    def test_resume_queries_only_existing_task(self):
        calls = []
        def request(url, *args, **kwargs):
            calls.append(url); return {'status': 'SUCCESS', 'results': [{'outputType': 'png', 'url': 'https://example.invalid/a.png'}]}
        with patch.object(ai_providers, 'json_request', side_effect=request), patch.object(ai_providers, 'read_image', return_value=png('red')):
            ai_providers.runninghub_result({'base_url': 'https://example.invalid', 'rh_version': 'v2'}, 'mock', 'existing', lambda **kw: None)
        self.assertEqual(calls, ['https://example.invalid/openapi/v2/query'])

    def test_download_recovery_never_regenerates(self):
        def generate(profile, key, prompt, images, update):
            self.count += 1
            update(download_value='https://example.invalid/saved.png')
            raise OSError('download interrupted')
        with patch.object(ai_providers, 'generate', side_effect=generate):
            p = self.plan(1); self.approve(p); p = self.until(p['id'], 'paused')
        with patch.object(ai_providers, 'read_image', return_value=png('purple')), patch.object(ai_providers, 'generate') as regenerate:
            tasks.retry_local(p['id'], p['items'][0]['id']); self.until(p['id'], 'completed')
            regenerate.assert_not_called()
        self.assertEqual(self.count, 1)

    def test_folder_plan_undo_and_occupied_protection(self):
        p = tasks.create({'kind': 'create_folder', 'items': [{'name': 'New folder'}]}, self.session['id'])
        self.approve(p); p = store.get('plan', p['id']); folder = p['items'][0]['folder_id']
        library.update_asset(self.assets[0], {'folder_id': folder})
        with self.assertRaises(ValueError): tasks.undo(p['id'])
        library.update_asset(self.assets[0], {'folder_id': None}); tasks.undo(p['id'])
        self.assertFalse(any(f['id'] == folder for f in library.sidebar()['folders']))

    def test_backup_contains_consistent_agent_state_and_skills(self):
        from artlib import backup
        p = self.plan(); skills.listing()
        path = Path(backup.create_backup(self.work, self.work / 'backup')['path'])
        target = self.work / 'restored'; backup.restore_backup(path, target)
        import sqlite3
        with sqlite3.connect(target / 'agent' / 'agent.db') as conn:
            self.assertTrue(conn.execute("SELECT 1 FROM records WHERE kind='plan' AND id=?", (p['id'],)).fetchone())
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertTrue((target / 'agent/workspace/.agents/skills/batch-edit/SKILL.md').exists())

    def test_mcp_transport_and_no_notification_reply(self):
        self.assertIsNone(handle({'jsonrpc': '2.0', 'method': 'notifications/initialized'}))
        r = handle({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-11-25'}})
        self.assertIn('tools', r['result']['capabilities'])
        with patch('artlib.mcp_server.forward', return_value={'content': [{'type': 'text', 'text': 'ok'}]}) as forward:
            handle({'id': 2, 'method': 'tools/call', 'params': {'name': 'lingtu_state', 'arguments': {}}})
            forward.assert_called_once()


if __name__ == '__main__':
    unittest.main()
