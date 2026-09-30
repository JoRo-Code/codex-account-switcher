import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import test_launcher as fixtures
app = fixtures.app

def executable(version):
    return ('#!/usr/bin/env python3\n"""Local ChatGPT account selection for Codex CLI"""\n'
            + f'VERSION = "{version}"\nprint(VERSION)\n').encode()

def release(version, preview=False):
    tag='v'+version
    return dict(tag_name=tag,prerelease=preview,draft=False,assets=[
        dict(name=name,state='uploaded',browser_download_url=
            f'https://github.com/{app.RELEASE_REPO}/releases/download/{tag}/{name}')
        for name in ('codex-accounts','codex-accounts.sha256')])

class UpdateTests(unittest.TestCase):
    setUp = fixtures.LauncherTests.setUp

    def setup_install(self):
        self.destination=app.ROOT/'bin/codex-accounts'
        self.destination.parent.mkdir()
        self.destination.write_bytes(executable('0.4.0'))
        patcher=patch.object(app,'executable_path',return_value=self.destination)
        patcher.start();self.addCleanup(patcher.stop)

    def test_catalog_ignores_drafts_and_preview_by_default(self):
        items=[release('0.5.0'),release('0.6.0',True),dict(release('9.0.0'),draft=True),release('0.4.0')]
        with patch.object(app,'fetch_public',return_value=json.dumps(items).encode()):
            self.assertEqual(app.newest_release()['tag_name'],'v0.5.0')
            self.assertEqual(app.newest_release(True)['tag_name'],'v0.6.0')

    def test_verified_download_requires_checksum_and_matching_version(self):
        payload=executable('0.5.0');r=release('0.5.0')
        checksum=hashlib.sha256(payload).hexdigest()+'  codex-accounts\n'
        with patch.object(app,'fetch_public',side_effect=[checksum.encode(),payload]):
            self.assertEqual(app.verified_release(r),payload)
        with patch.object(app,'fetch_public',side_effect=[('0'*64+'  codex-accounts').encode(),payload]):
            with self.assertRaises(app.Error):app.verified_release(r)
        with patch.object(app,'fetch_public',side_effect=[checksum.encode(),payload]):
            with self.assertRaises(app.Error):app.verified_release(release('0.6.0'))

    def test_asset_cannot_redirect_to_another_repository(self):
        r=release('0.5.0');r['assets'][0]['browser_download_url']='https://github.com/other/project/releases/download/v0.5.0/codex-accounts'
        with self.assertRaises(app.Error):app.release_asset(r,'codex-accounts')
        with self.assertRaises(app.Error):app.fetch_public('http://example.com/file')

    def test_update_and_rollback_preserve_accounts_and_history(self):
        self.setup_install()
        original=self.destination.read_bytes();history=self.path.read_bytes()
        auth=(app.account_home('personal')/'auth.json').read_bytes()
        with patch.object(app,'newest_release',return_value=release('0.5.0')), \
             patch.object(app,'verified_release',return_value=executable('0.5.0')),contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(app.self_update())
        self.assertEqual(app.installed_version(self.destination),'0.5.0')
        self.assertEqual((self.destination.parent/'.codex-accounts.previous').read_bytes(),original)
        with contextlib.redirect_stdout(io.StringIO()):app.self_update(rollback=True)
        self.assertEqual(self.destination.read_bytes(),original)
        self.assertEqual(app.update_settings()['policy'],'notify')
        self.assertEqual(self.path.read_bytes(),history)
        self.assertEqual((app.account_home('personal')/'auth.json').read_bytes(),auth)

    def test_check_never_downloads_or_replaces_executable(self):
        self.setup_install();original=self.destination.read_bytes()
        with patch.object(app,'newest_release',return_value=release('0.5.0')), \
             patch.object(app,'verified_release') as download,contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(app.self_update(check=True))
        download.assert_not_called()
        self.assertEqual(self.destination.read_bytes(),original)

    def test_never_downgrades_or_overwrites_backup_for_already_updated_process(self):
        self.setup_install();self.destination.write_bytes(executable('9.0.0'))
        with patch.object(app,'newest_release',return_value=release('0.5.0')), \
             patch.object(app,'verified_release') as download,contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(app.self_update())
        download.assert_not_called()
        self.assertEqual(app.installed_version(self.destination),'9.0.0')

    def test_failed_smoke_check_retains_existing_binary(self):
        self.setup_install();original=self.destination.read_bytes()
        with patch.object(app,'newest_release',return_value=release('0.5.0')), \
             patch.object(app,'verified_release',return_value=b'raise RuntimeError("broken")'):
            with self.assertRaises(app.Error):app.self_update()
        self.assertEqual(self.destination.read_bytes(),original)

    def test_atomic_activation_failure_retains_existing_binary(self):
        self.setup_install();original=self.destination.read_bytes();replace=app.os.replace
        def fail_activation(source,target):
            if Path(target)==self.destination:raise OSError('simulated activation failure')
            return replace(source,target)
        with patch.object(app,'newest_release',return_value=release('0.5.0')), \
             patch.object(app,'verified_release',return_value=executable('0.5.0')), \
             patch.object(app.os,'replace',side_effect=fail_activation):
            with self.assertRaises(OSError):app.self_update()
        self.assertEqual(self.destination.read_bytes(),original)

    def test_source_checkout_cannot_be_self_updated(self):
        self.setup_install();(self.destination.parent/'.git').mkdir()
        with self.assertRaises(app.Error):app.self_update()

    def test_automatic_checks_throttle_and_allow_work_offline(self):
        self.setup_install()
        app.atomic_json(app.install_marker(self.destination),{'repository':app.RELEASE_REPO})
        with patch.object(app,'self_update',side_effect=app.Error('offline')) as update:
            app.maybe_auto_update();app.maybe_auto_update()
        self.assertEqual(update.call_count,1)

    def test_notify_and_off_policies(self):
        self.setup_install()
        app.atomic_json(app.install_marker(self.destination),{'repository':app.RELEASE_REPO})
        app.record_update(policy='notify',last_check=0)
        with patch.object(app,'self_update',return_value=False) as update:app.maybe_auto_update()
        update.assert_called_once_with(check=True)
        app.record_update(policy='off',last_check=0)
        with patch.object(app,'self_update') as update:app.maybe_auto_update()
        update.assert_not_called()

if __name__=='__main__':unittest.main()
