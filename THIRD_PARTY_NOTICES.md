# Third-party notices

The root MIT license applies to this project's original code, not to third-party components.

## Swagger UI

`bridge/static/swagger/` contains selected assets from `swagger-ui-dist` 5.34.1, published by the [Swagger UI project](https://github.com/swagger-api/swagger-ui).

- The upstream Apache License 2.0 text is preserved in `bridge/static/swagger/LICENSE`.
- The upstream notice is preserved in `bridge/static/swagger/NOTICE`.
- Bundled dependency notices are preserved in `bridge/static/swagger/swagger-ui-bundle.js.LICENSE.txt`.
- Exact source URL, archive integrity, and per-file hashes are recorded in `bridge/static/swagger/provenance.json`.
- `tools/fetch-swagger-ui.py` downloads that pinned archive and verifies its SHA-512 before extracting the selected static assets. It does not run npm or package scripts.

## Microsoft Windows Phone SDK

No Microsoft SDK assemblies, USB binaries, drivers, installers, or firmware are included. Build/setup scripts operate on locally obtained Microsoft components, which remain subject to their original license terms. This project's MIT license does not grant rights to those components.

## Python dependencies

Pillow is installed separately from the pinned requirements file; its upstream license applies. Dependency packages are not vendored here.
