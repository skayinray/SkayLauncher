"""Build a slim SkayLauncher AppImage from the current Python environment.

Only the PySide6 modules used by the launcher are copied, together with their
recursive Qt dependencies, a small set of Qt plugins, one libpython, one
OpenSSL generation, a CA bundle, and a pruned Python standard library.

Usage:
    python tools/build_appimage.py [path/to/appimagetool.AppImage]
    python tools/build_appimage.py --download
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import os
import shutil
import subprocess
import sys
import sysconfig
import urllib.request
import zlib
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
APPDIR = BUILD / "AppDir"
OUTPUT = ROOT / "SkayLauncher-x86_64.AppImage"

PY_VERSION = f"python{sys.version_info.major}.{sys.version_info.minor}"
PY_SHORT = f"{sys.version_info.major}.{sys.version_info.minor}"

APPIMAGETOOL_VERSION = "1.9.1"
APPIMAGETOOL_SHA256 = "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"

QT_MODULES = ("QtCore", "QtGui", "QtWidgets", "QtNetwork")
QT_LIB_PREFIXES = ("libQt6", "libshiboken6", "libpyside6")

# These bindings are never copied. The list documents the deliberate exclusions
# and guards against adding a module name by mistake.
EXCLUDED_PYSIDE6_MODULES = (
    "Qt3D", "QtBluetooth", "QtCharts", "QtConcurrent", "QtDataVisualization",
    "QtDBus", "QtDesigner", "QtGraphs", "QtHelp", "QtHttpServer", "QtLocation",
    "QtMultimedia", "QtNetworkAuth", "QtNfc", "QtPdf", "QtPositioning", "QtQml",
    "QtQuick", "QtRemoteObjects", "QtSensors", "QtSerialBus", "QtSerialPort",
    "QtSql", "QtSvg", "QtTest", "QtTextToSpeech", "QtUiTools", "QtWebChannel",
    "QtWebEngine", "QtWebSocket", "QtWebSockets", "QtWebView",
)

# Match by stem because wheel and system Qt use different file name prefixes.
PLUGIN_STEMS = {
    "platforms": ("qxcb", "qminimal", "qoffscreen"),
    "imageformats": ("qpng", "qjpeg", "qico"),
    "tls": ("qopensslbackend", "qcertonlybackend"),
}

GENERIC_LIB_PREFIXES = (
    "libssl", "libcrypto", "libffi", "libz", "libbz2", "liblzma",
    "libsqlite3", "libuuid", "libexpat", "libbrotli", "libzstd", "libgcc_s",
)
OPENSSL_VERSIONS = ("3", "4", "1.1")

STDLIB_EXCLUDES = (
    "__pycache__",
    "*.pyc",
    "site-packages",
    "test",
    "tests",
    "idlelib",
    "tkinter",
    "lib2to3",
    "ensurepip",
    "turtledemo",
    "distutils",
    "venv",
    "pydoc_data",
    "config-*",
    "libpython*.a",
    "Tools",
)

CA_BUNDLES = (
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/pki/tls/certs/ca-bundle.crt",
    "/etc/ssl/cert.pem",
)


def python_paths() -> tuple[Path, Path]:
    paths = sysconfig.get_paths()
    stdlib = Path(paths["stdlib"])
    candidates = [Path(paths["purelib"]), Path(paths.get("platlib", paths["purelib"]))]
    site_packages = next(
        (path for path in candidates if (path / "PySide6").is_dir()), candidates[0]
    )
    if not (site_packages / "PySide6").is_dir():
        raise SystemExit(f"PySide6 is not installed in {site_packages}")
    return stdlib, site_packages


PY_STDLIB, SITE_PACKAGES = python_paths()


def check_module_selection() -> None:
    selected = set(QT_MODULES)
    blocked = {name for name in EXCLUDED_PYSIDE6_MODULES if name in selected}
    if blocked:
        raise SystemExit(f"excluded PySide6 modules selected for packaging: {sorted(blocked)}")


def qt_plugins_dir() -> Path:
    candidates = (
        SITE_PACKAGES / "PySide6" / "Qt" / "plugins",
        SITE_PACKAGES / "PySide6" / "Qt6" / "plugins",
        Path("/usr/lib/qt6/plugins"),
    )
    for candidate in candidates:
        if (candidate / "platforms").is_dir():
            return candidate
    return candidates[0]


def library_search_dirs() -> list[Path]:
    return [
        SITE_PACKAGES / "PySide6" / "Qt" / "lib",
        SITE_PACKAGES / "PySide6" / "Qt6" / "lib",
        Path("/usr/lib"),
        Path("/usr/lib64"),
        Path("/usr/lib/x86_64-linux-gnu"),
        Path("/lib/x86_64-linux-gnu"),
    ]


def ldd_dependencies(path: Path) -> tuple[list[tuple[str, Path]], set[str]]:
    """Return (soname, resolved file) pairs and unresolved SONAMEs for an ELF file."""
    try:
        result = subprocess.run(
            ["ldd", str(path)],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return [], set()

    resolved: list[tuple[str, Path]] = []
    missing: set[str] = set()
    for line in result.stdout.splitlines():
        fields = line.strip().split()
        if not fields:
            continue
        name = fields[0]
        if "=>" in fields:
            index = fields.index("=>")
            if index + 1 >= len(fields) or fields[index + 1] == "not":
                missing.add(name)
                continue
            target = fields[index + 1]
        elif len(fields) >= 2 and fields[1].startswith("/"):
            target = fields[1]
        else:
            continue
        if target.startswith("/") and Path(target).is_file():
            resolved.append((Path(target).name, Path(target).resolve()))
    return resolved, missing


def collect_native_libs(seeds: list[Path], prefixes: tuple[str, ...]) -> dict[str, Path]:
    """Follow ldd from each seed and keep only libraries with an allowed prefix."""
    queue: deque[Path] = deque(seeds)
    found: dict[str, Path] = {}
    seen: set[Path] = set()
    missing: set[str] = set()

    while queue:
        target = queue.popleft()
        try:
            real = target.resolve()
        except OSError:
            continue
        if real in seen or not real.is_file():
            continue
        seen.add(real)

        dependencies, unresolved = ldd_dependencies(real)
        missing.update(unresolved)
        for soname, dependency in dependencies:
            if soname.startswith(prefixes) and soname not in found:
                found[soname] = dependency
                queue.append(dependency)

    for name in sorted(missing):
        if not name.startswith(prefixes) or name in found:
            continue
        for directory in library_search_dirs():
            candidate = directory / name
            if candidate.is_file():
                found[name] = candidate.resolve()
                break
    return dict(sorted(found.items()))


def ignored_stdlib(directory: str, names: list[str]) -> set[str]:
    del directory
    return {
        name for name in names if any(fnmatch.fnmatchcase(name, pattern) for pattern in STDLIB_EXCLUDES)
    }


def copy_stdlib() -> None:
    destination = APPDIR / "usr/lib" / PY_VERSION
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        PY_STDLIB, destination, ignore=ignored_stdlib, symlinks=True, dirs_exist_ok=True
    )


def copy_libpython(destination: Path) -> None:
    libdir = Path(sysconfig.get_config_var("LIBDIR") or "")
    candidates = [
        value for value in (
            sysconfig.get_config_var("INSTSONAME"),
            sysconfig.get_config_var("LDLIBRARY"),
        ) if value
    ]
    for value in candidates:
        candidate = libdir / str(value)
        if candidate.is_file():
            source = candidate.resolve()
            shutil.copy2(source, destination / candidate.name)
            return
    for source in sorted(libdir.glob(f"libpython{PY_SHORT}*.so*")):
        if source.is_file():
            shutil.copy2(source.resolve(), destination / source.name)
            return
    print("warning: no shared libpython found; assuming a statically linked interpreter")


def copy_python_runtime() -> str:
    executable = Path(sys.executable).resolve()
    bin_dir = APPDIR / "usr/bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(executable, bin_dir / executable.name)
    if executable.name != "python3":
        (bin_dir / "python3").symlink_to(executable.name)
    copy_libpython(APPDIR / "usr/lib")
    return executable.name


def copy_python_packages() -> list[Path]:
    """Copy the launcher, its package data, and the minimum Python packages."""
    destination = APPDIR / "usr/lib" / PY_VERSION / "site-packages"
    destination.mkdir(parents=True, exist_ok=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyi")

    pyside_src = SITE_PACKAGES / "PySide6"
    pyside_dst = destination / "PySide6"
    pyside_dst.mkdir(parents=True, exist_ok=True)
    for name in ("__init__.py", "_config.py", "_git_pyside_version.py"):
        source = pyside_src / name
        if source.is_file():
            shutil.copy2(source, pyside_dst / name)
    support = pyside_src / "support"
    if support.is_dir():
        shutil.copytree(support, pyside_dst / "support", ignore=ignore, dirs_exist_ok=True)

    seeds: list[Path] = []
    for module in QT_MODULES:
        matches = sorted(pyside_src.glob(f"{module}.*so")) or sorted(pyside_src.glob(f"{module}.so"))
        if not matches:
            raise SystemExit(f"PySide6.{module} extension module not found in {pyside_src}")
        for source in matches:
            shutil.copy2(source.resolve(), pyside_dst / source.name)
            seeds.append(source.resolve())

    for package in ("shiboken6", "shiboken6_generator", "cryptography"):
        source = SITE_PACKAGES / package
        if source.is_dir():
            shutil.copytree(source, destination / package, ignore=ignore, symlinks=True)

    # cryptography's Rust extension imports this module at runtime.
    for backend in SITE_PACKAGES.glob("_cffi_backend*.so"):
        shutil.copy2(backend.resolve(), destination / backend.name)

    src_package = ROOT / "src" / "skaylauncher"
    if not src_package.is_dir():
        raise SystemExit(f"application package not found: {src_package}")
    shutil.copytree(src_package, destination / "skaylauncher", ignore=ignore, dirs_exist_ok=True)

    resources = ROOT / "src" / "resources"
    if resources.is_dir():
        shutil.copytree(
            resources, destination / "skaylauncher" / "resources", ignore=ignore, dirs_exist_ok=True
        )
        share_resources = APPDIR / "usr/share/skaylauncher/resources"
        share_resources.mkdir(parents=True, exist_ok=True)
        shutil.copytree(resources, share_resources, ignore=ignore, dirs_exist_ok=True)

    for native in destination.rglob("*.so*"):
        if native.is_file():
            seeds.append(native)
    return seeds


def copy_plugins() -> list[Path]:
    """Copy the small plugin set and return native dependency seeds."""
    base = qt_plugins_dir()
    seeds: list[Path] = []
    for group, stems in PLUGIN_STEMS.items():
        directory = base / group
        if not directory.is_dir():
            print(f"warning: Qt plugin directory not found: {directory}", file=sys.stderr)
            continue
        for stem in stems:
            matches = sorted(directory.glob(f"*{stem}.so"))
            if not matches:
                print(f"warning: Qt plugin {stem} not found in {directory}", file=sys.stderr)
                continue
            plugin = matches[0].resolve()
            target = APPDIR / "usr/lib/qt/plugins" / group / matches[0].name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(plugin, target)
            seeds.append(plugin)
    return seeds


def select_openssl_version() -> tuple[str, list[tuple[str, Path]]]:
    """Choose exactly one OpenSSL generation and return its library pair."""
    for version in OPENSSL_VERSIONS:
        for directory in library_search_dirs():
            ssl = directory / f"libssl.so.{version}"
            crypto = directory / f"libcrypto.so.{version}"
            if ssl.is_file() and crypto.is_file():
                return version, [
                    (ssl.name, ssl.resolve()),
                    (crypto.name, crypto.resolve()),
                ]
    return "", []


def copy_ca_bundle() -> None:
    destination = APPDIR / "usr/share/skaylauncher/ca-bundle.crt"
    destination.parent.mkdir(parents=True, exist_ok=True)
    for pattern in CA_BUNDLES:
        source = Path(pattern)
        if source.is_file():
            shutil.copy2(source.resolve(), destination)
            return
    print("warning: no system CA bundle found", file=sys.stderr)


def find_icon() -> Path | None:
    candidates = (
        ROOT / "src/resources/icon.png",
        ROOT / "src/skaylauncher/resources/icon.png",
        ROOT / "src/resources/icon.ico",
        ROOT / "src/skaylauncher/resources/icon.ico",
    )
    return next((path for path in candidates if path.is_file()), None)


def write_fallback_icon(path: Path, size: int = 256) -> None:
    """Write a small solid PNG so appimagetool has a DirIcon without extra deps."""
    colour = bytes((26, 31, 43, 255))
    scanlines = b"".join(b"\x00" + colour * size for _ in range(size))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            len(data).to_bytes(4, "big")
            + kind
            + data
            + zlib.crc32(kind + data).to_bytes(4, "big")
        )

    header = b"\x89PNG\r\n\x1a\n"
    ihdr = size.to_bytes(4, "big") + size.to_bytes(4, "big") + bytes((8, 6, 0, 0, 0))
    path.write_bytes(header + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(scanlines)) + chunk(b"IEND", b""))


def write_desktop_and_apprun(python_name: str) -> None:
    desktop = """[Desktop Entry]
Type=Application
Name=SkayLauncher
GenericName=Application Launcher
Comment=Browse and install releases published by skayinray
Exec=SkayLauncher
Icon=skaylauncher
Terminal=false
Categories=Utility;
StartupNotify=true
"""
    (APPDIR / "SkayLauncher.desktop").write_text(desktop, encoding="utf-8")
    applications = APPDIR / "usr/share/applications"
    applications.mkdir(parents=True, exist_ok=True)
    (applications / "SkayLauncher.desktop").write_text(desktop, encoding="utf-8")

    apprun = f"""#!/bin/sh
APPDIR="$(dirname "$(readlink -f "$0")")"
export APPDIR
export LD_LIBRARY_PATH="$APPDIR/usr/lib${{LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}}"
export QT_PLUGIN_PATH="$APPDIR/usr/lib/qt/plugins"
export QT_QPA_PLATFORM_PLUGIN_PATH="$APPDIR/usr/lib/qt/plugins/platforms"
export PYTHONPATH="$APPDIR/usr/lib/{PY_VERSION}/site-packages${{PYTHONPATH:+:$PYTHONPATH}}"
export XDG_DATA_DIRS="$APPDIR/usr/share:${{XDG_DATA_DIRS:-/usr/local/share:/usr/share}}"
if [ -f "$APPDIR/usr/share/skaylauncher/ca-bundle.crt" ]; then
    export SSL_CERT_FILE="$APPDIR/usr/share/skaylauncher/ca-bundle.crt"
fi
exec "$APPDIR/usr/bin/{python_name}" "$APPDIR/usr/share/skaylauncher/SkayLauncher.py" "$@"
"""
    apprun_path = APPDIR / "AppRun"
    apprun_path.write_text(apprun, encoding="utf-8")
    apprun_path.chmod(0o755)


def copy_app_files() -> None:
    source_entry = ROOT / "SkayLauncher.py"
    if not source_entry.is_file():
        raise SystemExit(f"entry point not found: {source_entry}")
    share = APPDIR / "usr/share/skaylauncher"
    share.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_entry, share / "SkayLauncher.py")

    icon = find_icon()
    icon_target = APPDIR / "skaylauncher.png"
    if icon:
        shutil.copy2(icon, icon_target)
    else:
        write_fallback_icon(icon_target)
    hicolor = APPDIR / "usr/share/icons/hicolor/256x256/apps"
    hicolor.mkdir(parents=True, exist_ok=True)
    shutil.copy2(icon_target, hicolor / "skaylauncher.png")
    (APPDIR / ".DirIcon").symlink_to("skaylauncher.png")

    if (ROOT / "LICENSE").is_file():
        doc_dir = APPDIR / "usr/share/doc/skaylauncher"
        doc_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "LICENSE", doc_dir / "copyright")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_appimagetool() -> Path:
    url = (
        "https://github.com/AppImage/appimagetool/releases/download/"
        f"{APPIMAGETOOL_VERSION}/appimagetool-x86_64.AppImage"
    )
    target = BUILD / f"appimagetool-{APPIMAGETOOL_VERSION}-x86_64.AppImage"
    BUILD.mkdir(parents=True, exist_ok=True)
    if target.is_file() and _sha256(target) == APPIMAGETOOL_SHA256:
        return target

    print(f"downloading pinned appimagetool {APPIMAGETOOL_VERSION}")
    try:
        with urllib.request.urlopen(url, timeout=60) as response, target.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
    except (OSError, ValueError) as error:
        target.unlink(missing_ok=True)
        raise SystemExit(f"cannot download appimagetool: {error}") from error

    actual = _sha256(target)
    if actual != APPIMAGETOOL_SHA256:
        target.unlink(missing_ok=True)
        raise SystemExit(f"appimagetool SHA-256 mismatch: expected {APPIMAGETOOL_SHA256}, got {actual}")
    target.chmod(0o755)
    return target


def resolve_tool(cli_path: str | None, download: bool) -> Path:
    if cli_path:
        tool = Path(cli_path).expanduser().resolve()
        if not tool.is_file():
            raise SystemExit(f"appimagetool not found: {tool}")
        return tool

    local = ROOT / "tools" / "appimagetool.AppImage"
    if local.is_file():
        return local

    env_path = os.environ.get("APPIMAGETOOL", "")
    if env_path:
        tool = Path(env_path).expanduser().resolve()
        if not tool.is_file():
            raise SystemExit(f"appimagetool not found: {tool}")
        return tool

    if download:
        return download_appimagetool()
    raise SystemExit(
        "appimagetool is missing; pass its path, place tools/appimagetool.AppImage, "
        "set APPIMAGETOOL, or use --download"
    )


def prepare_tool(tool: Path) -> Path:
    extracted = BUILD / "appimagetool-root"
    stale = BUILD / "squashfs-root"
    if extracted.exists():
        shutil.rmtree(extracted)
    if stale.exists():
        shutil.rmtree(stale)
    BUILD.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(tool), "--appimage-extract"], cwd=BUILD, check=True, stdout=subprocess.DEVNULL)
    stale.rename(extracted)
    tool_bin = extracted / "AppRun"
    tool_bin.chmod(0o755)
    return tool_bin


def report_size() -> None:
    payload = sum(path.stat().st_size for path in APPDIR.rglob("*") if path.is_file())
    print(f"AppDir payload: {payload / (1024 * 1024):.1f} MiB")
    if OUTPUT.is_file():
        print(f"AppImage size: {OUTPUT.stat().st_size / (1024 * 1024):.1f} MiB")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("appimagetool", nargs="?", help="path to appimagetool.AppImage")
    parser.add_argument(
        "--download",
        action="store_true",
        help="download the pinned appimagetool version with SHA-256 verification",
    )
    args = parser.parse_args(argv)

    if not sys.platform.startswith("linux"):
        raise SystemExit("the AppImage builder requires Linux")
    check_module_selection()
    tool = resolve_tool(args.appimagetool, args.download)

    if APPDIR.exists():
        shutil.rmtree(APPDIR)
    for directory in ("usr/bin", "usr/lib", "usr/share/skaylauncher"):
        (APPDIR / directory).mkdir(parents=True, exist_ok=True)

    print("[1/6] Python interpreter and pruned standard library")
    python_name = copy_python_runtime()
    copy_stdlib()

    print("[2/6] Launcher package and minimal Python dependencies")
    seeds = copy_python_packages()

    print("[3/6] Qt plugins and native libraries")
    seeds.extend(copy_plugins())
    qt_libs = collect_native_libs(seeds, QT_LIB_PREFIXES)
    openssl_version, openssl_libs = select_openssl_version()

    dynload = APPDIR / "usr/lib" / PY_VERSION / "lib-dynload"
    stdlib_seeds = [
        path for pattern in ("_ssl*.so", "_hashlib*.so", "_lzma*.so", "_bz2*.so", "_sqlite3*.so")
        for path in dynload.glob(pattern)
    ]
    generic_libs = collect_native_libs(seeds + stdlib_seeds, GENERIC_LIB_PREFIXES)
    for name in list(generic_libs):
        if name.startswith(("libssl.so.", "libcrypto.so.")):
            if not openssl_version or not name.endswith(f".{openssl_version}"):
                del generic_libs[name]

    for soname, library in sorted({**qt_libs, **generic_libs, **dict(openssl_libs)}.items()):
        shutil.copy2(library, APPDIR / "usr/lib" / soname)

    print("[4/6] Application files, CA bundle, and desktop integration")
    copy_ca_bundle()
    copy_app_files()
    write_desktop_and_apprun(python_name)

    print("[5/6] Prepare appimagetool")
    tool_bin = prepare_tool(tool)

    print("[6/6] Pack AppImage")
    if OUTPUT.exists():
        OUTPUT.unlink()
    subprocess.run([str(tool_bin), "--no-appstream", str(APPDIR), str(OUTPUT)], check=True)
    OUTPUT.chmod(0o755)
    report_size()
    print(f"Done: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
