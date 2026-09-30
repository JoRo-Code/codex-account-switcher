import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

loader = importlib.machinery.SourceFileLoader('launcher', str(Path(__file__).with_name('codex-accounts')))
spec = importlib.util.spec_from_loader(loader.name, loader)
app = importlib.util.module_from_spec(spec)
loader.exec_module(app)

class LauncherTests(unittest.TestCase):
    def setUp(self):
        binary_patch = patch.object(app, "BINARY", sys.executable)
        binary_patch.start()
        self.addCleanup(binary_patch.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        app.ROOT = Path(self.tmp.name)
        for name in ['personal', 'work']:
            app.private_dir(app.account_home(name))
            (app.account_home(name) / 'auth.json').write_text('{"test_credentials":true}')
        self.sid = str(uuid.uuid4())
        self.path = app.account_home('personal') / 'sessions/2026/09/29' / f'rollout-2026-09-29T12-00-00-{self.sid}.jsonl'
        self.path.parent.mkdir(parents=True)
        self.rows = [dict(type='session_meta', payload=dict(id=self.sid, cwd=self.tmp.name, history_mode='legacy')),
                     dict(type='event_msg', payload=dict(type='user_message', message='Fix login page'))]
        self.path.write_text(''.join(json.dumps(x) + '\n' for x in self.rows))

    def quiet_move(self, row, target):
        with contextlib.redirect_stdout(io.StringIO()):
            app.move(row, target)

    def test_environment_isolates_accounts_and_removes_ambient_auth(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY':'secret', 'CODEX_THREAD_ID':'existing', 'CODEX_HOME':'old'}):
            a, b = app.environment('personal'), app.environment('work')
        self.assertNotEqual(a['CODEX_HOME'], b['CODEX_HOME'])
        self.assertNotIn('OPENAI_API_KEY', a)
        self.assertNotIn('CODEX_THREAD_ID', a)
        self.assertEqual(Path(a['CODEX_HOME']), app.account_home('personal'))

    def test_move_preserves_full_history_and_roundtrip_avoids_duplicates(self):
        original = self.path.read_bytes()
        self.quiet_move(app.choose_session(self.sid), 'work')
        row = app.choose_session(self.sid)
        self.assertEqual(row['account'], 'work')
        self.assertEqual(Path(row['path']).read_bytes(), original)
        self.assertEqual(self.path.read_bytes(), original)
        with Path(row['path']).open('a') as f:
            f.write(json.dumps({'type':'event_msg','payload':{'type':'agent_message','message':'Done'}})+'\n')
        updated = Path(row['path']).read_bytes()
        self.quiet_move(app.choose_session(self.sid), 'personal')
        self.assertEqual(self.path.read_bytes(), updated)
        self.assertEqual(len(list((app.account_home('personal')/'sessions').rglob('*.jsonl'))), 1)
        self.assertEqual(len(app.session_records()), 1)
        self.assertTrue(list((app.ROOT/'backups').glob('*.jsonl')))

    def test_resume_passes_account_cwd_and_no_daemon(self):
        with patch.object(app.subprocess, 'call', return_value=7) as call, contextlib.redirect_stdout(io.StringIO()):
            result = app.run('personal', app.choose_session(self.sid), prompt='Continue safely')
        self.assertEqual(result, 7)
        args = call.call_args.args[0]
        self.assertIn('--no-daemon', args)
        self.assertEqual(args[1:3], ['resume', self.sid])
        self.assertEqual(args[-2:], ['--', 'Continue safely'])
        self.assertEqual(call.call_args.kwargs['env']['CODEX_HOME'], str(app.account_home('personal')))
        self.assertFalse(list((app.ROOT/'runs').glob('*.json')))

    def test_move_rejects_running_session(self):
        app.atomic_json(app.ROOT/'runs/active.json', dict(pid=os.getpid(), account='personal',session=self.sid))
        with self.assertRaises(app.Error):
            self.quiet_move(app.choose_session(self.sid), 'work')
        self.assertFalse(app.owners())

    def test_move_allows_other_known_conversation_to_continue(self):
        app.atomic_json(app.ROOT/'runs/active.json', dict(pid=os.getpid(), account='personal',session=str(uuid.uuid4())))
        self.quiet_move(app.choose_session(self.sid), 'work')
        self.assertEqual(app.choose_session(self.sid)['account'], 'work')

    def test_paginated_move_fails_without_changes(self):
        row = app.choose_session(self.sid)
        row['history_mode']='paginated'
        with self.assertRaises(app.Error):
            self.quiet_move(row, 'work')
        self.assertFalse(list((app.account_home('work')/'sessions').rglob('*.jsonl')))

    def test_two_account_processes_can_hold_locks_concurrently(self):
        with app.lock('account-personal', shared=True), app.lock('account-work', shared=True):
            with self.assertRaises(app.Error):
                with app.lock('account-personal'):
                    pass

    def test_duplicate_session_lock_rejects_second_resume(self):
        with app.lock('session-' + self.sid):
            with self.assertRaises(app.Error):
                app.run('personal', app.choose_session(self.sid))

    def test_bad_name_and_missing_account_are_rejected(self):
        with self.assertRaises(app.Error):
            app.account_home('../outside')
        with self.assertRaises(app.Error):
            app.environment('missing')

    def test_titles_are_extracted_without_tool_output(self):
        self.assertEqual(app.choose_session(self.sid)['title'], 'Fix login page')

    def test_list_displays_email_and_plan_and_handles_one_failed_lookup(self):
        def identity(name):
            if name == 'work':
                raise app.Error('do not expose raw backend errors or tokens')
            return ('person@example.com', 'pro', 'cached')
        output = io.StringIO()
        with patch.object(app, 'account_identity', side_effect=identity), contextlib.redirect_stdout(output):
            app.list_accounts()
        text = output.getvalue()
        self.assertIn('person@example.com', text)
        self.assertIn('pro', text)
        self.assertIn('identity unavailable', text)
        self.assertNotIn('raw backend errors', text)

    def test_identity_uses_account_read_without_refresh_and_closes_backend(self):
        from collections import deque
        class Stub:
            def __init__(self):
                self.messages = deque()
                self.sent = []
                self.closed = False
            def send(self, message):
                self.sent.append(message)
                if message.get('method') == 'initialize':
                    self.messages.append({'id': 1, 'result': {}})
                if message.get('method') == 'account/read':
                    self.messages.append({'id': 2, 'result': {'account': {
                        'type': 'chatgpt', 'email': 'person@example.com', 'planType': 'plus'}}})
            def close(self):
                self.closed = True
        backend = Stub()
        with patch.object(app, 'Backend', return_value=backend):
            self.assertEqual(app.account_identity('personal'), ('person@example.com', 'plus', 'cached'))
        self.assertTrue(backend.closed)
        self.assertIn({'id': 2, 'method': 'account/read', 'params': {'refreshToken': False}}, backend.sent)

if __name__ == '__main__':
    unittest.main()
