"""Native multi-client routing and disconnect/resume smoke test; no inference."""
import json, os, select, shutil, subprocess, sys, tempfile, time, uuid
from pathlib import Path

binary=shutil.which('codex')
if not binary:raise SystemExit('Codex CLI required')
source=Path(__file__).with_name('codex-accounts').resolve()
with tempfile.TemporaryDirectory(prefix='car-',dir='/tmp') as tmp:
    root=Path(tmp);address=root/'r.sock';sid=str(uuid.uuid4())
    for account in ('a','b'):
        home=root/'accounts'/account;home.mkdir(parents=True)
        (home/'auth.json').write_text('{}')
    common=root/'common';common.mkdir()
    fixture=common/'mcp.py'
    fixture.write_text('''import json,sys
for line in sys.stdin:
    request=json.loads(line)
    if 'id' not in request: continue
    method=request.get('method')
    if method=='initialize': result={'protocolVersion':'2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'shared','version':'1'}}
    elif method=='tools/list': result={'tools':[{'name':'shared_fixture','description':'Offline test','inputSchema':{'type':'object','properties':{}}}]}
    elif method=='resources/list': result={'resources':[]}
    elif method=='resources/templates/list': result={'resourceTemplates':[]}
    else: result={}
    print(json.dumps({'jsonrpc':'2.0','id':request['id'],'result':result}),flush=True)
''')
    (common/'config.toml').write_text('[mcp_servers.shared_fixture]\ncommand='+json.dumps(sys.executable)+'\nargs=['+json.dumps(str(fixture))+']\n')
    (root/'shared.json').write_text(json.dumps({'enabled':True,'home':str(common)}))
    logs=root/'accounts/a/sessions/2026/09/29';logs.mkdir(parents=True)
    meta={'id':sid,'timestamp':'2026-09-29T12:00:00Z','cwd':tmp,'originator':'codex_cli_rs',
          'cli_version':'0.159.2','source':'cli','model_provider':'openai','base_instructions':{'text':'Test only.'}}
    (logs/('rollout-2026-09-29T12-00-00-'+sid+'.jsonl')).write_text(json.dumps({'timestamp':'2026-09-29T12:00:00Z','type':'session_meta','payload':meta})+'\n')
    with (logs/('rollout-2026-09-29T12-00-00-'+sid+'.jsonl')).open('a') as f:
        for kind,payload in [
            ('response_item',{'type':'message','role':'user','content':[{'type':'input_text','text':'Router history fixture'}]}),
            ('event_msg',{'type':'user_message','message':'Router history fixture','images':[]}),
            ('event_msg',{'type':'task_complete','turn_id':str(uuid.uuid4()),'last_agent_message':'Fixture complete'})]:
            f.write(json.dumps({'timestamp':'2026-09-29T12:00:00Z','type':kind,'payload':payload})+'\n')
    env=dict(os.environ,CODEX_ACCOUNTS_HOME=tmp,CODEX_ACCOUNTS_BINARY=binary,CODEX_ACCOUNTS_NO_UPDATE='1')
    env.pop('CODEX_THREAD_ID',None)
    logfile=(root/'router.log').open('w+')
    runner=root/'runner.py'
    runner.write_text("""
import importlib.machinery,importlib.util,sys,uuid
loader=importlib.machinery.SourceFileLoader('router_app',sys.argv[1])
spec=importlib.util.spec_from_loader(loader.name,loader)
app=importlib.util.module_from_spec(spec);loader.exec_module(app)
class FaultBackend(app.Backend):
    def send(self,message):
        if message.get('method')!='turn/start': return super().send(message)
        # Inject protocol events only; never send inference requests.
        sid=message['params']['threadId'];turn={'id':str(uuid.uuid4()),'status':'inProgress','items':[]}
        self.messages.append({'id':message['id'],'result':{'turn':dict(turn)}})
        self.messages.append({'method':'turn/started','params':{'threadId':sid,'turn':dict(turn)}})
        if self.name=='a':
            turn.update(status='failed',error={'message':'Injected quota','codexErrorInfo':'usageLimitExceeded'})
        else: turn.update(status='completed',error=None)
        self.messages.append({'method':'turn/completed','params':{'threadId':sid,'turn':turn}})
app.MultiRouter.__init__.__defaults__=(None,FaultBackend)
app.serve_router(sys.argv[2], 'a')
""")
    server=subprocess.Popen(['python3',str(runner),str(source),str(address)],env=env,stderr=logfile)
    clients=[]
    class Client:
        def __init__(self):
            self.p=subprocess.Popen([binary,'app-server','proxy','--sock',str(address)],env=env,
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
            self.buf=b'';self.i=0;clients.append(self)
        def rpc(self,method,params):
            self.i+=1;i=self.i
            self.p.stdin.write((json.dumps({'id':i,'method':method,'params':params})+'\n').encode());self.p.stdin.flush()
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                while b'\n' in self.buf:
                    line,self.buf=self.buf.split(b'\n',1);result=json.loads(line)
                    if result.get('id')==i:
                        if 'error' in result:raise AssertionError(result['error'])
                        return result['result']
                if select.select([self.p.stdout],[],[],.2)[0]:
                    chunk=os.read(self.p.stdout.fileno(),65536)
                    if not chunk:raise AssertionError('Proxy disconnected')
                    self.buf+=chunk
            raise AssertionError('RPC timeout: '+method)
        def initialize(self):
            self.rpc('initialize',{'clientInfo':{'name':'native_router_test','version':'1'},'capabilities':{'experimentalApi':True}})
            self.p.stdin.write(b'{"method":"initialized"}\n');self.p.stdin.flush()
        def close(self):
            if self.p.poll() is None:
                self.p.terminate();self.p.wait(timeout=5)
    try:
        deadline=time.monotonic()+10
        while not address.exists() and time.monotonic()<deadline:time.sleep(.05)
        a=Client();a.initialize();b=Client();b.initialize()
        assert a.rpc('thread/resume',{'threadId':sid,'excludeTurns':True})['thread']['id']==sid
        other=b.rpc('thread/start',{'cwd':tmp,'experimentalRawEvents':False})['thread']['id']
        assert other!=sid
        assert set(a.rpc('thread/loaded/list',{})['data'])=={sid,other}
        a.close()
        c=Client();c.initialize()
        assert c.rpc('thread/resume',{'threadId':sid,'excludeTurns':True})['thread']['id']==sid
        assert b.rpc('thread/read',{'threadId':other})['thread']['id']==other
        assert any('shared_fixture' in row['tools'] for row in c.rpc('mcpServerStatus/list',{'threadId':sid,'serverName':'shared_fixture'})['data'])
        listed=c.rpc('thread/list',{'sourceKinds':['cli','appServer','vscode'],'limit':100})['data']
        assert sid in {r['id'] for r in listed}, listed
        c.rpc('turn/start',{'threadId':sid,'input':[{'type':'text','text':'Injected test only','text_elements':[]}]})
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            ownership=json.loads((root/'owners.json').read_text()) if (root/'owners.json').exists() else {}
            if ownership.get(sid)=='b':break
            time.sleep(.05)
        assert ownership.get(sid)=='b', ownership
        assert c.rpc('thread/read',{'threadId':sid})['thread']['id']==sid
        assert b.rpc('thread/read',{'threadId':other})['thread']['id']==other
        assert any('shared_fixture' in row['tools'] for row in c.rpc('mcpServerStatus/list',{'threadId':sid,'serverName':'shared_fixture'})['data'])
        for name in ('a','b'):
            assert (root/'accounts'/name/'auth.json').read_text()=='{}'
            assert (root/'accounts'/name/'config.toml').resolve()==(common/'config.toml').resolve()
        assert set(b.rpc('thread/loaded/list',{})['data'])=={sid,other}

        print('PASS: native proxy, two chats, reconnect, combined history and shared MCP tools after injected quota failover; separate credentials, no model requests.')
    finally:
        for c in clients:c.close()
        server.terminate()
        try:server.wait(timeout=45)
        except subprocess.TimeoutExpired:server.kill();server.wait()
        logfile.seek(0)
        if server.returncode:print(logfile.read())
        logfile.close()
