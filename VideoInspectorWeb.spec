# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


project_root = Path(SPEC).resolve().parent
ffmpeg_dir = project_root / "tools" / "ffmpeg"
web_dist = project_root / "web" / "dist"

analysis = Analysis(
    [str(project_root / "app" / "web" / "launcher.py")],
    pathex=[str(project_root)],
    binaries=[
        (str(ffmpeg_dir / "ffmpeg.exe"), "tools/ffmpeg"),
        (str(ffmpeg_dir / "ffprobe.exe"), "tools/ffmpeg"),
    ],
    datas=[
        (str(project_root / "app" / "config" / "rules.json"), "config"),
        (str(ffmpeg_dir / "LICENSE.txt"), "tools/ffmpeg"),
        (str(web_dist), "web_static"),
    ],
    hiddenimports=(
        collect_submodules("uvicorn")
        + collect_submodules("multipart")
        + collect_submodules("python_multipart")
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide6"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="VideoInspectorWeb",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="VideoInspectorWeb",
)
