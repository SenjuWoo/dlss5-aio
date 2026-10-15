r"""Persistent preferences + locating a local renodx add-on.

renodx builds shared on Discord are not on the public mirror. Once the user
points at a file, remember it and use it as the default for every game.

Search order:
    1. previously chosen / remembered file
    2. the  renodx\  folder next to the executable    <- portable install
    3. Downloads / Desktop (up to one subfolder deep)
    4. none found -> download from the rhi-repo mirror
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path

FILE = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "dlss5-aio" / "settings.json"


def app_dir() -> Path:
    """Folder next to the executable (PyInstaller onefile aware)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


# One read-modify-write at a time. The watcher's worker, the DLSS worker and
# the Tk thread all call set_; two of them interleaved used to lose the
# first one's key, and a read that met a half-written file came back {} -
# which the next set_ then wrote back as a one-key file, installs list gone.
_lock = threading.RLock()
_mutation = threading.RLock()
# The text of the last settings read whole or written, per file (tests move
# FILE), so a file that cannot be read for a moment is not taken for an
# empty one. Text, not the dict: a caller that appends to a list it got
# must not change the copy kept.
_good: dict[str, str] = {}


@contextmanager
def mutation_lock():
    """Serialize profile changes across CLI/GUI processes; reads remain available."""
    from . import gamelock
    with _mutation, ExitStack() as stack:
        FILE.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + 15
        while True:
            try:
                stack.enter_context(gamelock.locked(FILE.parent))
                break
            except OSError as e:
                # Only OS lock contention is transient; path/permission errors stay errors.
                if e.__cause__ is None or time.monotonic() >= deadline:
                    raise
                time.sleep(.02)
        yield


def _last_good() -> dict:
    try:
        return json.loads(_good.get(str(FILE)) or "{}")
    except ValueError:
        return {}


def _read() -> tuple[dict, bool]:
    """(settings, readable). A missing file is readable and empty; a
    truncated, locked or hand-broken one, or JSON that is not an object,
    is not - and hands back the last good copy instead of {}."""
    key = str(FILE)
    try:
        text = FILE.read_text(encoding="utf8")
        data = json.loads(text)
    except FileNotFoundError:
        _good[key] = "{}"
        return {}, True
    except (OSError, ValueError):
        return _last_good(), False
    if not isinstance(data, dict):
        # a top-level [] or "x": every get() would raise AttributeError
        return _last_good(), False
    _good[key] = text
    return data, True


def load() -> dict:
    with _lock:
        return _read()[0]


def save(data: dict) -> None:
    with mutation_lock(), _lock:
        tmp = None
        try:
            FILE.parent.mkdir(parents=True, exist_ok=True)
            text = json.dumps(data, ensure_ascii=False, indent=2)
            # Written beside and moved over: a reader sees the old file or
            # the new one, never the half of one that was being written.
            tmp = FILE.with_name(f"{FILE.name}.{os.getpid()}.tmp")
            tmp.write_text(text, encoding="utf8")
            for attempt in range(6):
                try:
                    os.replace(tmp, FILE)
                    break
                except PermissionError:
                    # another process has it open for reading this moment
                    if attempt == 5:
                        raise
                    time.sleep(0.02)
            _good[str(FILE)] = text
        except OSError as e:
            from . import log
            log.write(f"settings were not saved; previous settings kept: {e}", "warn")
        finally:
            if tmp is not None:
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass


def get(key: str, default=None):
    return load().get(key, default)


def set_(key: str, value) -> None:
    with mutation_lock(), _lock:
        d, readable = _read()
        if not readable:
            # Keep unreadable personal edits even after this run saw a good copy.
            time.sleep(0.05)
            d, readable = _read()
            if not readable:
                try:
                    saved = FILE.with_name(f"{FILE.name}.unreadable.{time.time_ns()}")
                    saved.write_bytes(FILE.read_bytes())
                except OSError as e:
                    from . import log
                    log.write(f"settings were not saved; unreadable personal edits could not be preserved: {e}", "warn")
                    return
        d[key] = value
        save(d)


def is_renodx(path: Path) -> bool:
    """Is this actually a RenoDX DLSS 5 add-on (either family)?

    DLSS5-Feeder's own dlss5-feed.addon64 shares the extension, so we do not
    trust the name - we look for the signature string inside the binary.
    Installing the wrong file would break the install silently.
    """
    try:
        if not path.is_file() or path.stat().st_size < 200_000:
            return False
        data = path.read_bytes()
        if data[:2] != b"MZ":
            return False
        return b"RenoDX" in data and b"DLSS" in data
    except OSError:
        return False


def is_renodx_sf(path: Path) -> bool:
    """ShortFuse's renodx-dlss build, as opposed to Krish's renodx-dlss5.

    The two are not interchangeable: the SF build hooks D3D9/D3D11/D3D12
    itself and carries its own module name in the PE, so that is what is
    checked - not the file name, which people rename freely.
    """
    try:
        if not is_renodx(path):
            return False
        data = path.read_bytes()
        return (b"renodx-dlss.addon64" in data
                or "renodx-dlss.addon64".encode("utf-16-le") in data)
    except OSError:
        return False


def _candidates() -> list[Path]:
    hits: list[Path] = []

    # 2) the renodx folder next to the app (and the app folder itself)
    for d in (app_dir() / "renodx", app_dir()):
        if d.is_dir():
            try:
                hits += [f for f in d.glob("*.addon64") if f.is_file()]
            except OSError:
                pass

    # 3) Downloads / Desktop, one subfolder deep - people usually leave the
    #    file inside a folder rather than loose on the Desktop.
    home = Path.home()
    roots = [home / "Downloads", home / "Desktop",
             Path(os.environ.get("USERPROFILE", home)) / "Downloads"]
    for d in roots:
        if not d.is_dir():
            continue
        try:
            hits += [f for f in d.glob("*.addon64") if f.is_file()]
            for sub in d.iterdir():
                if sub.is_dir() and not sub.name.startswith("."):
                    try:
                        hits += [f for f in sub.glob("*.addon64") if f.is_file()]
                    except OSError:
                        continue
        except OSError:
            continue

    uniq: dict[Path, Path] = {}
    for f in hits:
        try:
            uniq.setdefault(f.resolve(), f)
        except OSError:
            continue
    good = [f for f in uniq.values() if is_renodx(f)]
    good.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return good


def find_renodx(sf: bool = False) -> tuple[Path | None, list[Path]]:
    """(file_to_use, all_candidates) of the requested family.

    A remembered choice wins, but only if it is of the right family - a
    remembered renodx-dlss5 must not be handed to the renodx-dlss route.
    """
    cands = [c for c in _candidates() if is_renodx_sf(c) == sf]
    saved = get("renodx_local")
    if saved:
        p = Path(saved)
        if p.is_file() and is_renodx_sf(p) == sf:
            others = [c for c in cands if c.resolve() != p.resolve()]
            return p, [p] + others
    return (cands[0] if cands else None), cands


def remember_renodx(path: Path | None) -> None:
    set_("renodx_local", str(path) if path else None)


# --- Vulkan installs ----------------------------------------------------
# The Vulkan layer is registered once for the whole user, not per game, so it
# must only be removed when the LAST Vulkan game that needs it is uninstalled.

def installs() -> list[str]:
    """Every folder this tool has set up (and not removed since)."""
    v = get("installs", [])
    return [str(x) for x in v] if isinstance(v, list) else []


def _change_paths(key: str, folder, add: bool) -> list[str]:
    """Keep the list read and its edit under one shared profile lock."""
    with mutation_lock():
        old = get(key, [])
        values = [str(x) for x in old] if isinstance(old, list) else []
        path = str(folder)
        same = lambda value: os.path.normcase(os.path.abspath(value)) == os.path.normcase(os.path.abspath(path))
        if add and any(same(value) for value in values):
            return values
        values = values + [path] if add else [value for value in values if not same(value)]
        set_(key, values)
        return values


def add_install(install_dir) -> None:
    _change_paths("installs", install_dir, True)


def drop_install(install_dir) -> None:
    _change_paths("installs", install_dir, False)


def vulkan_games() -> list[str]:
    v = get("vulkan_games", [])
    return v if isinstance(v, list) else []


def add_vulkan_game(install_dir) -> None:
    _change_paths("vulkan_games", install_dir, True)


def drop_vulkan_game(install_dir) -> list[str]:
    """Forget this game and return the ones still registered."""
    return _change_paths("vulkan_games", install_dir, False)


# The VR installs that rely on our OpenXR layer registration, so the last
# uninstall is the one that removes it.
def openxr_games() -> list[str]:
    v = get("openxr_games", [])
    return v if isinstance(v, list) else []


def add_openxr_game(install_dir) -> None:
    _change_paths("openxr_games", install_dir, True)


def drop_openxr_game(install_dir) -> list[str]:
    return _change_paths("openxr_games", install_dir, False)
