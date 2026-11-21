# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for the Windows portable build."""

from pathlib import Path

UNUSED_PYSIDE6_MODULES = [
    "PySide6.Qt3DAnimation", "PySide6.Qt3DCore", "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DRender",
    "PySide6.QtBluetooth", "PySide6.QtCharts", "PySide6.QtConcurrent",
    "PySide6.QtDataVisualization", "PySide6.QtDBus", "PySide6.QtDesigner",
    "PySide6.QtGraphs", "PySide6.QtGraphsWidgets", "PySide6.QtHelp",
    "PySide6.QtHttpServer", "PySide6.QtLocation", "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets", "PySide6.QtNetworkAuth", "PySide6.QtNfc",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtPositioning",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D",
    "PySide6.QtQuickControls2", "PySide6.QtQuickTest", "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtSensors",
    "PySide6.QtSerialBus", "PySide6.QtSerialPort", "PySide6.QtSpatialAudio",
    "PySide6.QtSql", "PySide6.QtStateMachine", "PySide6.QtSvg",
    "PySide6.QtSvgWidgets", "PySide6.QtTest", "PySide6.QtTextToSpeech",
    "PySide6.QtUiTools", "PySide6.QtWebChannel", "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSocket", "PySide6.QtWebSockets", "PySide6.QtWebView",
]

datas = [
    ("src/skaylauncher/updater/windows_replace.ps1", "skaylauncher/updater"),
    ("LICENSE", "."),
]

for resource_dir in (
    Path("src/resources"),
    Path("src/skaylauncher/resources"),
):
    if resource_dir.is_dir():
        datas.append((str(resource_dir), "skaylauncher/resources"))
        break

icon = next(
    (
        str(path)
        for path in (
            Path("src/resources/icon.ico"),
            Path("src/skaylauncher/resources/icon.ico"),
        )
        if path.is_file()
    ),
    None,
)

a = Analysis(
    ["SkayLauncher.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtNetwork",
        "shiboken6",
        "skaylauncher.ui.main_window",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=UNUSED_PYSIDE6_MODULES + [
        "tkinter", "idlelib", "pydoc_data", "distutils", "ensurepip", "venv",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe_options = {
    "name": "SkayLauncher",
    "debug": False,
    "bootloader_ignore_signals": False,
    "strip": False,
    "upx": False,
    "console": False,
    "disable_windowed_traceback": False,
    "argv_emulation": False,
    "target_arch": None,
    "codesign_identity": None,
    "entitlements_file": None,
}
if icon:
    exe_options["icon"] = icon

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    **exe_options,
)
