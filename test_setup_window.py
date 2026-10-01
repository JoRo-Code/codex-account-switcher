import http.client
import json
import threading
import unittest
from unittest.mock import patch
import test_launcher as fixtures
app=fixtures.app

class WindowTests(unittest.TestCase):
    setUp=fixtures.LauncherTests.setUp
    def server(self):
        self.window=app.SetupWindow()
        server=app.setup_http_server(self.window)
        t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        return server
    def request(self,server,path='/api/state',method='GET',headers=None,body=None):
        conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=2)
        conn.request(method,path,body=body,headers=headers or {})
        r=conn.getresponse();data=r.read();conn.close();return r.status,data
    def test_auth_host_and_origin_are_required(self):
        s=self.server();auth={'Authorization':'Bearer '+self.window.token}
        self.assertEqual(self.request(s)[0],403)
        self.assertEqual(self.request(s,headers=auth)[0],200)
        self.assertEqual(self.request(s,headers=dict(auth,Host='evil.example'))[0],403)
        self.assertEqual(self.request(s,headers=dict(auth,Origin='https://evil.example'))[0],403)
        self.assertEqual(self.request(s,method='POST',path='/api/action',body='{"action":"connect"}')[0],403)
    def test_only_known_actions_and_valid_labels(self):
        s=self.server();auth={'Authorization':'Bearer '+self.window.token}
        for data in ({'action':'shell'},{'action':'add','label':'../escape'},['connect']):
            code,body=self.request(s,'/api/action','POST',auth,json.dumps(data))
            self.assertIn(code,(200,400))
            if code==200:self.assertTrue(json.loads(body)['job']['error'])
        self.assertFalse(self.window.job['busy'])
    def test_page_has_no_secrets_and_state_does_not_claim_desktop_linked(self):
        s=self.server();code,body=self.request(s,'/')
        self.assertEqual(code,200);self.assertNotIn(self.window.token.encode(),body)
        state=self.window.snapshot()
        self.assertFalse(state['ready']);self.assertNotIn('test_credentials',json.dumps(state))
        self.assertEqual(len(state['accounts']),2)
    def test_connect_uses_terminal_subprocess_and_failure_is_visible(self):
        w=app.SetupWindow(account='work',port=22284)
        with patch.object(app.subprocess,'Popen') as popen:
            popen.return_value.wait.return_value=1
            w.work('connect','')
        args=popen.call_args[0][0]
        self.assertEqual(args[-6:],['setup','--terminal','--account','work','--port','22284'])
        self.assertTrue(w.job['error']);self.assertFalse(w.job['busy'])
    def test_add_uses_generated_label_and_preserves_existing_accounts(self):
        w=app.SetupWindow()
        with patch.object(app.subprocess,'Popen') as popen,patch.object(app,'collect_status',return_value=[]):
            popen.return_value.wait.return_value=0
            w.work('add','')
        self.assertEqual(popen.call_args[0][0][-2:],['add','account-1'])
        with patch.object(app.subprocess,'Popen') as popen:w.work('add','personal')
        popen.assert_not_called();self.assertTrue(w.job['error'])
    def test_parser_keeps_terminal_option_and_hides_internal_server(self):
        self.assertTrue(app.parser().parse_args(['setup','--terminal']).terminal)
        self.assertNotIn('setup-window',app.parser().format_help())

if __name__=='__main__':unittest.main()
