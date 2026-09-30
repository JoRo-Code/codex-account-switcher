import contextlib
import io
import json
import os
import time
import unittest
from collections import deque
from unittest.mock import patch
import test_launcher as fixtures
from test_auto import FakeBackend, FakeWS
app = fixtures.app

class StatusTests(unittest.TestCase):
    setUp = fixtures.LauncherTests.setUp

    def test_multi_bucket_windows_and_unknown_usage(self):
        usage = {'rateLimits': {'primary': {'usedPercent': 99}}, 'rateLimitsByLimitId': {
            'codex': {'primary': {'usedPercent': 25, 'windowDurationMins': 300, 'resetsAt': time.time()+3600},
                      'secondary': {'usedPercent': None, 'windowDurationMins': 10080}},
            'other': {'primary': {'usedPercent': 110, 'windowDurationMins': 60}}}}
        output = '\n'.join(app.usage_lines(usage))
        self.assertIn('75% left (25% used)', output)
        self.assertIn('0% left (110% used)', output)
        self.assertIn('usage unknown', output)
        self.assertIn('reset unknown', output)
        self.assertNotIn('99% used', output)

    def test_backend_block_overrides_apparently_free_windows(self):
        lines = app.usage_lines({'ordinaryUsageAllowed': False,
            'rateLimits': {'primary': {'usedPercent': 0}}})
        self.assertIn('blocked by backend', '\n'.join(lines))
        self.assertIn('100% left', '\n'.join(lines))

    def test_failed_usage_fetch_preserves_identity(self):
        class Stub:
            def __init__(self): self.messages=deque();self.closed=False
            def send(self, message):
                method = message['method']
                if method == 'initialize': self.messages.append({'id':1,'result':{}})
                if method == 'account/read':
                    self.messages.append({'id':2,'result':{'account':{
                        'type':'chatgpt','email':'person@example.com','planType':'pro'}}})
                if method == 'account/rateLimits/read':
                    self.messages.append({'id':3,'error':{'message':'SECRET_RAW_ERROR'}})
            def close(self): self.closed=True
        backend=Stub()
        with patch.object(app,'Backend',return_value=backend):
            report=app.account_snapshot('personal',include_usage=True)
        self.assertEqual(report['identity'][0],'person@example.com')
        self.assertIsNone(report['usage'])
        self.assertIsNotNone(report['usage_error'])
        self.assertNotIn('SECRET',json.dumps(report))
        self.assertTrue(backend.closed)

    def test_one_account_failure_does_not_hide_other_account(self):
        def snapshot(name, **kw):
            if name=='personal': raise app.Error('failed')
            return dict(identity=('work@example.com','pro','cached'),usage={'rateLimits':{}},
                        usage_error=None,checked_at=time.time())
        with patch.object(app,'account_snapshot',side_effect=snapshot):
            reports=app.collect_status()
        self.assertEqual(len(reports),2)
        self.assertIsNotNone(reports[0]['usage_error'])
        self.assertEqual(reports[1]['identity'][0],'work@example.com')

    def test_marker_uses_project_and_preserves_start_time(self):
        bridge=app.AutoBridge('personal',FakeWS(),app.ROOT/'runs/bridge.json',factory=FakeBackend,cwd='/chosen/project')
        self.addCleanup(bridge.close)
        started=app.read_json(bridge.marker)['started']
        self.assertEqual(app.read_json(bridge.marker)['cwd'],'/chosen/project')
        bridge.set_thread({'id':self.sid,'cwd':'/actual/project','name':'Fix login','model':'test-model'})
        bridge.inspect({'method':'turn/started','params':{'threadId':self.sid}})
        row=app.read_json(bridge.marker)
        self.assertEqual(row['cwd'],'/actual/project')
        self.assertEqual(row['started'],started)
        self.assertEqual(row['phase'],'working')
        self.assertEqual(row['title'],'Fix login')
        bridge.inspect({'method':'item/commandExecution/requestApproval','id':42,'params':{'threadId':self.sid}})
        self.assertEqual(app.read_json(bridge.marker)['phase'],'waiting for input')
        bridge.from_client({'id':42,'result':{'decision':'accept'}})
        self.assertEqual(app.read_json(bridge.marker)['phase'],'working')
        bridge.inspect({'method':'turn/completed','params':{'threadId':self.sid,'turn':{'status':'completed'}}})
        self.assertEqual(app.read_json(bridge.marker)['phase'],'idle')

    def test_subagent_activity_does_not_change_parent_status(self):
        bridge=app.AutoBridge('personal',FakeWS(),app.ROOT/'runs/bridge.json',factory=FakeBackend)
        self.addCleanup(bridge.close)
        bridge.set_thread({'id':self.sid})
        bridge.inspect({'method':'turn/started','params':{'threadId':'other'}})
        self.assertEqual(app.read_json(bridge.marker)['phase'],'idle')

    def test_render_lists_locations_and_handles_unknown_legacy_markers(self):
        report=dict(label='personal',identity=('person@example.com','pro','cached'),
                    usage=None,usage_error='Offline',checked_at=time.time(),routing={},runs=[
                        dict(pid=os.getpid(),account='personal',session=self.sid,cwd='/project')])
        output=io.StringIO()
        with contextlib.redirect_stdout(output):app.render_status([report])
        text=output.getvalue()
        self.assertIn('/project',text)
        self.assertIn(self.sid,text)
        self.assertIn('turn state unknown',text)
        self.assertIn('Limits unavailable: Offline',text)
        self.assertNotIn('0% used',text)

    def test_json_snapshot_and_watch_validation(self):
        output=io.StringIO()
        with patch.object(app,'collect_status',return_value=[]),contextlib.redirect_stdout(output):
            app.show_status(as_json=True)
        self.assertEqual(json.loads(output.getvalue()),[])
        with self.assertRaises(app.Error): app.show_status(interval=1)
        with self.assertRaises(app.Error): app.show_status(watch=True,as_json=True)

    def test_watch_refreshes_and_exits_cleanly_without_login_mutations(self):
        with patch.object(app.sys.stdout,'isatty',return_value=True), \
             patch.object(app,'collect_status',return_value=[]) as collect, \
             patch.object(app,'render_status'), patch('builtins.print'), \
             patch.object(app.time,'sleep',side_effect=[None,KeyboardInterrupt]):
            self.assertEqual(app.show_status(watch=True),0)
        self.assertEqual(collect.call_count,2)

if __name__=='__main__': unittest.main()
