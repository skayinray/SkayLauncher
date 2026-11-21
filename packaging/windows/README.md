# Windows packaging

The Windows release asset is a portable `SkayLauncher.exe` built with PyInstaller 6.22.3. It does not install system components and does not need administrator rights.

## Build

```bat
python -m pip install -r requirements.txt -r requirements-dev.txt
pyinstaller SkayLauncher.spec --noconfirm --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtQuick --exclude-module PySide6.QtMultimedia
```

Release builds pass the full `--exclude-module` list from `.github/workflows/build.yml`. `SkayLauncher.spec` repeats that list in `excludes` and adds the following data files:

- `src/skaylauncher/updater/windows_replace.ps1` into `skaylauncher/updater` for self-update;
- `LICENSE` into the bundle root;
- `src/resources` or `src/skaylauncher/resources` when present.

The update helper is read by `skaylauncher.updater.updater` at runtime with `Path(__file__).with_name("windows_replace.ps1")`. Keep the destination path in sync if the updater layout changes.

## Signing

The EXE is not Authenticode signed. Authenticode needs a paid code signing certificate, which this project does not provide. Windows SmartScreen can warn about an unsigned executable.

The release workflow instead creates an Ed25519 `.sig` file over the raw EXE bytes and includes the EXE in `SHA256SUMS`. Verify it with `tools/sign_release.py` as described in [SECURITY.md](../../SECURITY.md). OS trust and project signature verification are separate mechanisms.
