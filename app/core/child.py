r"""Starting somebody else's program from this one.

The release is a PyInstaller onefile: its bootloader unpacks into
%TEMP%\_MEIxxxxx and calls SetDllDirectoryW on that folder, so this process
finds its own DLLs. Windows hands that setting to every child process, and
the folder then sits in the child's search order AHEAD of System32: a game
started with 'play' found OUR vcruntime140.dll first. RPCS3 checks where its
runtime came from and refuses to start (#287):

    The module vcruntime140.dll was incorrectly installed at
    '...\AppData\Local\Temp\_MEI000083a02\VCRUNTIME140.dll'

A program that does not check simply runs on a C runtime, a zlib or a
libcrypto it was not built against. So the programs that bring no runtime
of their own - a game, the video player, yt-dlp, ffmpeg, ffprobe - start
through popen() and run() here (Windows' own tools - tar, tasklist,
powershell, cmd, explorer - and 7-Zip beside its own DLLs do not): the DLL
directory is lifted for the moment the child is created and put back, and
the bootloader's _PYI_* variables stay behind (selfupdate.clean_env, #136).

Running from source there is no bootloader: the DLL directory is left alone,
and only the environment is the cleaned copy.

LIMITS. While the directory is lifted - the length of one CreateProcess,
longer under an antivirus scan - a LoadLibrary by bare name in THIS process
does not see the unpack folder; everything the window needs is loaded long
before anyone presses play. TCL_LIBRARY and TK_LIBRARY, set by PyInstaller's
Tk hook, still reach the child. What Windows itself starts for us -
webbrowser.open, os.startfile, explorer - does not come through here.
"""
from __future__ import annotations

import subprocess
import sys
import threading

_lock = threading.Lock()


def _set_dll_directory(path) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
        k32.SetDllDirectoryW.restype = ctypes.c_int
        return bool(k32.SetDllDirectoryW(path))
    except Exception:
        return False


def _start(args, kw) -> subprocess.Popen:
    from . import selfupdate
    if kw.get("env") is None:               # an explicit None would inherit the lot
        kw["env"] = selfupdate.clean_env()
    ours = getattr(sys, "_MEIPASS", None) if getattr(sys, "frozen", False) else None
    if not ours:
        return subprocess.Popen(args, **kw)
    with _lock:
        lifted = _set_dll_directory(None)       # None: back to Windows' default search order
        try:
            return subprocess.Popen(args, **kw)
        finally:
            if lifted:
                _set_dll_directory(str(ours))


def run(args, *, input=None, capture_output=False, timeout=None, check=False,
        **kw) -> subprocess.CompletedProcess:
    """subprocess.run for a program that is not this tool.

    The DLL directory is lifted while the program is CREATED, not while it
    is waited for: the first version held the lock for the whole of an
    `ffmpeg -list_devices` (up to 20 s behind a hung camera driver), and
    'open player' on the Tk thread waited behind it with the window frozen.
    This is the body of subprocess.run. LIMIT: capture_output together with
    an explicit stdout/stderr is not refused as the original refuses it.
    """
    if capture_output:
        kw["stdout"] = kw["stderr"] = subprocess.PIPE
    if input is not None:
        kw["stdin"] = subprocess.PIPE
    with _start(args, kw) as p:
        try:
            out, err = p.communicate(input, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            p.kill()
            e.stdout, e.stderr = p.communicate()
            raise
        except BaseException:
            p.kill()
            raise
        rc = p.poll()
    if check and rc:
        raise subprocess.CalledProcessError(rc, p.args, output=out, stderr=err)
    return subprocess.CompletedProcess(p.args, rc, out, err)


def popen(args, **kw) -> subprocess.Popen:
    """subprocess.Popen for a program that is not this tool.

    `env` defaults to this process's without the bootloader's bookkeeping.
    The lock is for the DLL directory, which is one value for the whole
    process: two launches at once must not put back each other's None.
    """
    return _start(args, kw)
