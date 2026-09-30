import contextlib
import io
import os
import sqlite3
import unittest
from unittest.mock import patch
import test_launcher as fixtures
app=fixtures.app

class OverviewTests(unittest.TestCase):
    setUp=fixtures.LauncherTests.setUp

    def overview(self):
        with patch.object(app,'local_chats',return_value=[]):return app.conversation_overview()

    def test_old_storage_does_not_fabricate_account_usage(self):
        row=self.overview()['conversations'][0]
        self.assertEqual(row['stored_account'],'personal')
        self.assertEqual(row['observed_accounts'],[])
        self.assertEqual(row['activity'],[])

    def test_usage_history_survives_move_and_deduplicates_turn_events(self):
        app.record_activity(self.sid,'personal','auto_opened')
        for _ in range(2):app.record_activity(self.sid,'personal','turn_started',key='turn1')
        with contextlib.redirect_stdout(io.StringIO()):app.move(app.choose_session(self.sid),'work')
        row=self.overview()['conversations'][0]
        self.assertEqual(row['stored_account'],'work')
        self.assertEqual(row['observed_accounts'],['personal'])
        self.assertEqual(len(row['activity']),3)
        app.record_activity(self.sid,'work','auto_opened')
        self.assertEqual(self.overview()['conversations'][0]['observed_accounts'],['personal','work'])

    def test_running_and_unidentified_sessions_remain_visible(self):
        app.atomic_json(app.ROOT/'runs/known.json',dict(pid=os.getpid(),account='personal',session=self.sid,phase='working'))
        app.atomic_json(app.ROOT/'runs/unknown.json',dict(pid=os.getpid(),account='work',session=None,cwd='/tmp'))
        result=self.overview()
        self.assertEqual(result['conversations'][0]['running'][0]['phase'],'working')
        self.assertEqual(result['unassigned_launches'][0]['account'],'work')

    def test_old_unmatched_launcher_is_not_counted_as_an_extra_chat(self):
        app.atomic_json(app.ROOT/'runs/old.json',dict(pid=os.getpid(),account='personal',
            session='helper-id',mode='auto',title='Same title'))
        result=self.overview()
        self.assertEqual(len(result['conversations']),1)
        self.assertEqual(result['unverified_launches'][0]['session'],'helper-id')
        with patch.object(app,'local_chats',return_value=[]),patch.object(app,'collect_status',return_value=[]),contextlib.redirect_stdout(io.StringIO()) as output:
            app.show_overview()
        self.assertIn('chat tracking unverified',output.getvalue())
        self.assertIn('no verified running session',output.getvalue())

    def test_current_unsaved_launcher_remains_a_conversation(self):
        app.atomic_json(app.ROOT/'runs/new.json',dict(pid=os.getpid(),account='personal',
            session='new-id',mode='auto',tracking_version=app.VERSION))
        result=self.overview()
        self.assertEqual(len(result['conversations']),2)
        self.assertEqual(result['unverified_launches'],[])

    def test_historical_account_filter_includes_moved_chat(self):
        app.record_activity(self.sid,'personal','auto_opened')
        with contextlib.redirect_stdout(io.StringIO()):app.move(app.choose_session(self.sid),'work')
        with patch.object(app,'local_chats',return_value=[]),patch.object(app,'collect_status',return_value=[]),contextlib.redirect_stdout(io.StringIO()) as output:
            app.show_overview(account='personal',history=True)
        self.assertIn(self.sid,output.getvalue())
        self.assertIn('personal → work',output.getvalue())

    def test_audit_write_failure_does_not_stop_conversation(self):
        with patch.object(app.sqlite3,'connect',side_effect=sqlite3.OperationalError('read only')),contextlib.redirect_stderr(io.StringIO()) as err:
            app.record_activity(self.sid,'personal','turn_started')
        self.assertIn('could not record',err.getvalue())

    def test_picker_layout_fits_narrow_and_wide_terminals(self):
        rows=app.session_records()
        for width in (45,80,120):
            lines=app.picker_screen(rows,'login','all','/tmp',0,24,width,{})
            self.assertTrue(any(style=='selected' for _,_,style in lines))
            self.assertTrue(all(len(text)<=width-1 for _,text,_ in lines))
            self.assertTrue(all(0<=y<24 for y,_,_ in lines))

    def test_picker_scope_and_search_are_composable(self):
        rows=[dict(id='a',title='Billing login',cwd='/tmp/project',account='work'),dict(id='b',title='Billing tests',cwd='/tmp/other',account='local',source_home='/tmp/local')]
        self.assertEqual([r['id'] for r in app.filter_picker_rows(rows,'billing','project','/tmp/project')],['a'])
        self.assertEqual(len(app.filter_picker_rows(rows,'billing','all','/tmp/project')),2)
        self.assertEqual([r['id'] for r in app.filter_picker_rows(rows,'billing','launcher','/tmp/project')],['a'])

if __name__=='__main__':unittest.main()
