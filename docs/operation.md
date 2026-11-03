# Camera operation

Leave Lumia Agent open in the foreground, connected to the same LAN as the bridge, and externally powered. Moving to Settings or another app releases the camera; tap Connect camera after returning if needed. Reopening the app can reconnect using its saved pairing settings.

## Phone controls

- Portrait and both landscape orientations are supported.
- Show live preview opens the rear camera if none is selected. Later agent commands can select rear/front normally. Hide live preview hides the phone viewfinder without disabling HTTP camera operations.
- OLED protection defaults on. After 30 idle seconds while connected or local preview is enabled, every app pixel is black, including the status-bar area. No wake button, text or icon stays visible.
- Black screen now activates that state immediately. Half/full press of the physical camera button or a tap anywhere wakes the controls. This is an app-owned black screen, not an OS lock; keep the app foregrounded for camera work.

Preview, 38 MP capture and physical wake were verified while the screen was black. Firmware flashing, resetting, or changing the lock screen is not needed for these controls.

## HTTP workflow

All `/v1/*` calls require the agent bearer token. The phone uses the separate device token and session header on `/device/*`.

1. `POST /v1/preview` or `/v1/captures` queues a job and returns HTTP 202.
2. Poll `GET /v1/jobs/ID`. The job becomes done or error.
3. Download `job.image.url` using the same authorization header.
4. For efficient framing, get `/v1/images/IMAGE_ID/thumbnail.jpg?max=1280`.
5. `POST /v1/images/IMAGE_ID/crop` with integer x, y, width and height creates a crop from that retained original.

Coordinates use the encoded JPEG's top-left origin. No endpoint automatically rotates or mirrors pixels based on EXIF. Map thumbnail coordinates to the original dimensions before cropping. UI orientation does not change this coordinate convention.

An explicit `encode_orientation_degrees` control can rotate pixels on the phone before encoding. Use the returned image dimensions for crops. A `focus_region` uses normalized unrotated preview coordinates, which differ from full-resolution JPEG pixel coordinates. See [camera controls](camera-controls.md).

Original captures are retained byte for byte. Crops decode the JPEG and re-encode the selected region at quality 95; they are not lossless JPEG bitstream crops. Preview uses a smaller viewfinder buffer. Front stills use that camera's enumerated maximum; rear stills explicitly request the documented 1020 modes.

Jobs expire after 180 seconds, with a queue bound of 16. A new phone session cancels outstanding work. After an error or reconnect, submit a fresh job; old jobs are not silently replayed. Completed records remain in memory for up to an hour. Original image data survives bridge restarts.

## Browser and CLI

Swagger UI is at `/docs` (also `/` and `/swagger`); OpenAPI is `/openapi.json`. Use a modern browser on another device. Paste agent_token into Authorize; Swagger does not persist it across page reloads or send the spec to an external validator.

The CLI reads its credential from `LUMIA_AGENT_TOKEN` or a private config file. It prints image IDs, real dimensions and local JPEG paths. An AI agent needs to open the file with its vision tool after downloading it.

## Limits

No video streaming, RAW/DNG or ordinary background camera service is implemented. Native still-camera controls are exposed when reported as supported by the phone. The 41 MP sensor marketing figure is not a promise of a rectangular 41 MP JPEG. Lighting, focus and hand motion still determine useful image detail. A reported autofocus lock does not guarantee a sharp image.

Factory-reset recovery and hardware restoration are untested. This repository deliberately excludes phone backups, identifiers, firmware, private logs and real camera samples.
