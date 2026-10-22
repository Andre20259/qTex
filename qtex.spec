# PyInstaller build recipe for QTeX.  Used by build.ps1:  pyinstaller qtex.spec
# Produces dist/QTeX/ (a folder with QTeX.exe and its Qt libraries).
import os
import sys

block_cipher = None
here = os.path.abspath(SPECPATH)

# Qt modules QTeX doesn't use; excluding them keeps the build small.
unused_qt = [
    "QtWebEngineCore", "QtWebEngineWidgets", "QtWebEngineQuick", "QtWebChannel", "QtWebSockets",
    "QtQml", "QtQuick", "QtQuickWidgets", "QtQuick3D", "QtQuickControls2",
    "Qt3DCore", "Qt3DRender", "Qt3DInput", "Qt3DLogic", "Qt3DAnimation", "Qt3DExtras",
    "QtMultimedia", "QtMultimediaWidgets", "QtSpatialAudio", "QtCharts", "QtDataVisualization",
    "QtGraphs", "QtBluetooth", "QtNfc", "QtPositioning", "QtLocation", "QtSensors",
    "QtSerialPort", "QtSerialBus", "QtSql", "QtTest", "QtDesigner", "QtHelp", "QtUiTools",
    "QtRemoteObjects", "QtScxml", "QtStateMachine", "QtTextToSpeech", "QtHttpServer",
    "QtOpenGL", "QtOpenGLWidgets", "QtSvgWidgets", "QtAxContainer",
]

a = Analysis(
    [os.path.join(here, "texeditor.py")],
    pathex=[here],
    datas=[(os.path.join(here, "assets"), "assets")],
    hiddenimports=[],
    excludes=["tkinter", "unittest", "pydoc", "PyQt5", "PyQt6", "PySide2"]
             + [f"PySide6.{m}" for m in unused_qt],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="QTeX",
    icon=os.path.join(here, "assets", "qtex.ico"),
    console=False,          # windowed app: no terminal window
    upx=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="QTeX",
)
