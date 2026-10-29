# Build the game-only Windows application; runtime files come from publishers.
# One-folder layout on purpose: the single-file build self-extracts to %TEMP% and
# is flagged by Microsoft Defender's ML (Wacatac/Contebrew) and reputation (Suschil!rfn) engines.
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
    pyz, a.scripts, [], exclude_binaries=True,
    name="DLSS5-AIO", debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False, disable_windowed_traceback=False,
    icon=str(app_dir / "dlss5-aio.ico"),
    version=str(app_dir / "version_info.txt"),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="DLSS5-AIO")
