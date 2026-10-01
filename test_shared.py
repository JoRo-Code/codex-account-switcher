import concurrent.futures
import contextlib
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import test_launcher as fixtures

app = fixtures.app


class SharedCapabilitiesTests(unittest.TestCase):
    setUp = fixtures.LauncherTests.setUp

    def source(self):
        source = app.ROOT / 'shared-codex'
        source.mkdir(exist_ok=True)
        return source.resolve()

    def sync(self, source=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return app.shared_capabilities('sync', source or self.source())

    def off(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return app.shared_capabilities('off')

    def test_capabilities_follow_accounts_without_copying_credentials_or_histories(self):
        source = self.source()
        config = 'model = "shared-model"\n[mcp_servers.fixture]\ncommand = "fixture"\n'
        (source / 'config.toml').write_text(config)
        (source / 'AGENTS.md').write_text('Common instructions')
        (source / 'hooks.json').write_text('{}')
        (source / 'installation_id').write_text('shared-device')
        (source / 'chrome-native-hosts-v2.json').write_text('{"entries": []}')
        (source / 'review.config.toml').write_text('model = "review-model"')
        for private in ('auth.json', '.credentials.json', 'models_cache.json', 'history.jsonl'):
            (source / private).write_text('DO NOT COPY')
        (source / 'sessions').mkdir()
        (source / 'sessions/private.jsonl').write_text('PRIVATE HISTORY')
        original = self.path.read_bytes()
        self.sync(source)
        for name in ('personal', 'work'):
            home = app.account_home(name)
            self.assertEqual((home / 'config.toml').read_text(), config)
            self.assertEqual((home / 'AGENTS.md').read_text(), 'Common instructions')
            self.assertEqual((home / 'review.config.toml').resolve(), source / 'review.config.toml')
            self.assertEqual((home / 'chrome-native-hosts-v2.json').resolve(), source / 'chrome-native-hosts-v2.json')
            self.assertEqual((home / 'auth.json').read_text(), '{"test_credentials":true}')
            self.assertFalse((home / 'auth.json').is_symlink())
            self.assertFalse((home / '.credentials.json').exists())
            self.assertFalse((home / 'models_cache.json').exists())
            self.assertFalse((home / 'history.jsonl').exists())
            self.assertFalse((home / 'sessions/private.jsonl').exists())
        self.assertEqual(self.path.read_bytes(), original)
        self.assertNotEqual(app.environment('personal')['CODEX_HOME'], app.environment('work')['CODEX_HOME'])

    def test_resource_union_preserves_canonical_conflicts_and_original_profile_backups(self):
        source = self.source()
        common = source / 'skills/common/SKILL.md'
        common.parent.mkdir(parents=True)
        common.write_text('Canonical skill')
        home = app.account_home('personal')
        local = home / 'skills/common/SKILL.md'
        local.parent.mkdir(parents=True)
        local.write_text('Old account skill')
        unique = home / 'skills/unique/SKILL.md'
        unique.parent.mkdir()
        unique.write_text('Account custom skill')
        (home / 'config.toml').write_text('model = "old-account-model"')
        (source / 'config.toml').write_text('model = "common-model"')
        self.sync(source)
        self.assertEqual(common.read_text(), 'Canonical skill')
        self.assertEqual((source / 'skills/unique/SKILL.md').read_text(), 'Account custom skill')
        self.off()
        self.assertEqual(local.read_text(), 'Old account skill')
        self.assertEqual(unique.read_text(), 'Account custom skill')
        self.assertEqual((home / 'config.toml').read_text(), 'model = "old-account-model"')
        self.assertFalse((app.account_home('work') / 'config.toml').exists())
        self.assertEqual(common.read_text(), 'Canonical skill')

    def test_changes_are_shared_and_repeated_sync_preserves_original_backups(self):
        source = self.source()
        (app.account_home('personal') / 'config.toml').write_text('model = "original"')
        self.sync(source)
        manifest = (app.ROOT / 'shared-links/personal.json').read_bytes()
        (app.account_home('work') / 'config.toml').write_text('model = "changed"')
        self.sync(source)
        self.assertEqual((app.ROOT / 'shared-links/personal.json').read_bytes(), manifest)
        self.assertEqual((app.account_home('personal') / 'config.toml').read_text(), 'model = "changed"')
        self.off()
        self.assertEqual((app.account_home('personal') / 'config.toml').read_text(), 'model = "original"')
        self.assertEqual((source / 'config.toml').read_text(), 'model = "changed"')

    def test_new_accounts_and_simultaneous_backend_starts_inherit_capabilities(self):
        source = self.source()
        self.sync(source)
        app.private_dir(app.account_home('new-account'))
        (app.account_home('new-account') / 'auth.json').write_text('NEW ACCOUNT AUTH')
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(app.environment, name) for name in ('new-account', 'work')]
            for future in futures: future.result(timeout=5)
        self.assertEqual((app.account_home('new-account') / 'config.toml').resolve(), source / 'config.toml')
        self.assertEqual((app.account_home('new-account') / 'auth.json').read_text(), 'NEW ACCOUNT AUTH')
        (source / 'later.config.toml').write_text('model = "later"')
        app.environment('new-account')
        self.assertEqual((app.account_home('new-account') / 'later.config.toml').resolve(), source / 'later.config.toml')

    def test_invalid_shared_homes_do_not_change_account_configuration(self):
        for source in (app.ROOT, app.ROOT.parent, app.ROOT / 'accounts', app.account_home('personal')):
            with self.assertRaises(app.Error): self.sync(source)
        self.assertFalse((app.ROOT / 'shared.json').exists())
        self.assertFalse((app.account_home('personal') / 'config.toml').exists())

    def test_interrupted_link_install_can_be_retried_and_original_restored(self):
        source = self.source()
        path = app.account_home('personal') / 'config.toml'
        path.write_text('model = "original"')
        replace = app.os.replace
        def interrupted(old, new):
            if new == path and '.shared-' in Path(old).name: raise OSError('Interrupted link installation')
            return replace(old, new)
        with patch.object(app.os, 'replace', side_effect=interrupted):
            with self.assertRaises(OSError): self.sync(source)
        self.assertFalse(path.exists())
        self.sync(source)
        self.off()
        self.assertEqual(path.read_text(), 'model = "original"')

    def test_interrupted_backup_move_is_retried_without_losing_original(self):
        source = self.source()
        path = app.account_home('personal') / 'config.toml'
        path.write_text('model = "original"')
        replace = app.os.replace
        def interrupted(old, new):
            if old == path: raise OSError('Interrupted backup move')
            return replace(old, new)
        with patch.object(app.os, 'replace', side_effect=interrupted):
            with self.assertRaises(OSError): self.sync(source)
        self.assertEqual(path.read_text(), 'model = "original"')
        self.sync(source)
        self.off()
        self.assertEqual(path.read_text(), 'model = "original"')

    def test_interrupted_migration_can_be_disabled_without_changing_original(self):
        source = self.source()
        path = app.account_home('personal') / 'config.toml'
        path.write_text('model = "original"')
        replace = app.os.replace
        def interrupted(old, new):
            if old == path: raise OSError('Interrupted backup move')
            return replace(old, new)
        with patch.object(app.os, 'replace', side_effect=interrupted):
            with self.assertRaises(OSError): self.sync(source)
        self.off()
        self.assertEqual(path.read_text(), 'model = "original"')

    def test_detached_files_are_preserved_and_reported(self):
        source = self.source()
        self.sync(source)
        path = app.account_home('work') / 'config.toml'
        path.unlink()
        path.write_text('model = "external-edit"')
        with self.assertRaisesRegex(app.Error, 'changed externally'): self.sync(source)
        with self.assertRaisesRegex(app.Error, 'changed externally'): self.off()
        self.assertEqual(path.read_text(), 'model = "external-edit"')
        self.assertEqual((source / 'config.toml').read_text(), '')

    def test_interrupted_restore_can_be_finished_without_replacing_restored_paths(self):
        source = self.source()
        path = app.account_home('personal') / 'config.toml'
        path.write_text('model = "original"')
        self.sync(source)
        replace = app.os.replace
        def interrupted(old, new):
            result = replace(old, new)
            if new == path and 'shared-backups' in str(old): raise OSError('Interrupted after restore')
            return result
        with patch.object(app.os, 'replace', side_effect=interrupted):
            with self.assertRaises(OSError): self.off()
        self.assertEqual(path.read_text(), 'model = "original"')
        with self.assertRaisesRegex(app.Error, 'finish restoring'): self.sync(source)
        with self.assertRaisesRegex(app.Error, 'finish restoring'): app.environment('work')
        path.write_text('model = "edited-after-restore"')
        self.off()
        self.assertFalse(app.shared_settings()['enabled'])
        self.assertEqual(path.read_text(), 'model = "edited-after-restore"')

    def test_interrupted_restore_before_backup_move_can_be_retried(self):
        source = self.source()
        path = app.account_home('personal') / 'config.toml'
        path.write_text('model = "original"')
        self.sync(source)
        replace = app.os.replace
        def interrupted(old, new):
            if new == path and 'shared-backups' in str(old): raise OSError('Interrupted before restore')
            return replace(old, new)
        with patch.object(app.os, 'replace', side_effect=interrupted):
            with self.assertRaises(OSError): self.off()
        self.assertFalse(path.exists())
        self.off()
        self.assertEqual(path.read_text(), 'model = "original"')

    def test_source_change_requires_restore_and_no_optional_registrations_are_fabricated(self):
        source = self.source()
        self.sync(source)
        self.assertFalse((source / 'chrome-native-hosts-v2.json').exists())
        other = app.ROOT / 'other-source'
        with self.assertRaisesRegex(app.Error, 'shared off'): self.sync(other)
        self.assertFalse(other.exists())
        self.off()
        self.sync(other)
        self.assertEqual((app.account_home('work') / 'config.toml').resolve(), (other / 'config.toml').resolve())

    def test_capability_link_into_account_is_rejected(self):
        source = self.source()
        home = app.account_home('personal')
        (home / 'skills').mkdir()
        (source / 'skills').symlink_to(home / 'skills')
        with self.assertRaisesRegex(app.Error, 'points into an account'): self.sync(source)
        self.assertFalse((home / 'skills').is_symlink())

    def test_interrupted_resource_copy_is_retried_without_publishing_partial_content(self):
        source = self.source()
        original = app.account_home('personal') / 'plugins/custom/data.txt'
        original.parent.mkdir(parents=True)
        original.write_text('COMPLETE RESOURCE')
        copy = app.shutil.copy2
        def interrupted(old, new):
            if old == original:
                Path(new).write_text('PARTIAL')
                raise OSError('Interrupted copy')
            return copy(old, new)
        with patch.object(app.shutil, 'copy2', side_effect=interrupted):
            with self.assertRaises(OSError): self.sync(source)
        self.assertFalse((source / 'plugins/custom/data.txt').exists())
        self.assertFalse(list(source.rglob('.shared-copy-*')))
        self.sync(source)
        self.assertEqual((source / 'plugins/custom/data.txt').read_text(), 'COMPLETE RESOURCE')

    def test_nested_capability_link_cannot_share_account_credentials(self):
        source = self.source()
        private = app.account_home('personal') / 'auth.json'
        plugin = app.account_home('work') / 'plugins/custom'
        plugin.mkdir(parents=True)
        (plugin / 'credentials').symlink_to(private)
        with self.assertRaisesRegex(app.Error, 'points into an account'): self.sync(source)
        self.assertFalse((source / 'plugins/custom/credentials').exists())
        self.assertEqual(private.read_text(), '{"test_credentials":true}')


if __name__ == '__main__': unittest.main()
