#!/usr/bin/env python3
"""Dependency-free local launcher for Structurizr (Python 3.10+)."""
from __future__ import annotations
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
RUN = ROOT / '.run'
STATE = RUN / 'state.json'
DIST = ROOT / 'dist'


def java():
    home = os.environ.get('JAVA_HOME')
    binary = str(Path(home) / 'bin' / ('java.exe' if os.name == 'nt' else 'java')) if home else shutil.which('java')
    if not binary:
        raise RuntimeError('Install JDK 21+ and set JAVA_HOME.')
    output = subprocess.run([binary, '-version'], capture_output=True, text=True, check=True)
    match = re.search(r'version "(\d+)', output.stderr + output.stdout)
    if not match or int(match[1]) < 21:
        raise RuntimeError('JDK 21+ is required; set JAVA_HOME to that installation.')
    return binary


@contextlib.contextmanager
def lock():
    RUN.mkdir(exist_ok=True)
    with (RUN / 'launcher.lock').open('a+b') as stream:
        stream.seek(0)
        stream.write(b'0')
        stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def state():
    try:
        return json.loads(STATE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def control(action):
    info = state()
    if not info:
        return None
    try:
        with socket.create_connection(('127.0.0.1', info['controlPort']), timeout=3) as client:
            client.sendall(json.dumps({'token': info['token'], 'action': action}).encode() + b'\n')
            return json.loads(client.recv(4096))
    except (OSError, ValueError, KeyError):
        return None


def http_ok(port):
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f'http://127.0.0.1:{port}/', timeout=1) as response:
            return response.status == 200
    except (OSError, ValueError):
        return False


def config():
    conf = json.loads((ROOT / 'launcher.json').read_text(encoding='utf-8'))
    for key in ('uiPort', 'mcpPort'):
        if type(conf[key]) is not int or not 1024 <= conf[key] <= 65535:
            raise RuntimeError(f'{key} must be an integer between 1024 and 65535')
    if conf['uiPort'] == conf['mcpPort']:
        raise RuntimeError('UI and MCP ports must be different')
    return conf


def commands(conf):
    binary = java()
    workspaces = ROOT / 'workspaces'
    common = [binary, '-Dfile.encoding=UTF-8', '-Dserver.address=127.0.0.1']
    return [
        ('ui', common + [f'-Dserver.port={conf["uiPort"]}', '-Dstructurizr.launcher.offline=true',
                        '-Dstructurizr.workspaces=multiple', '-Dstructurizr.network.urls.allowed=(?!)',
                        '-jar', str(DIST / 'structurizr.war'), 'local', str(workspaces)]),
        ('mcp', common + [f'-Dserver.port={conf["mcpPort"]}',
                         f'-Dstructurizr.launcher.workspaces={workspaces}',
                         '-jar', str(DIST / 'structurizr-mcp.war'), '-dsl'])
    ]


def supervise():
    conf = config()
    children = []
    handles = []
    token = secrets.token_hex(32)
    listener = socket.socket()
    try:
        # Check all ports before starting either service.
        for port in (conf['uiPort'], conf['mcpPort']):
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', port))
        listener.bind(('127.0.0.1', 0))
        listener.listen(4)
        listener.settimeout(0.5)
        for name, command in commands(conf):
            log = (ROOT / 'logs' / f'{name}.log').open('ab', buffering=0)
            handles.append(log)
            children.append(subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT))
        info = {'controlPort': listener.getsockname()[1], 'token': token,
                'uiPort': conf['uiPort'], 'mcpPort': conf['mcpPort']}
        temp = RUN / 'state.tmp'
        temp.write_text(json.dumps(info), encoding='utf-8')
        if os.name != 'nt':
            temp.chmod(0o600)
        temp.replace(STATE)
        while all(child.poll() is None for child in children):
            try:
                client, _ = listener.accept()
            except socket.timeout:
                continue
            with client:
                client.settimeout(2)
                try:
                    request = json.loads(client.recv(4096))
                    if not secrets.compare_digest(str(request.get('token', '')), token):
                        continue
                    action = request.get('action')
                    client.sendall(json.dumps({'running': True, 'uiPort': conf['uiPort'], 'mcpPort': conf['mcpPort']}).encode())
                    if action == 'stop':
                        break
                except (OSError, ValueError):
                    continue
        else:
            print('A service exited unexpectedly; stopping both. See ui.log and mcp.log.', flush=True)
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=20)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        listener.close()
        for handle in handles:
            handle.close()
        if (state() or {}).get('token') == token:
            STATE.unlink(missing_ok=True)


def start():
    with lock():
        if control('status'):
            print('Already running. Use status for URLs.')
            return
        conf = config()
        commands(conf)  # validate Java before detaching
        for name in ('structurizr.war', 'structurizr-mcp.war'):
            if not (DIST / name).is_file():
                raise RuntimeError(f'Missing dist/{name}; run build first.')
        (ROOT / 'logs').mkdir(exist_ok=True)
        (ROOT / 'workspaces').mkdir(exist_ok=True)
        flags = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS} if os.name == 'nt' else {'start_new_session': True}
        with (ROOT / 'logs' / 'launcher.log').open('ab', buffering=0) as log:
            process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '_supervise'],
                                       cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, **flags)
        try:
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('Startup failed. See logs/launcher.log, ui.log, mcp.log.')
                if control('status') and http_ok(conf['uiPort']) and http_ok(conf['mcpPort']):
                    print(f'UI : http://127.0.0.1:{conf["uiPort"]}/')
                    print(f'MCP: http://127.0.0.1:{conf["mcpPort"]}/mcp (Streamable HTTP)')
                    return
                time.sleep(0.5)
            raise RuntimeError('Startup timed out. See logs/.')
        except BaseException:
            control('stop')
            try:
                process.wait(timeout=45)
            except subprocess.TimeoutExpired:
                # Do not kill unrelated PIDs or abandon owned Java children.
                print('Supervisor is still shutting down; see logs/launcher.log.', file=sys.stderr)
            raise


def stop():
    with lock():
        if not control('stop'):
            print('Not running (no responding launcher).')
            return
        deadline = time.monotonic() + 50
        while STATE.exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        if STATE.exists():
            raise RuntimeError('Shutdown timed out; inspect logs/launcher.log.')
        print('Stopped UI and MCP. Workspaces are preserved.')


def build(offline=False):
    with lock():
        if control('status'):
            raise RuntimeError('Stop the services before replacing build artifacts.')
        binary = Path(java())
        env = os.environ.copy()
        env['JAVA_HOME'] = str(binary.resolve().parent.parent)
        repo = ROOT / 'structurizr'
        wrapper = repo / ('mvnw.cmd' if os.name == 'nt' else 'mvnw')
        args = [str(wrapper), '-B', '-ntp', '-pl', 'structurizr-application,structurizr-mcp', '-am',
                'package', '-DskipTests', '-Dmaven.javadoc.skip=true', '-Dgpg.skip=true', '-Pexclude-playwright']
        if offline:
            args.append('-o')
        subprocess.run(args, cwd=repo, env=env, check=True)
        DIST.mkdir(exist_ok=True)
        for module, source, target in (
            ('structurizr-application', 'structurizr-1.0.0.war', 'structurizr.war'),
            ('structurizr-mcp', 'structurizr-mcp-1.0.0.war', 'structurizr-mcp.war')):
            shutil.copy2(repo / module / 'target' / source, DIST / (target + '.tmp'))
        for target in ('structurizr.war', 'structurizr-mcp.war'):
            (DIST / (target + '.tmp')).replace(DIST / target)
        manifest = {name: hashlib.sha256((DIST / name).read_bytes()).hexdigest()
                    for name in ('structurizr.war', 'structurizr-mcp.war')}
        (DIST / 'sha256.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        print('Built dist/structurizr.war and dist/structurizr-mcp.war')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'stop', 'status', 'build', '_supervise'])
    parser.add_argument('--offline', action='store_true', help='Build using cached Maven dependencies only')
    args = parser.parse_args()
    try:
        if args.action == 'start': start()
        elif args.action == 'stop': stop()
        elif args.action == 'build': build(args.offline)
        elif args.action == '_supervise': supervise()
        else:
            info = control('status')
            if info:
                print(f'UI: http://127.0.0.1:{info["uiPort"]}/\nMCP: http://127.0.0.1:{info["mcpPort"]}/mcp')
            else:
                print('Stopped')
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
