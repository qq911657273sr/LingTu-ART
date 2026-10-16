import io
import json
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from artlib import updates


def release(tag='v9.2.1', asset=True):
    version = tag.removeprefix('v'); name = f'LingTu-ART-Setup-{version}.exe'
    return {'tag_name': tag, 'body': '中文更新说明', 'draft': False, 'prerelease': False,
            'assets': [{'name': name, 'state': 'uploaded', 'size': 123,
                        'browser_download_url': f'https://github.com/{updates.REPOSITORY}/releases/download/{tag}/{name}'}] if asset else []}


class UpdateTests(unittest.TestCase):
    def setUp(self):
        updates._cached = None; updates._cached_at = 0

    def test_numeric_version_comparison(self):
        with patch.object(updates, 'VERSION', '1.4.9'):
            self.assertTrue(updates.release_info(release('v1.4.10'))['update_available'])
            self.assertFalse(updates.release_info(release('v1.4.9'))['update_available'])
            self.assertFalse(updates.release_info(release('v1.3.11'))['update_available'])

    def test_release_and_asset_url_validation(self):
        d = updates.release_info(release())
        self.assertEqual(d['state'], 'available'); self.assertEqual(d['notes'], '中文更新说明')
        bad = release(); bad['assets'][0]['browser_download_url'] = 'https://unrelated.example/a.exe'
        with self.assertRaises(ValueError): updates.release_info(bad)
        bad = release(); bad['prerelease'] = True
        with self.assertRaises(ValueError): updates.release_info(bad)
        with self.assertRaises(ValueError): updates.release_info(release('v9.2.1-beta'))

    def test_missing_installer_is_preparing(self):
        self.assertEqual(updates.release_info(release(asset=False))['state'], 'preparing')

    def test_network_errors_do_not_claim_latest(self):
        for error in (URLError('offline'), TimeoutError(), HTTPError(updates.LATEST_API, 403, '', {}, None)):
            with patch.object(updates, 'urlopen', side_effect=error):
                with self.assertRaises(ValueError): updates.check()
        self.assertIsNone(updates._cached)

    def test_no_release_and_malformed_reply(self):
        with patch.object(updates, 'urlopen', side_effect=HTTPError(updates.LATEST_API, 404, '', {}, None)):
            self.assertEqual(updates.check()['state'], 'unpublished')
        updates._cached = None
        for raw in (b'invalid', b'[]', b'x' * (1024 * 1024 + 1)):
            with patch.object(updates, 'urlopen', return_value=io.BytesIO(raw)):
                with self.assertRaises(ValueError): updates.check()

    def test_cache_and_request_never_include_provider_keys(self):
        with patch.object(updates, 'urlopen', return_value=io.BytesIO(json.dumps(release()).encode())) as network:
            self.assertEqual(updates.check(), updates.check()); self.assertEqual(network.call_count, 1)
            req = network.call_args.args[0]
            self.assertNotIn('Authorization', req.headers); self.assertEqual(req.full_url, updates.LATEST_API)


if __name__ == '__main__': unittest.main()
