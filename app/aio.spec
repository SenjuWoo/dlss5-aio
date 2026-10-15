# Build the game-only Windows application; runtime files come from publishers.
from pathlib import Path

app_dir = Path(SPECPATH)
a = Analysis(
    [str(app_dir / "dlss5_aio.py")],
    pathex=[str(app_dir)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["core.ui.ctl_video", "core.ui.vidpage"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    name="DLSS5-AIO", debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False, disable_windowed_traceback=False,
    icon=str(app_dir / "dlss5-aio.ico"),
    version=str(app_dir / "version_info.txt"),
)
