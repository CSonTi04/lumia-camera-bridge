# Lumia Camera Bridge

Use a Nokia Lumia 1020 as an HTTP camera for AI agents or a browser. A foreground Windows Phone app polls a Raspberry Pi over Wi-Fi; the Pi retains original JPEGs, serves previews, and crops full-resolution images on demand.

The runtime needs the **phone and a Debian/Linux bridge**. Windows is used to build and initially sideload the phone app. No Visual Studio IDE is required for the build.

## Features

- Rear and front camera previews and still capture.
- Actual 7136×5360 rear 4:3 and 7712×4352 rear 16:9 JPEGs on the tested Lumia 1020. Rear stills below 30 MP fail explicitly.
- Original JPEG preservation, thumbnails, and pixel-coordinate crops on the Pi.
- Authenticated HTTP API, OpenAPI definition, local Swagger UI, and an agent CLI.
- Camera-reported controls in Swagger: verified autofocus, focus regions, manual lens position, ISO, shutter time, exposure compensation, white balance, scenes, flash, orientation and shutter sound. See [camera controls](docs/camera-controls.md).
- Portrait and both landscape layouts, with a Show/Hide live viewfinder toggle.
- OLED protection: an entirely black screen after 30 idle seconds. The physical camera button or a tap wakes the controls. Camera requests continue while black.
- Windows C# compiler + genuine WP8 reference assemblies + ZIP packaging, without an old Visual Studio IDE.

Validated on a Lumia 1020 RM-875 running Windows Phone 8.1 Update, OS 8.10.14226.359, with a Raspberry Pi 5 running Debian ARM64. Other models and OS builds are unverified. The phone must already support sideloading; this project does not unlock, reset, or flash it.

| Operation | Verified dimensions |
| --- | --- |
| Rear preview | 1024×768 |
| Rear 4:3 still | 7136×5360, about 38 MP |
| Rear 16:9 still | 7712×4352, about 34 MP |
| Front preview / still | 1024×768 / 1280×960 |
| Crop from a retained rear original | 1600×1600 |

The physical camera, standalone operation with USB disconnected, landscape, preview toggle, OLED blanking, and hardware-button wake were tested. Autofocus, manual lens positions, exposure controls and rotated capture were also checked on hardware. Eighteen HTTP integration tests run with simulated phone uploads.

## Run the bridge

Requires Python 3.11+, Python venv support, and Pillow. On Debian:

```sh
git clone https://github.com/CSonTi04/lumia-camera-bridge.git
cd lumia-camera-bridge
sh tools/setup-pi.sh
.venv/bin/python bridge/lumia_bridge.py --host 0.0.0.0 --config config.json --data data
```

Setup generates separate `agent_token` and `device_token` values in the private `config.json`. Keep that file outside version control. For a boot-starting system service, see [Debian deployment](docs/debian.md).

## Build and pair the phone

See [Windows toolchain and USB deployment](docs/windows-toolchain.md). Build the XAP using locally obtained Microsoft references:

```powershell
.\tools\setup-sdk.ps1
.\tools\build-phone.ps1
```

The SDK download is about 1.72 GB. The extraction script does not execute its installers. Microsoft SDK files are not included in this repository and remain under their original terms. USB connectivity needs separately configured Microsoft SDK transport components; fresh-workstation USB provisioning is not fully automated here.

Once installed, point Lumia Agent at `http://PI_LAN_IP:8765` and enter the Pi's **device_token**. An optional private pairing-file import is described in the Windows guide. Keep the phone on the same LAN, powered, and open in Lumia Agent. It does not need to stay attached to Windows.

## Use without an agent

Open `http://PI_LAN_IP:8765/docs` in a modern browser on another device. Click **Authorize**, paste the **agent_token**, then try `GET /v1/status`.

`GET /v1/capabilities` reports the connected phone's actual controls, choices and sensor-specific limits. The live OpenAPI schema includes supported controls after Lumia Agent reports them; reload Swagger after pairing or a phone update. [Camera-control examples](docs/camera-controls.md) include focus regions and manual exposure.

1. `POST /v1/preview` or `/v1/captures` queues a camera job.
2. Poll `GET /v1/jobs/{id}` until it is done or reports an error.
3. Download the returned image, request a thumbnail, or crop the retained original.

The OpenAPI definition is at `/openapi.json`. Swagger assets are served locally; a CDN or online validator is not required. Opening a browser on the Lumia itself backgrounds the camera app, so use another device for the explorer.

## Agent CLI

Load `agent_token` through a private client config or the `LUMIA_AGENT_TOKEN` environment variable. Do not put it in prompts or command-line arguments.

```sh
python bridge/lumia_cli.py --url http://PI_HOST:8765 --config agent-config.json status
python bridge/lumia_cli.py --url http://PI_HOST:8765 --config agent-config.json capabilities
python bridge/lumia_cli.py --url http://PI_HOST:8765 --config agent-config.json preview --out preview.jpg
python bridge/lumia_cli.py --url http://PI_HOST:8765 --config agent-config.json capture --aspect 4:3 --out full.jpg
python bridge/lumia_cli.py --url http://PI_HOST:8765 --config agent-config.json crop IMAGE_ID 2000 1000 1024 1024 --out detail.jpg
```

The agent must open the downloaded JPEG with its vision tool to see the result. Read [the HTTP contract](openapi.json) and [operating notes](docs/operation.md) for authentication, coordinates, limits, and recovery after a failed job.

## Tests

```sh
python -m pip install -r bridge/requirements.txt
python -m unittest discover -s tests -v
```

These tests cover the HTTP workflow, auth separation, queue limits, JPEG handling, crops, session changes, focus telemetry, capability-driven controls, EXIF exposure metadata and local documentation routes. They do not emulate Lumia hardware.

## License

Project code is [MIT licensed](LICENSE). Vendored Swagger UI and its bundled dependencies retain their own licenses and notices; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
