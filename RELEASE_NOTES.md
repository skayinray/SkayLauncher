# SkayLauncher 1.0.0

First signed release of the PySide6 desktop launcher for public `skayinray` GitHub releases.

## Features

- Discovers public `skayinray` repositories with releases and ignores forks by default.
- Selects Linux AppImage or Windows EXE/ZIP assets for the current platform.
- Installs, launches, reinstalls, updates, and removes apps from a local registry.
- Verifies SHA-256 checksums and Ed25519 signatures before installing an asset.
- Checks for launcher updates in packaged builds and applies signed updates.
- Runs as a single instance with tray integration, search, tabs, patch notes, three themes, and English or Russian UI text.
- Caches GitHub API responses with ETags and reports new repositories or releases in the UI and tray.

## Assets

| Platform | Asset |
| --- | --- |
| Linux | `SkayLauncher-x86_64.AppImage` |
| Windows | `SkayLauncher.exe` |
| Checksums | `SHA256SUMS` |

Each asset has a `.sig` file containing an Ed25519 signature over the raw file bytes.

## Verify

```sh
python -m pip install -r requirements-dev.txt
python tools/sign_release.py verify SkayLauncher-x86_64.AppImage SkayLauncher-x86_64.AppImage.sig
sha256sum -c SHA256SUMS
```

On Windows, verify `SkayLauncher.exe` and compare its SHA-256 value with `SHA256SUMS`.

Ed25519 public key:

```text
WxuPjONAgTl81lw5mZT0hOwXFS2epOZb7G/aswOGVXk=
```

## Signing scope

These signatures are produced by the project release workflow. They are not operating system code signatures. The Windows executable is not Authenticode signed, and there is no signed or notarized macOS build. See [SECURITY.md](SECURITY.md) for details.
