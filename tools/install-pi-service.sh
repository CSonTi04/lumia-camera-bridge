#!/bin/sh
set -eu
if [ "$(id -u)" -ne 0 ]; then
    echo 'Run with sudo after setup-pi.sh, from /opt/lumia-agent.' >&2
    exit 1
fi
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ "$ROOT" != /opt/lumia-agent ]; then
    echo 'Place the runtime in /opt/lumia-agent before installing its system service.' >&2
    exit 1
fi
id lumia-agent >/dev/null 2>&1 || useradd --system --home-dir /var/lib/lumia-agent --shell /usr/sbin/nologin lumia-agent
install -d -o lumia-agent -g lumia-agent -m 750 /var/lib/lumia-agent
install -d -o root -g lumia-agent -m 750 /etc/lumia-agent
if [ ! -f /etc/lumia-agent/config.json ]; then
    if [ -f "$ROOT/config.json" ]; then
        install -o lumia-agent -g lumia-agent -m 600 "$ROOT/config.json" /etc/lumia-agent/config.json
    else
        "$ROOT/.venv/bin/python" "$ROOT/bridge/lumia_bridge.py" --config /etc/lumia-agent/config.json --init
        chown lumia-agent:lumia-agent /etc/lumia-agent/config.json
    fi
fi
install -m 644 "$ROOT/deploy/lumia-agent.service" /etc/systemd/system/lumia-agent.service
systemctl daemon-reload
systemctl enable --now lumia-agent
systemctl --no-pager --full status lumia-agent
