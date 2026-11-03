# Still-camera controls

Lumia Agent 0.1.12 and bridge API 0.4 expose native Windows Phone camera controls through `POST /v1/preview` and `POST /v1/captures`. Fetch `GET /v1/capabilities` first. It reports each sensor's supported controls, ranges, units, choices and autofocus support. Reload `/docs` after the phone connects: the live OpenAPI schema includes controls the phone actually reports. An offline schema cannot enumerate a future device's capabilities.

Controls are per request. The app reads the current native values, applies overrides, reads back applied values, and restores the baseline after acquisition. Omit `controls` or use `{}` for the baseline. For nullable controls, `null` explicitly selects automatic operation. Unsupported controls, invalid types and out-of-range values fail before queuing. A native setter failure becomes a job error. A restore failure closes the camera so the next request opens a clean device.

## Focus

Still capture defaults to `focus: true`; preview defaults to `false`. A focus request resets the previous scan, selects a supported range, checks the native lock result, retries once if necessary, and keeps focus locked through acquisition. Failure becomes a job error instead of a successful-looking image. `focus_status`, `focus_attempts`, `focus_range` and `supported_focus_ranges` are recorded with the image. An autofocus lock is the device's report, not a guarantee of optical sharpness.

`focus_range: "auto"` prefers `normal` for ordinary scenes, then the device's other available range. The tested rear camera reports `normal`, `macro`, `full`, `infinity` and `hyperfocal`. The front camera has fixed focus.

For a focused preview of the central part of a scene:

```json
{
  "camera": "rear",
  "focus": true,
  "focus_range": "normal",
  "focus_region": {"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5}
}
```

The focus rectangle uses normalized **unrotated preview** coordinates, with a top-left origin and each axis in 0..1. The app converts these to native preview pixels and reapplies the region after resetting focus. These are different from original JPEG crop coordinates and the phone's rotated UI coordinates. Omit the rectangle for native default metering. A region requires `focus: true` and native region support.

For a chosen lens position, use `focus: false` and `controls: {"manual_focus_position": 500}`. Position units are device-specific, not metres. Skipping explicit autofocus alone does not pin the lens at a chosen distance. Manual focus results report `focus_status: "manual"`.

## Available native controls

The adapter covers these standard native properties. Capability reports determine whether each is usable on a particular sensor.

| JSON control | Meaning |
| --- | --- |
| `iso` | ISO sensitivity; `null` selects auto |
| `exposure_time_us` | Shutter time in microseconds; `null` selects auto |
| `exposure_compensation` | Steps of 1/6 EV; `6` is +1 EV |
| `white_balance_preset` | Native white-balance choice; `null` selects auto |
| `white_balance_kelvin` | Temperature, when supported; `null` selects auto |
| `scene_mode` | Native scene choice |
| `flash_mode` | Native flash choice |
| `flash_power` | Native power units, when adjustable |
| `focus_illumination_mode` | Focus-assist light choice |
| `manual_focus_position` | Native lens position; requires `focus: false` |
| `auto_lock` | Bit flags: focus=1, exposure=2, white balance=4 |
| `encode_orientation_degrees` | Native encoding rotation; may swap JPEG width/height |
| `capture_orientation_degrees` | Native capture-orientation hint |
| `shutter_sound` | Sound enabled/disabled, subject to native regional requirements |

Use numeric choice values from the report; labels appear in Swagger's schema descriptions. For white balance, choose either a temperature or a preset. The app keeps the focus-lock bit set while acquiring an explicitly focused or manually positioned image, so the read-back `auto_lock` can include that bit.

The tested RM-875 reports twelve adjustable controls on the rear sensor. Its ISO range is 100–4000, shutter range is 60–4,000,000 microseconds, compensation is -18..18, and lens position is 0..1000. The front sensor has ISO 100–1600 and shutter 60–133,000 microseconds; it does not support manual focus. Kelvin white balance and flash power return fixed 0..0 sentinels on this firmware and are omitted from the live Swagger control fields. Do not assume these limits on another device.

## Manual exposure example

This rear 4:3 capture was checked on hardware, including ISO and shutter values from the original JPEG's EXIF:

```json
{
  "camera": "rear",
  "aspect": "4:3",
  "focus": true,
  "focus_range": "normal",
  "controls": {"iso": 3200, "exposure_time_us": 16667, "flash_mode": 0}
}
```

16667 microseconds is approximately 1/60 second. Pick exposure for the scene; a shorter shutter can reduce motion blur but may need more light or a higher ISO. The job's image metadata contains native `applied_controls` and, for stills with these EXIF tags, actual `iso` and `exposure_seconds`. Preview snapshots generally have no exposure EXIF. Some native properties affect stills only even when accepted on a preview request. Original JPEG bytes remain unchanged.

Encoding rotation is explicit. The bridge does not automatically rotate/mirror JPEGs from EXIF. Base thumbnail and crop coordinates on the returned encoded width and height.

## CLI

```sh
python bridge/lumia_cli.py --url http://PI_HOST:8765 --config agent-config.json capabilities
python bridge/lumia_cli.py --url http://PI_HOST:8765 --config agent-config.json preview --focus --focus-range normal --focus-region 0.25 0.25 0.5 0.5 --out focused.jpg
python bridge/lumia_cli.py --url http://PI_HOST:8765 --config agent-config.json capture --controls-file controls.json --out full.jpg
```

`controls.json` contains only the control object, for example `{"iso": 3200, "exposure_time_us": 16667, "flash_mode": 0}`. Manual lens positioning additionally needs `--no-focus`. The Windows wrapper supports `capabilities`, `-Focus`, `-NoFocus`, `-FocusRange`, `-ControlsFile` and `-FocusRegion`.

Hardware checks covered normal-range autofocus, full-resolution rear capture, a focus rectangle, combined exposure/white-balance/scene settings, both ends of the manual lens range, compensation, front-camera encoding rotation, and a subsequent normal autofocus request after overrides. They do not establish optical accuracy for every value or native property combination. Hardware or lens problems can still limit distant focus.

The native API conventions were cross-checked against Microsoft's [Camera Explorer sample](https://github.com/microsoft/camera-explorer) and the genuine Windows Phone SDK references. No video streaming or RAW/DNG capture is implemented.
