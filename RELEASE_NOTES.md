# SkayLauncher 1.0.1

Maintenance release with installation discovery and responsive window layout.

## Changes

- Detects apps installed outside the launcher, including AppImageLauncher files in `~/Applications`, `.desktop` entries, Windows uninstall registry records, and macOS bundles.
- Shows detected apps with a **FOUND** badge; launching, reinstalling and forgetting them are supported. Forgetting never deletes the file on disk.
- Adds `SKAYLAUNCHER_DISCOVERY_DIRS` for extra scan directories.
- Lowers the minimum window size to 640x460 and adapts sidebar width, card columns and toolbar to the available space.
- Fixes fullscreen: no transparent margins, no corner-resize handling, `F11` toggles fullscreen and `Esc` exits it.
- Adds a fullscreen button to the custom title bar.

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
