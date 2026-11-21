# AppImage packaging

`tools/build_appimage.py` builds `SkayLauncher-x86_64.AppImage` from the active Python 3.11 or newer environment. The active environment must contain the runtime dependencies from `requirements.txt` and a Linux x86_64 PySide6 wheel.

## Build

```sh
python tools/build_appimage.py /path/to/appimagetool.AppImage
```

The builder checks these locations in order:

1. the path passed on the command line;
2. `tools/appimagetool.AppImage`;
3. the `APPIMAGETOOL` environment variable;
4. `--download`, which fetches pinned appimagetool 1.9.1 and checks SHA-256 `ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0`.

CI downloads the pinned tool and verifies that hash before calling the builder.

## Contents

- `PySide6.QtCore`, `PySide6.QtGui`, `PySide6.QtWidgets`, and `PySide6.QtNetwork` only.
- Native Qt and shiboken libraries discovered recursively with `ldd`.
- `shiboken6`, `cryptography`, and their native modules.
- Qt platform plugins `xcb`, `minimal`, and `offscreen`.
- Qt image plugins `png`, `jpeg`, and `ico`, plus the small TLS backend plugins.
- One libpython, one OpenSSL generation, a CA bundle, and a pruned standard library.
- The launcher package, its data files, the source entry point, a desktop file, and an icon.

WebEngine, Quick, Multimedia, 3D, Designer, Test, Sql, Svg, and the other unused PySide6 addons are never selected. `EXCLUDED_PYSIDE6_MODULES` in the builder records the exclusion list.

`AppRun` exports `LD_LIBRARY_PATH`, `PYTHONPATH`, `QT_PLUGIN_PATH`, `QT_QPA_PLATFORM_PLUGIN_PATH`, and `SSL_CERT_FILE`. HTTPS certificate verification remains enabled.

The builder prints the AppDir payload size and the final AppImage size after a successful run. Standard X11 or Wayland client libraries must still exist on the host.
