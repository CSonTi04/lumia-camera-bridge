# Working on Lumia Camera Bridge

- Read README.md and docs/operation.md before changing behavior. Runtime is Debian/Linux; Windows is the phone build/deploy workstation.
- Phone code targets Windows Phone 8.0 Silverlight on WP8.1, using C# 5. Build with tools/build-phone.ps1 and legally obtained SDK references. Preserve the required AppManifest.xaml filename and raw XAML stream resources.
- Keep full-resolution JPEGs encoded on the phone. Decode/crop on the bridge. Never present a 5 MP fallback as a full-resolution 1020 still.
- Coordinates refer to unrotated encoded JPEG pixels. Keep thumbnail, crop and original coordinate conventions consistent.
- Validate HTTP behavior with `python -m unittest discover -s tests -v`. Simulated tests do not prove device behavior; describe hardware validation separately.
- Keep agent and device credentials separate. Never commit configuration files, photos, logs, phone identifiers, firmware, SDK caches or backups. Do not embed credentials in XAPs or browser pages.
- Ordinary builds and deployment never authorize phone resets, flashing, bootloader/root changes, or photo deletion.
- Local viewfinder and OLED controls must not disable agent camera requests. The black OLED screen must contain no visible text or wake target.
- Swagger UI is vendored with pinned integrity and upstream notices. Preserve its licenses; do not send local specs or credentials to an external validator.
