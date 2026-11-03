"""Lumia camera bridge: Python 3.11+, Pillow, no web framework. See README.md."""
import argparse
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import io
import json
import logging
from pathlib import Path
import re
import secrets
import threading
import time
from urllib.parse import parse_qs, urlsplit
from PIL import Image
from camera_controls import applied_metadata, clean_capabilities, openapi_with_controls, validate_request, wire_controls, wire_region

Image.MAX_IMAGE_PIXELS = 50_000_000
MAX_JPEG = 40 * 1024 * 1024
ID = r'[a-f0-9]{32}'
FOCUS_RANGES = ('auto', 'normal', 'macro', 'full', 'infinity', 'hyperfocal')
ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'bridge' / 'static'
DOC_ASSETS = {
    '/static/swagger-init.js': ('swagger-init.js', 'application/javascript; charset=utf-8'),
    '/static/swagger/swagger-ui.css': ('swagger/swagger-ui.css', 'text/css; charset=utf-8'),
    '/static/swagger/swagger-ui-bundle.js': ('swagger/swagger-ui-bundle.js', 'application/javascript; charset=utf-8'),
    '/static/swagger/LICENSE': ('swagger/LICENSE', 'text/plain; charset=utf-8'),
    '/static/swagger/NOTICE': ('swagger/NOTICE', 'text/plain; charset=utf-8'),
    '/static/swagger/swagger-ui-bundle.js.LICENSE.txt': ('swagger/swagger-ui-bundle.js.LICENSE.txt', 'text/plain; charset=utf-8'),
}


class APIError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class State:
    def __init__(self, data, config):
        self.data = Path(data)
        self.data.mkdir(parents=True, exist_ok=True)
        self.config = config
        self.jobs, self.images, self.pending = {}, {}, deque()
        self.condition = threading.Condition()
        self.processing = threading.Semaphore(1)  # Bound RAM on the Pi.
        self.last_seen, self.device = 0, None
        self.session = None
        self.capabilities = None
        for path in self.data.glob('*.json'):
            item = json.loads(path.read_text('utf-8'))
            if re.fullmatch(ID, item.get('id', '')) and (self.data / (item['id'] + '.jpg')).exists():
                self.images[item['id']] = item

    def expire(self):
        now = time.monotonic()
        for job in self.jobs.values():
            if job['status'] in ('queued', 'running') and now > job['_deadline']:
                job.update(status='error', error='Phone did not finish before the 180 second deadline.')
        self.pending = deque(key for key in self.pending if self.jobs[key]['status'] == 'queued')
        # Keep completed job records bounded. Image metadata remains persisted.
        for key in list(self.jobs):
            if now - self.jobs[key]['_created'] > 3600 and self.jobs[key]['status'] in ('done', 'error'):
                del self.jobs[key]

    def public_job(self, job):
        return {k: v for k, v in job.items() if not k.startswith('_')}

    def connected(self):
        return bool(self.device) and time.monotonic() - self.last_seen < 45

    def add_job(self, kind, params):
        camera = params.get('camera', 'rear')
        aspect = params.get('aspect', '4:3')
        focus = params.get('focus', kind == 'capture')
        focus_range = params.get('focus_range', 'auto')
        if camera not in ('rear', 'front') or aspect not in ('4:3', '16:9', 'maximum') or type(focus) is not bool:
            raise APIError(400, 'camera: rear/front; aspect: 4:3/16:9/maximum; focus: boolean')
        if focus_range not in FOCUS_RANGES:
            raise APIError(400, 'focus_range: auto/normal/macro/full/infinity/hyperfocal')
        if focus_range != 'auto' and (not focus or camera != 'rear'):
            raise APIError(400, 'An explicit focus_range requires focus=true and the rear camera')
        with self.condition:
            self.expire()
            if not self.connected():
                raise APIError(503, 'No phone connected. Open Lumia Agent and connect to this bridge.')
            if focus_range != 'auto' and self.device.get('protocol_version', 1) < 2:
                raise APIError(409, 'Explicit focus ranges require Lumia Agent 0.1.8 or later')
            try:
                controls, region = validate_request(params, camera, focus, self.device.get('protocol_version', 1), self.capabilities)
            except ValueError as error:
                raise APIError(400, str(error)) from error
            if sum(j['status'] in ('queued', 'running') for j in self.jobs.values()) >= 16:
                raise APIError(429, 'Camera queue is full.')
            key = secrets.token_hex(16)
            now = time.monotonic()
            job = dict(id=key, kind=kind, camera=camera, aspect=aspect, focus=focus, focus_range=focus_range, controls=controls, focus_region=region,
                       status='queued', _created=now, _deadline=now + 180)
            self.jobs[key] = job
            self.pending.append(key)
            self.condition.notify_all()
            return self.public_job(job)

    def store(self, data, kind, extra=None):
        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.format != 'JPEG' or image.width * image.height > 50_000_000:
                    raise ValueError('Expected JPEG with at most 50 million pixels')
                width, height = image.size
                orientation = image.getexif().get(274, 1)
                exposure = {}
                try:
                    exif = image.getexif()
                    tags = {**dict(exif), **(exif.get_ifd(34665) if 34665 in exif else {})}
                    if 33434 in tags:
                        value = float(tags[33434])
                        if 0 < value < 3600:
                            exposure['exposure_seconds'] = value
                    if 34855 in tags:
                        value = int(tags[34855])
                        if 0 < value < 10_000_000:
                            exposure['iso'] = value
                except (ValueError, TypeError, OverflowError, ZeroDivisionError):
                    pass
                image.verify()
        except Exception as exc:
            raise APIError(400, 'Invalid JPEG: ' + str(exc)) from exc
        key = secrets.token_hex(16)
        meta = dict(id=key, kind=kind, width=width, height=height, exif_orientation=orientation,
                    coordinates='encoded JPEG pixels, top-left origin; no automatic rotation',
                    bytes=len(data), created_at=datetime.now(timezone.utc).isoformat(),
                    url='/v1/images/' + key + '.jpg')
        if extra:
            meta.update(extra)
        meta.update(exposure)
        target = self.data / (key + '.jpg')
        target.with_suffix('.tmp').write_bytes(data)
        target.with_suffix('.tmp').replace(target)
        metadata = self.data / (key + '.json')
        metadata.with_suffix('.tmp').write_text(json.dumps(meta), 'utf-8')
        metadata.with_suffix('.tmp').replace(metadata)
        self.images[key] = meta
        return meta


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, address, state):
        self.state = state
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'LumiaBridge/0.4'

    def setup(self):
        super().setup()
        self.connection.settimeout(30)

    def log_message(self, fmt, *args):
        logging.info('%s %s', self.client_address[0], fmt % args)

    def send(self, status, payload, content_type='application/json'):
        if content_type == 'application/json':
            payload = json.dumps(payload).encode()
        if isinstance(payload, str):
            payload = payload.encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.end_headers()
        self.wfile.write(payload)

    def body(self, limit=16384):
        if self.headers.get('Transfer-Encoding'):
            raise APIError(400, 'Send Content-Length; chunked requests are unsupported.')
        try:
            size = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            raise APIError(400, 'Invalid Content-Length')
        if not 0 <= size <= limit:
            raise APIError(413, 'Body too large')
        data = self.rfile.read(size)
        if len(data) != size:
            raise APIError(400, 'Incomplete body')
        return data

    def json_body(self, limit=16384):
        try:
            result = json.loads(self.body(limit))
        except (ValueError, UnicodeError):
            raise APIError(400, 'Expected JSON object')
        if not isinstance(result, dict):
            raise APIError(400, 'Expected JSON object')
        return result

    def focus_metadata(self):
        status = self.headers.get('X-Camera-Focus-Status')
        if status is None:
            return {}  # Older phone versions do not report focus telemetry.
        attempts = self.headers.get('X-Camera-Focus-Attempts', '0')
        selected = self.headers.get('X-Camera-Focus-Range', 'device_default')
        supported = self.headers.get('X-Camera-Focus-Ranges', '')
        ranges = supported.split(',') if supported else []
        if status not in ('locked', 'manual', 'skipped', 'unsupported') or attempts not in ('0', '1', '2'):
            raise APIError(400, 'Invalid focus result metadata')
        if (status == 'locked') != (attempts in ('1', '2')):
            raise APIError(400, 'Inconsistent focus attempt count')
        if selected not in FOCUS_RANGES[1:] + ('device_default', 'unchanged', 'fixed', 'manual'):
            raise APIError(400, 'Invalid focus range result')
        if len(ranges) > 5 or len(set(ranges)) != len(ranges) or any(item not in FOCUS_RANGES[1:] for item in ranges):
            raise APIError(400, 'Invalid supported focus ranges')
        result = dict(focus_status=status, focus_attempts=int(attempts), focus_range=selected, supported_focus_ranges=ranges)
        applied = self.headers.get('X-Camera-Applied-Controls')
        if applied is not None:
            try:
                if len(applied) > 4096:
                    raise ValueError('Applied controls header too large')
                result['applied_controls'] = applied_metadata(json.loads(applied))
            except (ValueError, TypeError) as error:
                raise APIError(400, 'Invalid applied control metadata') from error
        return result

    def auth(self, role):
        expected = self.server.state.config[role + '_token']
        supplied = self.headers.get('Authorization', '')
        if not hmac.compare_digest(supplied.encode(), ('Bearer ' + expected).encode()):
            raise APIError(401, 'Missing or incorrect bearer token')
        if role == 'device' and self.path != '/device/register':
            if not self.server.state.session or self.headers.get('X-Device-Session') != self.server.state.session:
                raise APIError(409, 'Register this phone session first')

    def do_GET(self):
        self.handle_api('GET')

    def do_POST(self):
        self.handle_api('POST')

    def handle_api(self, method):
        try:
            self.route(method)
        except APIError as exc:
            self.close_connection = True
            self.send(exc.status, dict(error=exc.message))
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True
        except Exception:
            logging.exception('Request failed')
            self.close_connection = True
            self.send(500, dict(error='Internal bridge error; see service log'))

    def route(self, method):
        state = self.server.state
        parsed = urlsplit(self.path)
        path, query = parsed.path, parse_qs(parsed.query)
        if method == 'GET' and path in ('/', '/docs', '/docs/', '/swagger'):
            return self.send(200, (STATIC / 'docs.html').read_bytes(), 'text/html; charset=utf-8')
        if method == 'GET' and path == '/openapi.json':
            with state.condition:
                capabilities = state.capabilities
            return self.send(200, openapi_with_controls(json.loads((ROOT / 'openapi.json').read_text('utf-8-sig')), capabilities))
        if method == 'GET' and path in DOC_ASSETS:
            relative, content_type = DOC_ASSETS[path]
            return self.send(200, (STATIC / relative).read_bytes(), content_type)
        if method == 'GET' and path == '/healthz':
            return self.send(200, dict(service='lumia-bridge', version='0.4'))
        self.auth('device' if path.startswith('/device/') else 'agent')
        if method == 'GET' and path == '/v1/capabilities':
            with state.condition:
                result = dict(ready=state.capabilities is not None, connected=state.connected(), device=state.device,
                              cameras=state.capabilities['cameras'] if state.capabilities else [])
            return self.send(200, result)
        if method == 'GET' and path == '/v1/status':
            with state.condition:
                state.expire()
                result = dict(connected=state.connected(), device=state.device,
                              images=len(state.images), jobs=[state.public_job(j) for j in state.jobs.values()])
            return self.send(200, result)
        if method == 'POST' and path in ('/v1/preview', '/v1/captures'):
            return self.send(202, state.add_job('preview' if path.endswith('preview') else 'capture', self.json_body()))
        match = re.fullmatch('/v1/jobs/(' + ID + ')', path)
        if method == 'GET' and match:
            with state.condition:
                state.expire()
                job = state.jobs.get(match[1])
                if not job:
                    raise APIError(404, 'Unknown job')
                result = state.public_job(job)
            return self.send(200, result)
        match = re.fullmatch('/v1/images/(' + ID + r')(\.jpg|/thumbnail\.jpg|/crop)', path)
        if match:
            key, action = match.groups()
            meta = state.images.get(key)
            if not meta:
                raise APIError(404, 'Unknown image')
            image_path = state.data / (key + '.jpg')
            if method == 'GET' and action == '.jpg':
                return self.send(200, image_path.read_bytes(), 'image/jpeg')
            if method == 'GET' and action == '/thumbnail.jpg':
                try:
                    maximum = int(query.get('max', ['1280'])[0])
                except ValueError:
                    raise APIError(400, 'max must be an integer')
                if not 64 <= maximum <= 4096:
                    raise APIError(400, 'max must be between 64 and 4096')
                with state.processing, Image.open(image_path) as image:
                    image.draft('RGB', (maximum, maximum))
                    image.thumbnail((maximum, maximum))
                    output = io.BytesIO()
                    image.convert('RGB').save(output, 'JPEG', quality=85)
                return self.send(200, output.getvalue(), 'image/jpeg')
            if method == 'POST' and action == '/crop':
                params = self.json_body()
                values = [params.get(k) for k in ('x', 'y', 'width', 'height')]
                if any(type(v) is not int for v in values):
                    raise APIError(400, 'x, y, width, height must be integer pixels')
                x, y, w, h = values
                if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > meta['width'] or y + h > meta['height']:
                    raise APIError(400, 'Crop is outside source image')
                with state.processing, Image.open(image_path) as image:
                    output = io.BytesIO()
                    image.crop((x, y, x + w, y + h)).convert('RGB').save(output, 'JPEG', quality=95)
                    crop = state.store(output.getvalue(), 'crop', dict(source_id=key, crop=dict(x=x, y=y, width=w, height=h)))
                return self.send(201, crop)
        if method == 'POST' and path == '/device/register':
            info = self.json_body()
            protocol = info.get('protocol_version', 1)
            if type(protocol) is not int or protocol not in (1, 2, 3):
                raise APIError(400, 'Unsupported phone protocol version')
            with state.condition:
                # A registration starts a new session and invalidates old in-flight work.
                for job in state.jobs.values():
                    if job['status'] in ('queued', 'running'):
                        job.update(status='error', error='Phone session changed; submit a fresh command.')
                state.pending.clear()
                state.session = secrets.token_hex(16)
                state.device = {k: info.get(k) for k in ('model', 'os', 'app_version')}
                state.device['protocol_version'] = protocol
                state.capabilities = None
                state.last_seen = time.monotonic()
                session = state.session
            return self.send(200, session, 'text/plain')
        if method == 'POST' and path == '/device/capabilities':
            report = self.json_body(131072)
            try:
                clean = clean_capabilities(report)
            except ValueError as error:
                raise APIError(400, str(error)) from error
            with state.condition:
                if self.headers.get('X-Device-Session') != state.session:
                    raise APIError(409, 'Session replaced')
                state.capabilities = clean
                state.last_seen = time.monotonic()
            return self.send(200, dict(accepted=True))
        if method == 'GET' and path == '/device/next':
            session = self.headers.get('X-Device-Session')
            with state.condition:
                state.last_seen = time.monotonic()
                deadline = time.monotonic() + 15
                while True:
                    if session != state.session:
                        raise APIError(409, 'Session replaced')
                    state.expire()
                    active = any(j['status'] == 'running' for j in state.jobs.values())
                    if state.pending and not active:
                        job = state.jobs[state.pending.popleft()]
                        job['status'] = 'running'
                        job['_session'] = session
                        command = '\n'.join([job['id'], job['kind'], job['camera'], job['aspect'], str(job['focus']).lower(), job['focus_range'], wire_controls(job['controls']), wire_region(job['focus_region'])])
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        command = ''
                        break
                    state.condition.wait(remaining)
                state.last_seen = time.monotonic()
            return self.send(200, command, 'text/plain')
        match = re.fullmatch('/device/(result|error)/(' + ID + ')', path)
        if method == 'POST' and match:
            action, key = match.groups()
            focus_meta = self.focus_metadata() if action == 'result' else {}
            data = self.body(MAX_JPEG if action == 'result' else 4096)
            with state.condition:
                state.expire()
                job = state.jobs.get(key)
                if not job or job['status'] != 'running' or job.get('_session') != state.session:
                    raise APIError(410, 'Job expired or belongs to an older session')
                if action == 'error':
                    job.update(status='error', error=data.decode('utf-8', 'replace'))
                else:
                    extra = dict(camera=job['camera'], aspect=job['aspect'], **focus_meta)
                    if job['focus_region'] is not None:
                        extra['focus_region'] = job['focus_region']
                    meta = state.store(data, job['kind'], extra)
                    if job['kind'] == 'capture' and job['camera'] == 'rear' and meta['width'] * meta['height'] < 30_000_000:
                        job.update(status='error', error='Rear camera returned less than 30 MP; full-resolution capture is unavailable.', image=meta)
                    else:
                        job.update(status='done', image=meta)
                state.last_seen = time.monotonic()
                state.condition.notify_all()
            return self.send(200, dict(accepted=True))
        raise APIError(404, 'Unknown route')


def init_config(path):
    path = Path(path)
    config = dict(agent_token=secrets.token_urlsafe(32), device_token=secrets.token_urlsafe(32))
    # Exclusive creation prevents accidental credential replacement.
    with path.open('x', encoding='utf-8') as output:
        json.dump(config, output, indent=2)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    print('Created', path, '(contains private pairing credentials)')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='config.json')
    parser.add_argument('--data', default='data')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--init', action='store_true')
    args = parser.parse_args()
    if args.init:
        init_config(args.config)
        return
    config = json.loads(Path(args.config).read_text('utf-8'))
    if any(not isinstance(config.get(k), str) or len(config[k]) < 24 for k in ('agent_token', 'device_token')):
        parser.error('Config needs separate, strong agent_token and device_token values; use --init.')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    server = Server((args.host, args.port), State(args.data, config))
    logging.info('Listening on %s:%s', args.host, server.server_port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
