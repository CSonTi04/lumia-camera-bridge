"""Fetch only pinned Swagger UI browser assets; never run npm/package scripts."""
import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile
from urllib.request import urlopen

VERSION = '5.34.1'
URL = 'https://registry.npmjs.org/swagger-ui-dist/-/swagger-ui-dist-5.34.1.tgz'
INTEGRITY = 'VSr8fXfI93obYaQicLJbLUKGRxDojj/SfRJDDLCioGTUBj4BK/Nj4eE9jCeCAnJxVLi7iS+08PbiZLyrQKBkJQ=='
root = Path(__file__).resolve().parents[1] / 'bridge' / 'static' / 'swagger'
with urlopen(URL, timeout=60) as response:
    payload = response.read()
if base64.b64encode(hashlib.sha512(payload).digest()).decode() != INTEGRITY:
    raise SystemExit('Swagger UI archive integrity mismatch.')
root.mkdir(parents=True, exist_ok=True)
assets = {}
with tarfile.open(fileobj=io.BytesIO(payload), mode='r:gz') as archive:
    for name in ('swagger-ui.css', 'swagger-ui-bundle.js', 'LICENSE', 'NOTICE', 'swagger-ui-bundle.js.LICENSE.txt'):
        try:
            member = archive.getmember('package/' + name)
        except KeyError:
            if name in ('NOTICE', 'swagger-ui-bundle.js.LICENSE.txt'):
                continue
            raise
        if not member.isfile():
            raise SystemExit('Expected a regular upstream asset.')
        data = archive.extractfile(member).read()
        (root / name).write_bytes(data)
        assets[name] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
(root / 'provenance.json').write_text(json.dumps(dict(package='swagger-ui-dist', version=VERSION, source=URL, integrity='sha512-' + INTEGRITY, assets=assets), indent=2) + '\n')
print(json.dumps(dict(version=VERSION, assets={name: meta['bytes'] for name, meta in assets.items()})))
