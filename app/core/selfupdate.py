r"""Downloading and applying an update to this executable.

A running .exe cannot overwrite itself on Windows, so the swap is done by a
tiny batch file that waits for this process to exit, replaces the file, and
starts the new one. The old executable is kept as .old.exe through the new
build's first run, so a bad build can be rolled back by hand, and removed the
next time the tool starts (settle()).

Deliberately conservative:
  - the download is verified to be a real 64-bit PE of a sane size before
    anything is replaced;
  - the swap only happens after the user asks for it, never on its own;
  - nothing is deleted during the swap, only renamed; the old build goes
    only after the new one has come up once (settle()).

Two release layouts are understood. Today's is one self-contained .exe.
A release may instead ship the .exe with an `_internal` folder beside it
(PyInstaller's one-folder build, which antivirus heuristics take far less
exception to than a self-extracting single file); then the whole folder is
fetched and the swap replaces the folder as well as the .exe. This updater
has to know both BEFORE such a release exists: the copy already on
someone's PC is the one that will install it.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

from . import net, update

MIN_BYTES = 4 * 1024 * 1024          # a real one-file build is ~11 MB
# PyInstaller's one-folder layout keeps the runtime beside the .exe here.
INTERNAL = "_internal"


class UpdateError(RuntimeError):
    pass


def running_exe() -> Path | None:
    """The .exe to replace, or None when running from source."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable)
    return None


def _is_win64_pe(p: Path) -> bool:
    try:
        with open(p, "rb") as f:
            head = f.read(0x40)
            if len(head) < 0x40 or head[:2] != b"MZ":
                return False
            (off,) = struct.unpack_from("<I", head, 0x3C)
            f.seek(off)
            sig = f.read(6)
            return len(sig) == 6 and sig[:4] == b"PE\0\0" and \
                struct.unpack_from("<H", sig, 4)[0] == 0x8664
    except OSError:
        return False


PREFIX = "dlss5-aio-update-"


def fetch(progress=None) -> Path:
    """Download the latest release and return the extracted .exe.

    The staging folder goes if anything fails; one from an update that
    finished is emptied by the swap script and removed on the next fetch.
    Nothing removed them before, and a failed or refused download left one
    in %TEMP% each time.
    """
    _prune_old_staging()
    workdir = Path(tempfile.mkdtemp(prefix=PREFIX))
    try:
        return _fetch(workdir, progress)
    except BaseException:
        shutil.rmtree(workdir, ignore_errors=True)
        raise


def _prune_old_staging(max_age: float = 24 * 3600) -> None:
    """Staging folders of ours older than a day: a finished or failed update."""
    now = time.time()
    try:
        for d in Path(tempfile.gettempdir()).glob(PREFIX + "*"):
            try:
                if d.is_dir() and now - d.stat().st_mtime > max_age:
                    shutil.rmtree(d, ignore_errors=True)
            except OSError:
                continue
    except OSError:
        pass


def _fetch(workdir: Path, progress=None) -> Path:
    rel = net.json_get(update.API)
    assets = rel.get("assets", [])
    zipped_asset = next((a for a in assets
                    if a["name"].lower().startswith("dlss5-aio")
                    and a["name"].lower().endswith(".zip")), None)
    zip_url = zipped_asset["browser_download_url"] if zipped_asset else None
    exe_url = next((a["browser_download_url"] for a in assets
                    if a["name"].lower() == "dlss5-aio.exe"), None)
    sums_url = next((a["browser_download_url"] for a in assets
                     if a["name"] == "SHA256SUMS.txt"), None)
    tag = (rel.get("tag_name") or "new").lstrip("vV")
    if not sums_url:
        raise UpdateError("The release has no SHA256SUMS.txt; refusing an unverified update.")
    if not zip_url and not exe_url:
        raise UpdateError("The release has no downloadable build.")
    try:
        sums = net.fetch_text(sums_url).decode("utf8", "strict")
    except Exception as e:
        raise UpdateError(f"Could not read SHA256SUMS.txt ({e}); refusing an unverified update.") from e
    tag = re.sub(r"[^A-Za-z0-9._-]", "_", tag)

    if zip_url:
        z = net.download(zip_url, f"update-{tag}.zip", progress=progress)
        # One-folder updates load native DLLs too: authenticate the whole archive.
        expected_archive = _expected_hash(sums, zipped_asset["name"])
        if not expected_archive or net.sha256(z) != expected_archive:
            raise UpdateError("The release archive does not match SHA256SUMS.txt; refusing it.")
        with zipfile.ZipFile(z) as arc:
            names = [info.filename for info in net.zip_entries(arc)]
            executables = [n for n in names
                           if n.replace("\\", "/").split("/")[-1].lower() == "dlss5-aio.exe"]
            if len(executables) != 1:
                raise UpdateError("The release archive must contain exactly one executable.")
            member = executables[0]
            base = member.rsplit("/", 1)[0] + "/" if "/" in member else ""
            folder = [n for n in names
                      if n.startswith(base + INTERNAL + "/") and not n.endswith("/")]
            if folder:
                # One-folder build: the .exe and everything under _internal,
                # kept together - the .exe alone cannot start.
                for n in folder + [member]:
                    # Member names come out of a downloaded archive, so they
                    # are somebody else's strings: a `../` in one writes
                    # outside the temporary folder, and it happens before the
                    # build checks below can reject the download (#79).
                    try:
                        dest = net.inside(workdir, n[len(base):])
                    except net.OutsideError as e:
                        raise UpdateError(
                            f"The release archive contains a path that writes "
                            f"outside the update folder - refusing it. ({e})"
                        ) from None
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with arc.open(n) as src, open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst, 1 << 20)
                out = workdir / Path(member).name
            else:
                out = workdir / Path(member).name
                with arc.open(member) as src, open(out, "wb") as dst:
                    shutil.copyfileobj(src, dst, 1 << 20)
    elif exe_url:
        got = net.download(exe_url, f"update-{tag}.exe", progress=progress)
        out = workdir / got.name
        out.write_bytes(got.read_bytes())
    else:
        raise UpdateError("The release has no downloadable build.")

    # A one-folder build keeps its bulk in _internal; the exe alone is the
    # bootloader plus the app, a couple of MB. Judge the whole download.
    got = out.stat().st_size
    if (out.parent / INTERNAL).is_dir():
        got += sum(p.stat().st_size for p in (out.parent / INTERNAL).rglob("*")
                   if p.is_file())
    if got < MIN_BYTES:
        raise UpdateError(f"The downloaded build is only {got} "
                          f"bytes - refusing to install it.")
    if not _is_win64_pe(out):
        raise UpdateError("The downloaded file is not a 64-bit Windows "
                          "executable - refusing to install it.")
    # A fork release must publish an exact executable checksum before it can run.
    if sums_url:
        want = _expected_hash(sums, "DLSS5-AIO.exe")
        if not want:
            raise UpdateError("SHA256SUMS.txt does not list DLSS5-AIO.exe "
                              "- refusing to install an unverified build.")
        have = _sha256(out)
        if have != want:
            raise UpdateError(f"The downloaded build does not match the hash "
                              f"GitHub published ({have[:12]}... vs "
                              f"{want[:12]}...) - refusing to install it.")
    return out


def _expected_hash(sums: str, name: str) -> str | None:
    """The hash for `name` from a sha256sum-style listing (paths allowed)."""
    found = []
    for line in sums.splitlines():
        parts = line.strip().split()
        if (len(parts) == 2 and re.fullmatch(r"[A-Fa-f0-9]{64}", parts[0])
                and parts[1].lstrip("*").replace("\\", "/").rsplit("/", 1)[-1] == name):
            found.append(parts[0].lower())
    if len(found) > 1:
        raise UpdateError(f"SHA256SUMS.txt lists {name} more than once; refusing an ambiguous update.")
    return found[0] if found else None


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def swap_script(current: Path, new_exe: Path) -> str:
    """The batch file that replaces `current` with `new_exe` once we exit.

    ping is the portable way to wait a moment in a .bat; the loop retries
    while the old process still holds the file handle. When the new build
    brings an _internal folder, the folder is swapped the same way - the old
    one kept as _internal.old beside the .old.exe, so the pair can be put
    back by hand.
    """
    old, old_int = old_build(current)
    new_int = new_exe.parent / INTERNAL
    cur_int = current.parent / INTERNAL
    # Batch expands percent variables even inside quotes; these are literal paths.
    def literal(path):
        return str(path).replace("%", "%%")
    lines = [
        "@echo off",
        "chcp 65001 >nul",
        "setlocal DisableDelayedExpansion",
        f'set "TARGET={literal(current)}"',
        f'set "SOURCE={literal(new_exe)}"',
        f'set "BACKUP={literal(old)}"',
        "for /L %%i in (1,1,30) do (",
        "  ping -n 2 127.0.0.1 >nul",
        '  if exist "%BACKUP%" del /q "%BACKUP%" >nul 2>&1',
        '  move /y "%TARGET%" "%BACKUP%" >nul 2>&1 && goto swap',
        ")",
        "echo Could not replace the executable; it is still running.",
        "pause",
        "exit /b 1",
        ":swap",
    ]
    if new_int.is_dir():
        # The download is staged under %TEMP%, which may be another drive
        # than the install: cmd's `move` cannot move a directory across
        # drives (and reports success anyway), so the folder is copied with
        # xcopy and the copy is checked before anything is committed. The
        # exe is copied too, for the same reason; the old pair stays as
        # .old.exe + _internal.old until settle() removes it.
        lines += [
            f'if exist "{literal(old_int)}" rmdir /s /q "{literal(old_int)}" >nul 2>&1',
            f'if exist "{literal(old_int)}" goto restoreexe',
            f'if exist "{literal(cur_int)}" move /y "{literal(cur_int)}" "{literal(old_int)}" >nul 2>&1',
            f'if exist "{literal(cur_int)}" goto restoreexe',
            f'xcopy "{literal(new_int)}" "{literal(cur_int)}\\" /E /I /Q /Y /H >nul 2>&1',
            f'if errorlevel 1 goto rollback',
            f'if not exist "{literal(cur_int)}\\*" goto rollback',
            'copy /y "%SOURCE%" "%TARGET%" >nul 2>&1',
            'if errorlevel 1 goto rollback',
            'fc /b "%SOURCE%" "%TARGET%" >nul 2>&1',
            'if errorlevel 1 goto rollback',
            f'rmdir /s /q "{literal(new_int)}" >nul 2>&1',
            'del /q "%SOURCE%" >nul 2>&1',
            'goto done',
            ':rollback',
            f'if exist "{literal(cur_int)}" rmdir /s /q "{literal(cur_int)}" >nul 2>&1',
            f'if exist "{literal(old_int)}" move /y "{literal(old_int)}" "{literal(cur_int)}" >nul 2>&1',
            ':restoreexe',
            'if exist "%TARGET%" del /q "%TARGET%" >nul 2>&1',
            'move /y "%BACKUP%" "%TARGET%" >nul 2>&1',
            'echo The update could not be applied; the previous build was restored.',
            ':done',
        ]
    else:
        lines += [
            'copy /y "%SOURCE%" "%TARGET%" >nul 2>&1',
            'if errorlevel 1 goto rollback',
            'fc /b "%SOURCE%" "%TARGET%" >nul 2>&1',
            'if errorlevel 1 goto rollback',
            'del /q "%SOURCE%" >nul 2>&1',
            'goto done',
            ':rollback',
            'if exist "%TARGET%" del /q "%TARGET%" >nul 2>&1',
            'move /y "%BACKUP%" "%TARGET%" >nul 2>&1',
            'echo The update could not be applied; the previous build was restored.',
            ':done',
        ]
    if new_exe.parent.name.startswith(PREFIX):
        # Our own staging folder, now empty: rmdir without /s removes
        # nothing else, so a folder that still holds anything stays.
        lines.append(f'rmdir "{literal(new_exe.parent)}" >nul 2>&1')
    lines += [
        # The new build must start as a fresh top-level process, not as a
        # child of the onefile bootloader we were: without this its own
        # bootloader sees our _PYI_* variables and dies with "failed to
        # obtain executable path for parent process" (#136).
        'set "PYINSTALLER_RESET_ENVIRONMENT=1"',
        'start "" "%TARGET%"',
        'del /q "%~f0" >nul 2>&1',
    ]
    return "\r\n".join(lines) + "\r\n"


def clean_env() -> dict[str, str]:
    """Our environment minus PyInstaller's onefile bookkeeping.

    The onefile bootloader passes _PYI_* variables to the Python process it
    unpacks. Inherited by the swap script and then by the new exe, they made
    the new bootloader believe it was our child, and it quit with "Security
    validation failure: failed to obtain executable path for parent process"
    - every self-update relaunch died (#136). PYINSTALLER_RESET_ENVIRONMENT
    is PyInstaller's own switch for "start as a new top-level instance".
    """
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith("_PYI_")}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


# The version whose window has come up at least once on this machine.
SETTLED = "update_settled"


def old_build(current: Path) -> tuple[Path, Path]:
    """Where the swap keeps the previous build: the .exe and, for a
    one-folder build, its _internal folder."""
    return current.with_suffix(".old.exe"), current.parent / (INTERNAL + ".old")


def settle(version: str = "") -> list[Path]:
    """Remove the previous build once this one has proved it starts (#450).

    Called a few seconds after the main window is up. The first time a
    version gets here it only records that it did; the next start of the
    same version removes the .old.exe and _internal.old the swap left. So the
    old build is there for the whole of the new one's first run - long
    enough to notice a build that is broken and go back - and a new build
    that dies before its window appears never records itself, so the old
    one stays until one does. "Until the next update" left it there for
    good, and people read the leftover as a failed update.
    """
    from . import prefs
    current = running_exe()
    if current is None:
        return []
    version = version or update.VERSION
    if prefs.get(SETTLED) != version:
        prefs.set_(SETTLED, version)
        return []
    removed: list[Path] = []
    old, old_int = old_build(current)
    try:
        if old.is_file() and old != current:
            old.unlink()
            removed.append(old)
    except OSError:
        pass            # running, or held by a scanner: the next start tries again
    try:
        # Only once the .exe is gone: an old build somebody went back to and
        # is running right now needs its folder.
        if old_int.is_dir() and not old.exists():
            shutil.rmtree(old_int)
            removed.append(old_int)
    except OSError:
        pass
    return removed


def apply_and_restart(new_exe: Path) -> None:
    """Hand the swap to a helper batch file and quit so it can run."""
    current = running_exe()
    if current is None:
        raise UpdateError("Running from source, not a built executable - "
                          "nothing to replace.")
    if not Path(new_exe).is_file():
        # Staged more than a day ago and cleared since by another copy of
        # the tool (_prune_old_staging): say so, rather than restart into the
        # old build without a word.
        raise UpdateError("The downloaded update is no longer there - press "
                          "update again to fetch it.")

    bat = Path(tempfile.gettempdir()) / "dlss5-aio-update.bat"
    bat.write_text(swap_script(current, new_exe), encoding="utf8")

    creation = 0x00000008 | 0x08000000        # DETACHED_PROCESS | NO_WINDOW
    command = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "cmd.exe"
    # ".\" is required: current Windows builds no longer resolve a bare name from the cwd.
    subprocess.Popen([str(command), "/d", "/c", ".\\" + bat.name], creationflags=creation,
                     close_fds=True, cwd=str(Path(tempfile.gettempdir())),
                     env=clean_env())
    os._exit(0)
