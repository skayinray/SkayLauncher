# SkayLauncher

SkayLauncher is a desktop launcher for releases published by [skayinray](https://github.com/skayinray) on GitHub. It discovers public repositories that have releases, selects the right asset for the current platform, verifies the download, and manages installed copies.

[![CI](https://github.com/skayinray/SkayLauncher/actions/workflows/ci.yml/badge.svg)](https://github.com/skayinray/SkayLauncher/actions/workflows/ci.yml)
[![Build](https://github.com/skayinray/SkayLauncher/actions/workflows/build.yml/badge.svg)](https://github.com/skayinray/SkayLauncher/actions/workflows/build.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## Features

- Lists public `skayinray` repositories that have at least one release, with optional fork inclusion.
- Chooses Linux AppImage and Windows EXE or ZIP assets from release metadata.
- Downloads release assets over HTTPS with progress reporting and ETag based API caching.
- Verifies SHA-256 checksums and Ed25519 signatures before an asset is installed.
- Installs, launches, reinstalls, updates, and removes apps from a local registry.
- Detects apps installed manually (for example AppImages in `~/Applications`) and offers to launch them.
- Checks for SkayLauncher updates and applies signed updates in packaged builds.
- Runs as a single instance and supports minimize to tray with optional notifications.
- Offers search, filters, patch notes, three themes, and English or Russian interface text.
- Stores all settings, caches, logs, and installed apps under platform specific user directories.

SkayLauncher reads public GitHub REST API data. An optional GitHub token can be entered in settings to raise the API rate limit. The token is stored locally and is never sent anywhere except GitHub.

## Detecting existing installations

On startup and after every GitHub refresh the launcher scans conventional install locations and matches release assets to repositories:

- Linux: `~/Applications`, `~/.local/share/applications`, `~/.local/bin`, `~/bin`, and `/usr/share/applications`. AppImageLauncher file names such as `SkayClearTux-1.5.3.2-x86_64_<hash>.AppImage` are recognised.
- Windows: `%LOCALAPPDATA%\Programs`, Desktop, Program Files, and uninstall registry entries.
- macOS: `/Applications` and `~/Applications` bundles.

Add more directories with `SKAYLAUNCHER_DISCOVERY_DIRS` (a `PATH`-style separator-separated list). Detected apps are marked **FOUND** and can be launched, reinstalled or forgotten. Forgetting an app only removes it from the launcher list; the file on disk is untouched. The window supports custom drag/resize, maximize, and fullscreen with `F11` (`Esc` exits fullscreen).

## Download performance

Release assets are fetched over HTTPS. Files larger than 8 MiB are downloaded through up to eight parallel HTTP byte-range requests when the server supports them, which avoids the low per-connection throughput common with GitHub release CDN routes. If a range request fails, the launcher falls back to a single stream. GitHub API responses for individual repositories are also fetched in parallel.

Set `SKAYLAUNCHER_DOWNLOAD_SEGMENTS=1` to disable parallel downloads (useful with proxies that reject range requests). Partial files are removed on failure; downloads are verified with `SHA256SUMS` and the Ed25519 signature after assembly.

## Install from a release

Download the asset for your platform from [Releases](https://github.com/skayinray/SkayLauncher/releases).

### Linux AppImage

```sh
chmod +x SkayLauncher-x86_64.AppImage
./SkayLauncher-x86_64.AppImage
```

If FUSE is not available:

```sh
./SkayLauncher-x86_64.AppImage --appimage-extract-and-run
```

The AppImage bundles Qt, Python, and the dependencies needed by the launcher. Standard X11 or Wayland client libraries from the host are still required.

### Windows EXE

Download `SkayLauncher.exe` and run it. It is a portable PyInstaller executable and does not need installation. Windows may show a SmartScreen warning for unsigned executables. See [SECURITY.md](SECURITY.md) for the signing scope.

### macOS

There is no macOS release asset. Running from source is documented under [Build from source](#build-from-source). Packaging on macOS is a manual step.

## Verify a download

Every release includes `SHA256SUMS` and one `.sig` file per asset. The `.sig` file contains a base64 encoded Ed25519 signature over the raw file bytes. The public key is embedded in `tools/sign_release.py` and in the application verifier.

```sh
python -m pip install -r requirements-dev.txt
python tools/sign_release.py verify SkayLauncher-x86_64.AppImage SkayLauncher-x86_64.AppImage.sig
sha256sum -c SHA256SUMS
```

On Windows, replace the asset name with `SkayLauncher.exe` and use `certutil -hashfile SkayLauncher.exe SHA256` for the checksum. Do not run an asset that fails verification. Full details are in [SECURITY.md](SECURITY.md).

## Build from source

Python 3.11 or newer is required.

```sh
python -m pip install -e ".[dev,build]"
python SkayLauncher.py
```

Run the checks with:

```sh
ruff check .
python -m compileall -q src tools SkayLauncher.py
python -m pytest -q
```

The Linux AppImage builder uses the current Python environment. It copies only the PySide6 modules used by the launcher, their native Qt dependencies, a small set of Qt plugins, one libpython, one OpenSSL generation, a CA bundle, and a pruned standard library. See [packaging/appimage/README.md](packaging/appimage/README.md).

```sh
python tools/build_appimage.py /path/to/appimagetool.AppImage
```

The Windows executable is built with a pinned PyInstaller version:

```sh
pyinstaller SkayLauncher.spec --noconfirm
```

See [packaging/windows/README.md](packaging/windows/README.md) for platform notes.

## Signing limits

Linux AppImage and Windows EXE release assets carry the Ed25519 signatures described above. That project signature is independent of operating system trust stores.

There is no Authenticode signed Windows binary and no signed or notarized macOS build. Those require paid certificates from Microsoft or Apple. Without them, Windows SmartScreen and macOS Gatekeeper can still warn or block execution. This project does not claim platform level signing that it does not have.

## Project layout

```text
src/skaylauncher/    application package
tests/               pytest suite
tools/               AppImage builder and release signing tool
packaging/           platform specific build notes
.github/workflows/   CI and signed release workflows
SkayLauncher.py      source entry point and PyInstaller entry point
```

## License

MIT. See [LICENSE](LICENSE).
