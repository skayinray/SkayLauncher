# SkayLauncher 1.0.3

Fixes a startup failure in the Linux AppImage of 1.0.2.

## Changes

- Bundles the ICU 73 runtime required by Qt: the 1.0.2 AppImage crashed on startup with `libicui18n.so.73: cannot open shared object file`.
- Adds an automated AppImage smoke test to the release workflow so a build cannot be published if it fails to start. A matching smoke test checks the Windows executable.
- Pins `PySide6-Essentials` and `cryptography` so future builds use the same tested versions.
- Corrects the embedded application version, which was still reported as `1.0.0`.

If you installed 1.0.2, download this release and replace it. The 1.0.2 assets are no longer usable on Linux.

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

Ed25519 public key:

```text
WxuPjONAgTl81lw5mZT0hOwXFS2epOZb7G/aswOGVXk=
```

## Signing scope

These signatures are produced by the project release workflow. They are not operating system code signatures. The Windows executable is not Authenticode signed, and there is no signed or notarized macOS build. See [SECURITY.md](SECURITY.md) for details.
