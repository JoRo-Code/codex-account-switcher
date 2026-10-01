"""Real Codex configuration writes, skills and MCP inheritance; no inference."""
import contextlib
import io
import json
from pathlib import Path
import select
import shutil
import sys
import tempfile
import time
from test_launcher import app


binary = shutil.which('codex')
if not binary: raise SystemExit('Codex CLI required for this optional check.')

with tempfile.TemporaryDirectory(prefix='cas-shared-') as temporary:
    app.ROOT = Path(temporary).resolve()
    app.BINARY = binary
    source = app.ROOT / 'common'
    source.mkdir()
    server = source / 'fixture-mcp.py'
    server.write_text('''import json, sys
for line in sys.stdin:
    message = json.loads(line)
    if 'id' not in message: continue
    method = message.get('method')
    if method == 'initialize':
        result = {'protocolVersion': '2024-11-05', 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'shared-fixture', 'version': '1'}}
    elif method == 'tools/list':
        result = {'tools': [{'name': 'shared_fixture', 'description': 'Offline inheritance fixture', 'inputSchema': {'type': 'object', 'properties': {}}}]}
    elif method in ('resources/list', 'resources/templates/list'):
        result = {'resources': []} if method == 'resources/list' else {'resourceTemplates': []}
    else: result = {}
    print(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': result}), flush=True)
''')
    (source / 'config.toml').write_text('model = "shared-before"\n[mcp_servers.shared_fixture]\ncommand = ' + json.dumps(sys.executable) + '\nargs = [' + json.dumps(str(server)) + ']\n')
    skill = source / 'skills/shared-fixture/SKILL.md'
    skill.parent.mkdir(parents=True)
    skill.write_text('---\nname: shared-fixture\ndescription: Offline shared capability fixture\n---\nUse only for inheritance verification.\n')
    originals = {}
    for name in ('a', 'b'):
        home = app.account_home(name)
        app.private_dir(home)
        originals[name] = ('{"fixture_account": "' + name + '"}').encode()
        (home / 'auth.json').write_bytes(originals[name])
    with contextlib.redirect_stdout(io.StringIO()): app.shared_capabilities('sync', source)

    class Client:
        def __init__(self, name):
            self.backend = app.Backend(name)
            self.sequence = 0
            self.rpc('initialize', {'clientInfo': {'name': 'shared_capability_test', 'version': '1'}, 'capabilities': {'experimentalApi': True}})
            self.backend.send({'method': 'initialized'})

        def rpc(self, method, params):
            self.sequence += 1
            identifier = self.sequence
            self.backend.send({'id': identifier, 'method': method, 'params': params})
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                while self.backend.messages:
                    message = self.backend.messages.popleft()
                    if message.get('id') == identifier:
                        if 'error' in message: raise AssertionError(message['error'])
                        return message['result']
                if select.select([self.backend.process.stdout], [], [], .1)[0]: self.backend.read()
            raise AssertionError('RPC timed out: ' + method)

        def close(self): self.backend.close()

    clients = []
    try:
        for name in ('a', 'b'):
            client = Client(name)
            clients.append(client)
            effective = client.rpc('config/read', {'includeLayers': True})
            assert effective['config']['model'] == 'shared-before'
            assert 'shared_fixture' in effective['config']['mcp_servers']
            tools = client.rpc('mcpServerStatus/list', {'serverName': 'shared_fixture'})['data']
            assert any('shared_fixture' in entry['tools'] for entry in tools), tools
            skills = client.rpc('skills/list', {'cwds': [str(app.ROOT)], 'forceReload': True})['data']
            assert any(s['name'] == 'shared-fixture' for row in skills for s in row['skills']), skills
        clients[0].rpc('config/value/write', {'keyPath': 'model', 'value': 'shared-after', 'mergeStrategy': 'replace'})
        assert (app.account_home('a') / 'config.toml').is_symlink()
        assert 'shared-after' in (source / 'config.toml').read_text()
        fresh = Client('b')
        clients.append(fresh)
        assert fresh.rpc('config/read', {'includeLayers': False})['config']['model'] == 'shared-after'
        for name in ('a', 'b'): assert (app.account_home(name) / 'auth.json').read_bytes() == originals[name]
        print('PASS: real Codex backends inherit common config, skills and MCP tools; native writes reach a replacement account; credentials remain separate. No model requests.')
    finally:
        for client in clients: client.close()
