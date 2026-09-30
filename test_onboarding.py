import json
import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import test_launcher as fixtures
app=fixtures.app

class OnboardingTests(unittest.TestCase):
    setUp=fixtures.LauncherTests.setUp
    def settings(self):
        home=app.ROOT/'Home with spaces';home.mkdir(exist_ok=True)
        return home,app.desktop_config('personal',22284,'codex-auto','/usr/bin/true',home)
    def fake_keygen(self,args,**kwargs):
        key=Path(args[-1]);key.write_text('private fixture')
        key.with_suffix('.pub').write_text('ssh-ed25519 fixture test\n')
        return subprocess.CompletedProcess(args,0)
    def generate(self):
        home,settings=self.settings()
        with patch.object(app.subprocess,'run',side_effect=self.fake_keygen):app.generate_desktop_files(settings,home)
        return home,settings
    def test_setup_preserves_accounts_and_keys_and_ssh_configuration(self):
        home,settings=self.settings();(home/'.ssh').mkdir()
        (home/'.ssh/config').write_text('Host original\n  HostName original.example\n')
        auth=(app.account_home('personal')/'auth.json').read_bytes()
        with patch.object(app.subprocess,'run',side_effect=self.fake_keygen) as run:
            app.generate_desktop_files(settings,home)
            first=(app.ROOT/'desktop/client_key').read_bytes()
            app.generate_desktop_files(settings,home)
        self.assertEqual(run.call_count,2)
        self.assertEqual((app.ROOT/'desktop/client_key').read_bytes(),first)
        self.assertEqual((app.account_home('personal')/'auth.json').read_bytes(),auth)
        text=(home/'.ssh/config').read_text()
        self.assertEqual(text.count('Include '),1);self.assertIn('Host original',text)
        self.assertEqual((app.ROOT/'desktop/ssh_config.before').read_text(),'Host original\n  HostName original.example\n')
    def test_services_are_user_owned_and_isolated_from_other_launch_agents(self):
        home,settings=self.generate()
        for kind,path in settings['plists'].items():
            d=plistlib.loads(Path(path).read_bytes())
            self.assertEqual(d['Label'],app.desktop_label(kind))
            self.assertTrue(d['RunAtLoad']);self.assertTrue(d['KeepAlive'])
            self.assertEqual(d['EnvironmentVariables']['CODEX_ACCOUNTS_HOME'],str(app.ROOT))
        config=(app.ROOT/'desktop/sshd_config').read_text()
        self.assertIn('ListenAddress 127.0.0.1',config)
        self.assertIn('PasswordAuthentication no',config)
        self.assertIn('AllowAgentForwarding no',config)
        self.assertNotIn('0.0.0.0',config)
    def test_start_does_not_restart_loaded_services(self):
        self.generate()
        with patch.object(app.sys,'platform','darwin'),patch.object(app,'launchctl_loaded',return_value=True),patch.object(app.subprocess,'run') as run:
            app.desktop_service('start')
        run.assert_not_called()
    def test_native_daemon_mutation_is_rejected_even_with_global_flags(self):
        self.generate()
        with self.assertRaises(app.Error):app.desktop_proxy(['-c','x=true','app-server','daemon','stop'])
    def test_proxy_uses_managed_socket(self):
        home,settings=self.generate()
        with patch.object(app.os,'execv',side_effect=RuntimeError('exec')) as execute:
            with self.assertRaises(RuntimeError):app.desktop_proxy(['-c','x=true','app-server','proxy'])
        self.assertEqual(execute.call_args.args[1],['/usr/bin/true','app-server','proxy','--sock',settings['socket']])
    def test_no_accounts_in_noninteractive_setup_has_actionable_error(self):
        with patch.object(app.sys,'platform','darwin'),patch.object(app,'accounts',return_value=[]),patch.object(app.Path,'is_file',return_value=True),patch.object(app.sys.stdin,'isatty',return_value=False):
            with self.assertRaisesRegex(app.Error,'add NAME'):app.setup_desktop()
    def test_status_reports_unreachable_services_without_crashing(self):
        self.generate()
        with patch.object(app,'launchctl_loaded',return_value=False),patch.object(app.socket.socket,'connect',side_effect=ConnectionRefusedError):
            status=app.desktop_status(True)
        self.assertFalse(status['router_reachable']);self.assertFalse(status['ssh_reachable'])

    def test_non_mac_setup_fails_without_creating_files(self):
        with patch.object(app.sys,'platform','linux'):
            with self.assertRaisesRegex(app.Error,'macOS'):app.setup_desktop()
        self.assertFalse((app.ROOT/'desktop').exists())

if __name__=='__main__':unittest.main()
