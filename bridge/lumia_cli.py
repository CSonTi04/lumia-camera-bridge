"""Small agent-facing client. Credentials are read from env or the local config."""
import argparse
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default=os.getenv('LUMIA_URL', 'http://127.0.0.1:8765'))
    parser.add_argument('--config', default='config.json')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status')
    for name in ('preview', 'capture'):
        cmd = commands.add_parser(name)
        cmd.add_argument('--camera', choices=['rear', 'front'], default='rear')
        cmd.add_argument('--aspect', choices=['4:3', '16:9', 'maximum'], default='4:3')
        cmd.add_argument('--no-focus', action='store_true')
        cmd.add_argument('--out', required=True, type=Path)
    cmd = commands.add_parser('crop')
    cmd.add_argument('image_id')
    for name in ('x', 'y', 'width', 'height'):
        cmd.add_argument(name, type=int)
    cmd.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    token = os.getenv('LUMIA_AGENT_TOKEN')
    if not token:
        token = json.loads(Path(args.config).read_text('utf-8'))['agent_token']
    def request(path, payload=None, binary=False):
        data = None if payload is None else json.dumps(payload).encode()
        req = Request(args.url.rstrip('/') + path, data=data, headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        try:
            with urlopen(req, timeout=30) as response:
                content = response.read()
                return content if binary else json.loads(content)
        except HTTPError as error:
            raise SystemExit('HTTP %s: %s' % (error.code, error.read().decode()))
    if args.command == 'status':
        print(json.dumps(request('/v1/status'), indent=2))
        return
    if args.command == 'crop':
        image = request('/v1/images/' + args.image_id + '/crop', {k: getattr(args, k) for k in ('x', 'y', 'width', 'height')})
    else:
        job = request('/v1/preview' if args.command == 'preview' else '/v1/captures',
                      dict(camera=args.camera, aspect=args.aspect, focus=args.command == 'capture' and not args.no_focus))
        deadline = time.monotonic() + 190
        while job['status'] in ('queued', 'running'):
            if time.monotonic() > deadline:
                raise SystemExit('Timed out waiting for camera job ' + job['id'])
            time.sleep(0.25)
            job = request('/v1/jobs/' + job['id'])
        if job['status'] != 'done':
            raise SystemExit(json.dumps(job))
        image = job['image']
    content = request(image['url'], binary=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(content)
    print(json.dumps(dict(image=image, local_file=str(args.out.resolve())), indent=2))


if __name__ == '__main__':
    main()
