"""Run after start. Uses a temporary unique workspace, cleans it up in finally."""
import json
from pathlib import Path
import shutil
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
conf = json.loads((ROOT / 'launcher.json').read_text())
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
url = f'http://127.0.0.1:{conf["mcpPort"]}/mcp'
request_id = 0


def rpc(method, params):
    global request_id
    request_id += 1
    request = urllib.request.Request(url, data=json.dumps({'jsonrpc': '2.0', 'id': request_id, 'method': method, 'params': params}).encode(),
                                    headers={'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream', 'MCP-Protocol-Version': '2025-03-26'})
    with opener.open(request, timeout=30) as response:
        body = response.read().decode()
    if body.startswith('event:') or body.startswith('data:'):
        body = next(line[5:].strip() for line in body.splitlines() if line.startswith('data:'))
    message = json.loads(body)
    assert 'error' not in message, message
    return message['result']


def call(name, arguments, error=False):
    result = rpc('tools/call', {'name': name, 'arguments': arguments})
    assert bool(result.get('isError')) == error, result
    text = '\n'.join(item.get('text', '') for item in result.get('content', []))
    try:
        return json.loads(text)
    except ValueError:
        return text


rpc('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'launcher-smoke', 'version': '1.0'}})
tools = {tool['name'] for tool in rpc('tools/list', {})['tools']}
assert {'validate', 'parse', 'inspect', 'listLocalWorkspaces', 'readLocalWorkspace', 'createLocalWorkspace', 'updateLocalWorkspace'} <= tools, tools
ids = call('listLocalWorkspaces', {})
assert 1 in ids and 2 in ids, ids
id = int(time.time() * 1000)
directory = ROOT / 'workspaces' / str(id)
assert not directory.exists()
dsl = (ROOT / 'workspaces/1/workspace.dsl').read_text()
try:
    created = call('createLocalWorkspace', {'workspaceId': id, 'dsl': dsl})
    assert directory.joinpath('workspace.dsl').read_text() == dsl
    current = call('readLocalWorkspace', {'workspaceId': id})
    assert current['sha256'] == created['sha256']
    updated = call('updateLocalWorkspace', {'workspaceId': id, 'dsl': dsl.replace('Sample Web System', 'AI Created System'), 'expectedSha256': current['sha256']})
    assert updated['sha256'] != current['sha256']
    call('updateLocalWorkspace', {'workspaceId': id, 'dsl': dsl, 'expectedSha256': current['sha256']}, error=True)
    call('createLocalWorkspace', {'workspaceId': id, 'dsl': dsl}, error=True)
    for path in ('/', '/workspace/1', '/workspace/2', f'/workspace/{id}'):
        with opener.open(f'http://127.0.0.1:{conf["uiPort"]}{path}', timeout=30) as response:
            assert response.status == 200
            assert "connect-src 'self'" in response.headers.get('Content-Security-Policy', '')
    for workspace_id in (1, 2, id):
        with opener.open(f'http://127.0.0.1:{conf["uiPort"]}/api/workspace/{workspace_id}', timeout=30) as response:
            workspace = json.load(response)
            assert workspace['id'] == workspace_id
            assert len(workspace['model']['softwareSystems']) == 1
            assert workspace['views']['systemContextViews']
            if workspace_id == id:
                assert workspace['name'] == 'AI Created System'
    print('PASS: MCP initialize/list/create/read/update/conflict/duplicate, two sample UIs and new workspace, offline CSP')
finally:
    shutil.rmtree(directory, ignore_errors=True)
