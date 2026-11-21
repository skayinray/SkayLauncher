# SkayLauncher 1.0.2

Performance release for slow GitHub downloads.

## Changes

- Large release assets are downloaded with up to eight parallel HTTP byte-range requests, with automatic fallback to a single stream when ranges are unsupported.
- GitHub release lookups for all repositories now run in parallel instead of one at a time.
- Download and API caches are thread-safe; partial files are cleaned up after failed or cancelled downloads.
- Raised the download socket timeout to 60 seconds for slow networks.
- Added `SKAYLAUNCHER_DOWNLOAD_SEGMENTS=1` to disable parallel downloads for restrictive proxies.

All downloads are still verified with SHA-256 checksums and the Ed25519 signature after assembly.

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
