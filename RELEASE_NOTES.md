# SkayLauncher 1.0.5

Fixes broken card layout in smaller windows.

## Changes

- Cards no longer get squeezed to a fraction of their height when the window is small. The grid now scrolls instead of overlapping cards on top of each other.
- Long descriptions and topic lists are elided to fit the card width instead of overflowing into neighbouring cards.
- Added regression tests covering the small-window layout and text elision.

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
