# SkayLauncher 1.0.4

Faster release downloads on slow GitHub CDN routes.

## Changes

- Large release assets now use **16 parallel byte-range requests** with 2 MiB segments instead of 8 requests with 4 MiB segments. On a connection where GitHub serves a single stream at 14 KB/s, this raises the effective download rate to roughly 0.9 MB/s.
- `SKAYLAUNCHER_DOWNLOAD_SEGMENTS` still overrides the default (set it to `1` to disable parallel downloads).

Downloads remain verified with `SHA256SUMS` and the Ed25519 signature after assembly.

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
