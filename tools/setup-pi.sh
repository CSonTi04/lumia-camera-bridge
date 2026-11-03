#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
python3 -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ required"'
if ! python3 -m venv .venv; then
    echo 'Install Debian prerequisites: sudo apt-get install python3-venv python3-pip' >&2
    exit 1
fi
.venv/bin/python -m pip install -r bridge/requirements.txt
if [ ! -f config.json ]; then
    .venv/bin/python bridge/lumia_bridge.py --config config.json --init
fi
.venv/bin/python -m unittest discover -s tests -v
echo 'Ready. Start with: .venv/bin/python bridge/lumia_bridge.py --host 0.0.0.0'
echo 'Pair the phone using device_token from config.json and the Pi LAN IP.'
