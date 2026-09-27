"""Loopback-only browser UI; stdlib HTTP + a single background parsing process."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import multiprocessing as mp
from pathlib import Path
import queue
import secrets
import shutil
import socket
import threading
import time
from urllib.parse import parse_qs, urlsplit, quote
import uuid
import urllib.request
import webbrowser

from tasks import ROOT, worker


class State:
    def __init__(self):
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.requests, self.results = mp.Queue(), mp.Queue()
        self.process = mp.Process(target=worker, args=(self.requests, self.results), daemon=True)
        self.process.start()
        self.job = None
        self.folder = None
        self.source = None
        self.meta = None
        self.revision = None
        self.downloads = {}
        self.jobs = {}
        threading.Thread(target=self.collect, daemon=True).start()

    def collect(self):
        while True:
            try:
                kind, value = self.results.get(timeout=.5)
            except queue.Empty:
                if self.process.is_alive():
                    continue
                with self.lock:
                    if self.job and self.job['status'] == 'running':
                        self.job.update(status='error', error='后台进程已退出，请重启服务')
                return
            with self.lock:
                job = self.job
                if kind == 'progress':
                    job['message'] = value
                    continue
                if kind == 'error':
                    job.update(status='error', error=value)
                    continue
                if job['action'] == 'open':
                    self.folder, self.meta = value
                    self.source = job['source']
                    self.revision = uuid.uuid4().hex
                    value = self.snapshot()
                elif job['action'] == 'export':
                    key = uuid.uuid4().hex
                    self.downloads[key] = Path(value)
                    value = {'path': value, 'url': '/api/download?id=' + key}
                job.update(status='done', result=value, elapsed=time.monotonic()-job['started'])

    def snapshot(self):
        return {'revision': self.revision, 'source': self.source, 'meta': self.meta}

    def start(self, body):
        with self.lock:
            if not self.process.is_alive():
                raise ValueError('后台进程已退出，请重启服务')
            if self.job and self.job['status'] == 'running':
                raise ValueError('另一个后台任务正在运行，请稍后再试')
            action = body.get('action')
            if action == 'open':
                source = Path(body['path']).resolve()
                if not str(source).lower().endswith(('.xml', '.xml.gz')) or not source.is_file():
                    raise ValueError('请选择存在的 .xml 或 .xml.gz 存档')
                args = (str(source),)
            else:
                if not self.folder or body.get('revision') != self.revision:
                    raise ValueError('当前存档已变化，请重新打开或刷新页面')
                if action == 'query':
                    args = (self.folder, body.get('mode', 'children'), body.get('value', 0), int(body.get('after', 0)))
                elif action == 'details':
                    args = (self.folder, int(body['node']))
                elif action == 'tags':
                    args = (self.folder,)
                elif action == 'export':
                    changes = body.get('changes', {})
                    if not isinstance(changes, dict) or any(not isinstance(v, dict) or any(not isinstance(x, str) for x in v.values()) for v in changes.values()):
                        raise ValueError('修改清单格式错误')
                    name = str(body.get('name', 'edited.xml.gz'))
                    if Path(name).name != name or any(c in name for c in '/\\:') or not name.lower().endswith(('.xml', '.xml.gz')):
                        raise ValueError('导出名称必须为 .xml 或 .xml.gz 文件名')
                    dest = ROOT / '.local' / 'exports' / uuid.uuid4().hex / name
                    dest.parent.mkdir(parents=True)
                    args = (self.folder, changes, str(dest))
                else:
                    raise ValueError('未知任务')
            job = dict(id=uuid.uuid4().hex, action=action, status='running', message='任务已开始', started=time.monotonic())
            if action == 'open':
                job['source'] = str(source)
            # Keep bounded recent results for clients polling quickly completed tasks.
            if len(self.jobs) >= 32:
                self.jobs.pop(next(iter(self.jobs)))
            self.jobs[job['id']] = self.job = job
            self.requests.put((action, args))
            return job['id']

    def close(self):
        self.process.terminate()
        self.process.join(2)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Do not log local paths, attributes, or access tokens.

    def send_bytes(self, data, content_type, status=200):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(data)

    def json(self, data, status=200):
        self.send_bytes(json.dumps(data, ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8', status)

    def allowed(self, token=False):
        port = self.server.server_address[1]
        host = f'127.0.0.1:{port}'
        origin = self.headers.get('Origin')
        if self.headers.get('Host') != host or (origin and origin != 'http://' + host):
            self.json({'error': '仅允许本机同源访问'}, 403)
            return False
        if token and not secrets.compare_digest(self.headers.get('X-X4-Token', ''), self.server.state.token):
            self.json({'error': '页面会话已过期，请刷新'}, 403)
            return False
        return True

    def do_GET(self):
        if not self.allowed():
            return
        parsed = urlsplit(self.path)
        params = parse_qs(parsed.query)
        state = self.server.state
        if parsed.path == '/api/session':
            with state.lock:
                self.json({'app': 'X4SaveEditor', 'token': state.token, **state.snapshot()})
        elif parsed.path == '/api/job':
            if not self.allowed(token=True):
                return
            with state.lock:
                job = state.jobs.get(params.get('id', [''])[0])
                self.json(job or {'error': '任务不存在'}, 200 if job else 404)
        elif parsed.path == '/api/saves':
            if not self.allowed(token=True):
                return
            root = Path.home() / 'Documents' / 'Egosoft' / 'X4'
            paths = list(root.glob('*/save/*.xml')) + list(root.glob('*/save/*.xml.gz'))
            rows = [{'path': str(p), 'name': p.name, 'bytes': p.stat().st_size, 'mtime': p.stat().st_mtime} for p in paths if p.is_file()]
            self.json(sorted(rows, key=lambda r: r['mtime'], reverse=True))
        elif parsed.path == '/api/download':
            # Unpredictable per-export capability; no user-controlled filesystem path.
            with state.lock:
                path = state.downloads.get(params.get('id', [''])[0])
            if not path or not path.is_file():
                self.json({'error': '导出文件不存在'}, 404)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(path.stat().st_size))
            self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + quote(path.name))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            with path.open('rb') as f:
                shutil.copyfileobj(f, self.wfile, 1024*1024)
        elif parsed.path in ('/', '/app.js', '/style.css'):
            name = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}[parsed.path]
            mime = {'index.html': 'text/html; charset=utf-8', 'app.js': 'text/javascript; charset=utf-8', 'style.css': 'text/css; charset=utf-8'}[name]
            self.send_bytes((ROOT / 'web' / name).read_bytes(), mime)
        else:
            self.json({'error': 'Not found'}, 404)

    def do_POST(self):
        if not self.allowed(token=True):
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            parsed = urlsplit(self.path)
            if parsed.path == '/api/upload':
                if length <= 0 or length > 8*1024**3:
                    raise ValueError('文件为空或超过 8 GiB')
                name = parse_qs(parsed.query).get('name', ['save.xml.gz'])[0]
                if Path(name).name != name or any(c in name for c in '/\\:') or not name.lower().endswith(('.xml', '.xml.gz')):
                    raise ValueError('请选择 .xml 或 .xml.gz')
                path = ROOT / '.local' / 'imports' / uuid.uuid4().hex / name
                path.parent.mkdir(parents=True)
                self.connection.settimeout(120)
                try:
                    with path.open('xb') as f:
                        remaining = length
                        while remaining:
                            data = self.rfile.read(min(1024*1024, remaining))
                            if not data:
                                raise ValueError('文件传输中断')
                            f.write(data)
                            remaining -= len(data)
                except Exception:
                    path.unlink(missing_ok=True)
                    raise
                self.json({'path': str(path)})
            elif parsed.path == '/api/jobs':
                if length <= 0 or length > 4*1024*1024:
                    raise ValueError('请求大小不正确')
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError('请求格式错误')
                self.json({'id': self.server.state.start(body)}, 202)
            else:
                self.json({'error': 'Not found'}, 404)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            self.json({'error': str(exc)}, 400)


class LocalHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        # Windows SO_REUSEADDR can let two processes listen on the same port.
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def make_server(port=8765):
    server = LocalHTTPServer(('127.0.0.1', port), Handler)
    server.state = State()
    return server


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--no-browser', action='store_true')
    args = ap.parse_args()
    try:
        server = make_server(args.port)
    except OSError:
        url = f'http://127.0.0.1:{args.port}'
        try:
            with urllib.request.urlopen(url + '/api/session', timeout=2) as response:
                existing = json.load(response)
            if existing.get('app') != 'X4SaveEditor':
                raise ValueError('Port used by another application')
        except Exception:
            raise SystemExit(f'Port {args.port} is unavailable. Use --port with a different port.')
        if not args.no_browser:
            webbrowser.open(url)
        print(f'X4SaveEditor already running: {url}')
        return
    url = f'http://127.0.0.1:{server.server_address[1]}'
    print(f'X4SaveEditor: {url}\nCtrl+C to stop. Local access only.', flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.state.close()
        server.server_close()


if __name__ == '__main__':
    mp.freeze_support()
    main()
