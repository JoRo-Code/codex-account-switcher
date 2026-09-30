import contextlib
import io
import json
from pathlib import Path
import sqlite3
import unittest
import uuid
from unittest.mock import patch
import test_launcher as fixtures
app = fixtures.app

class ContinueTests(unittest.TestCase):
    setUp = fixtures.LauncherTests.setUp

    def local(self, sid=None):
        home = app.ROOT/'existing-codex'
        sid = sid or str(uuid.uuid4())
        path = home/'sessions/2026/09/30'/('rollout-'+sid+'.jsonl')
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = [dict(type='session_meta',payload=dict(id=sid,cwd=self.tmp.name,history_mode='paginated',source='cli')),
                dict(type='event_msg',payload=dict(type='item_completed',item=dict(type='UserMessage',content=[dict(type='text',text='Repair billing login')])))]
        path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
        return home,path,sid

    def report(self, name, allowed=True):
        return dict(label=name,identity=('person@example.com','pro','cached'),usage={'ordinaryUsageAllowed':allowed},runs=[],routing={})

    def test_local_discovery_searches_paginated_title_and_project(self):
        home,path,sid = self.local()
        rows = app.discover_chats('billing', home)
        self.assertEqual([r['id'] for r in rows],[sid])
        self.assertEqual(rows[0]['source_home'],str(home.resolve()))
        self.assertEqual(rows[0]['title'],'Repair billing login')

    def test_database_title_and_current_project_take_precedence(self):
        home,path,sid=self.local()
        with sqlite3.connect(home/'state_5.sqlite') as db:
            db.execute('CREATE TABLE threads (id TEXT,title TEXT,cwd TEXT,archived INTEGER)')
            db.execute('INSERT INTO threads VALUES (?,?,?,0)',(sid,'Renamed chat',self.tmp.name))
        self.assertEqual(app.discover_chats('Renamed',home)[0]['title'],'Renamed chat')

    def test_managed_copy_wins_over_local_original(self):
        home,_,_=self.local(self.sid)
        rows=app.discover_chats(self.sid,home)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['account'],'personal')
        self.assertNotIn('source_home',rows[0])

    def test_import_preserves_original_and_does_not_copy_auth(self):
        home,path,sid=self.local();original=path.read_bytes()
        (home/'auth.json').write_text('PRIVATE SOURCE AUTH')
        row=app.local_chats(home)[0]
        with contextlib.redirect_stdout(io.StringIO()):app.move(row,'work',source_home=home)
        self.assertEqual(path.read_bytes(),original)
        self.assertEqual(Path(app.choose_session(sid)['path']).read_bytes(),original)
        self.assertEqual((app.account_home('work')/'auth.json').read_text(),'{"test_credentials":true}')

    def test_live_quota_selection_skips_exhausted_and_prefers_current(self):
        reports=[self.report('personal',False),self.report('work',True)]
        self.assertEqual(app.select_ready_account(reports,preferred='personal')['label'],'work')
        with self.assertRaises(app.Error):app.select_ready_account(reports,requested='personal')
        reports[0]['usage']['ordinaryUsageAllowed']=True
        self.assertEqual(app.select_ready_account(reports,preferred='personal')['label'],'personal')

    def test_unknown_quota_requires_explicit_account(self):
        reports=[self.report('work',None)]
        with self.assertRaises(app.Error):app.select_ready_account(reports)
        self.assertEqual(app.select_ready_account(reports,requested='work')['label'],'work')

    def test_list_only_does_not_import_launch_or_check_accounts(self):
        home,_,sid=self.local()
        with patch.object(app,'collect_status') as status,patch.object(app,'auto_run') as run,contextlib.redirect_stdout(io.StringIO()) as out:
            app.continue_chat('billing',source_home=home,as_json=True)
        self.assertEqual(json.loads(out.getvalue())[0]['id'],sid)
        status.assert_not_called();run.assert_not_called()
        self.assertNotIn(sid,app.owners())

    def test_continue_imports_once_and_launches_with_live_selected_account(self):
        home,_,sid=self.local()
        with patch.object(app.sys.stdin,'isatty',return_value=True),patch.object(app,'collect_status',return_value=[self.report('personal',False),self.report('work')]),patch.object(app,'auto_run',return_value=0) as run,contextlib.redirect_stdout(io.StringIO()):
            app.continue_chat('billing',source_home=home)
        run.assert_called_once_with(account='work',session=sid)
        self.assertEqual(app.choose_session(sid)['account'],'work')

    def test_active_local_writer_blocks_import(self):
        home,_,sid=self.local();row=app.local_chats(home)[0]
        with app.history_writer_lock(home,sid),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(app.Error):app.move(row,'work',source_home=home)
        self.assertNotIn(sid,app.owners())

    def test_picker_filters_by_project_without_needing_id(self):
        home,_,sid=self.local()
        rows=app.discover_chats('',home)
        with patch.object(app.sys.stdin,'isatty',return_value=True),patch('builtins.input',side_effect=['billing','1']),contextlib.redirect_stdout(io.StringIO()):
            selected=app.pick_chat(rows)
        self.assertEqual(selected['id'],sid)

if __name__=='__main__':unittest.main()
