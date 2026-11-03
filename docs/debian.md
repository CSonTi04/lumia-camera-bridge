# Debian deployment

The bridge was tested on Debian ARM64 on a Raspberry Pi 5. Install Python 3.11+, `python3-venv`, `python3-pip`, and Git using your OS package manager.

For a system service, put a checkout or source/runtime bundle in `/opt/lumia-agent`, then run:

```sh
cd /opt/lumia-agent
sh tools/setup-pi.sh
sudo sh tools/install-pi-service.sh
sudo systemctl status lumia-agent
```

Setup creates a venv, installs Pillow, runs HTTP tests, and generates a private config if one does not exist. The service installer creates the `lumia-agent` system user and enables startup at boot. It does not replace an existing service config.

| Item | Location |
| --- | --- |
| Source and venv | `/opt/lumia-agent` |
| Service config | `/etc/lumia-agent/config.json` |
| Images and metadata | `/var/lib/lumia-agent` |
| Service | `lumia-agent.service` |
| HTTP port | `8765` |

The config contains separate `agent_token` and `device_token` values. Provide the device credential only to the Lumia app and the agent credential to API clients. Keep local copies private. The phone needs the Pi's LAN address; a tailnet-only address does not give an old Windows Phone a Tailscale client.

## Local agent command

To install a client for your ordinary Linux user, from the configured Pi:

```sh
sudo python3 /opt/lumia-agent/tools/install-agent-client.py --user "$(id -un)"
~/.local/bin/lumia-camera status
~/.local/bin/lumia-camera preview --out ~/lumia-preview.jpg
```

This creates `~/.local/bin/lumia-camera` and a mode-0600 profile at `~/.config/lumia-agent/agent-config.json`. It copies only agent_token into that profile, never device_token.

For a foreground process instead of a service:

```sh
.venv/bin/python bridge/lumia_bridge.py --host 0.0.0.0 --config config.json --data data
```

Browser explorer: `http://PI_LAN_IP:8765/docs`. Health: `/healthz`. OpenAPI: `/openapi.json`.

The phone link uses bearer-authenticated HTTP on the private LAN. Keep port 8765 off the public Internet; use a private network or encrypted tailnet for remote agent access. The local Swagger UI does not contact a CDN or external validator.

Images remain until the operator removes them. Config and image data survive service restarts, while job records and phone sessions are held in memory. After restarting the bridge, the phone retries registration automatically.
