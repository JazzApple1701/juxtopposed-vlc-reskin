# PyInstaller recipe for "VLC Reskin.exe" (run build.bat rather than this directly).
# Produces dist\VLC Reskin\ : the exe plus the Python runtime and Qt it needs.
# Video decoding uses the VLC installed on the PC (python-vlc finds it via the registry).

import os

HERE = os.path.abspath(SPECPATH)
PLAYER = os.path.join(HERE, "player")

a = Analysis(
    [os.path.join(PLAYER, "main.py")],
    pathex=[PLAYER],
    datas=[(os.path.join(PLAYER, "assets"), "assets")],
    hiddenimports=[],
    excludes=[
        # Not used by the player; keeps the folder smaller.
        "tkinter", "PIL", "numpy",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick",
        "PySide6.QtMultimedia", "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization",
        "PySide6.QtPdf", "PySide6.QtTest", "PySide6.QtNetwork",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VLC Reskin",
    icon=os.path.join(PLAYER, "assets", "app.ico"),
    version=os.path.join(HERE, "version_info.txt"),
    console=False,          # a normal windowed app: no black console window
    upx=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="VLC Reskin",
    upx=False,
)
