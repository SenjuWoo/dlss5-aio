r"""Frame generation files the person downloaded themselves (#370).

Two community projects give RTX 20/30 cards frame generation on top of the
OptiScaler route, and neither can be fetched by this tool:

  * sdli1995/dlssg_for_sm86 - a version.dll proxy plus dlssg_sm86.ini beside
    the game's executable. Its releases carry no files and no licence, and
    the dll embeds NVIDIA's nvngx_dlssg.dll.
  * DLSS Enabler (Nexus mod 757) - its version.dll, renamed
    dlss-enabler-headless.dll, in the folder OptiScaler is in.

So the person picks the files they downloaded, and the tool does the part
that goes wrong by hand: the right name in the right place, a backup of
anything it replaces, a record in the install manifest, and all of it out
again on uninstall. The picked files are copied into the tool's own folder
(%LOCALAPPDATA%\dlss5-aio\own-fg) so "update all" can place them
again after the download folder has been cleaned.

Nothing here runs the files. They are identified by name and by strings in
their bytes, and a dll must be a 64-bit Windows binary.

Not tried on this project's own rig (an RTX 40, which has frame generation
of its own); SiTWulf ran the sm86 files on an RTX 3060 with this tool's
OptiScaler install. Labelled experimental everywhere it shows.
"""
from __future__ import annotations

import shutil
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import prefs


@dataclass(frozen=True)
class Recipe:
    key: str
    label: str
    # (name it is picked under, name it goes in under) - the first one is the dll
    files: tuple[tuple[str, str], ...]
    # strings (lower case) in the dll that say which project it is
    markers: tuple[bytes, ...]
    # names a picked dll may carry that already say which project it is
    names: tuple[str, ...] = ()
    tip: str = ""


RECIPES: dict[str, Recipe] = {
    "sm86": Recipe(
        "sm86", "dlssg_for_sm86 (RTX 30 frame generation)",
        (("version.dll", "version.dll"), ("dlssg_sm86.ini", "dlssg_sm86.ini")),
        (b"dlssg_sm86", b"dlssg_for_sm86"),
        tip="turn frame generation on in the game's own menu"),
    "enabler": Recipe(
        "enabler", "DLSS Enabler (headless)",
        (("version.dll", "dlss-enabler-headless.dll"),),
        (b"dlss-enabler", b"dlss enabler", b"dlssenabler"),
        names=("dlss-enabler-headless.dll",),
        tip="the game has to ship DLSS frame generation of its own"),
}

# dlssg_for_sm86's "alternatives\" folder: the same proxy under the names a
# game that never loads version.dll does load. Picked under one of these, it
# goes in under that name - renamed to version.dll it would never load, which
# is why the person picked it (its readme, 0.3.5). dinput8.dll is left out:
# REFramework and the ASI loaders take that name on these routes.
SM86_ALTERNATIVES = ("winmm.dll", "dxgi.dll", "d3d12.dll", "dbghelp.dll")
for _alt in SM86_ALTERNATIVES:
    RECIPES["sm86-" + _alt[:-4]] = Recipe(
        "sm86-" + _alt[:-4], f"dlssg_for_sm86 as {_alt} (RTX 30 frame generation)",
        ((_alt, _alt), ("dlssg_sm86.ini", "dlssg_sm86.ini")),
        RECIPES["sm86"].markers, tip=RECIPES["sm86"].tip)
del _alt

STORE = "own-fg"
UNTRIED = ("experimental - not run on this project's own card (an RTX 40); "
           "please share the result")
_READ_MAX = 96 * 1024 * 1024


class OwnFgError(Exception):
    pass


def store_dir(key: str = "") -> Path:
    base = Path(prefs.FILE).parent / STORE
    return base / key if key else base


def dests(key: str) -> list[str]:
    r = RECIPES.get(key)
    return [d for _, d in r.files] if r else []


def label(key: str) -> str:
    r = RECIPES.get(key)
    return r.label if r else key


def stored(key: str) -> dict[str, Path]:
    """{name it goes in under: the stored copy}, or {} when any is missing."""
    r = RECIPES.get(key)
    if r is None:
        return {}
    out = {}
    for src, dst in r.files:
        p = store_dir(key) / dst
        if not p.is_file():
            return {}
        out[dst] = p
    return out


def available() -> list[str]:
    """Recipes whose files are all in the store, in table order."""
    return [k for k in RECIPES if stored(k)]


def _is_x64_dll(p: Path) -> bool:
    try:
        with open(p, "rb") as f:
            head = f.read(0x40)
            if len(head) < 0x40 or head[:2] != b"MZ":
                return False
            (off,) = struct.unpack_from("<I", head, 0x3C)
            f.seek(off)
            sig = f.read(24)
        return len(sig) >= 24 and sig[:4] == b"PE\0\0" \
            and struct.unpack_from("<H", sig, 4)[0] == 0x8664 \
            and bool(struct.unpack_from("<H", sig, 22)[0] & 0x2000)   # IMAGE_FILE_DLL
    except (OSError, struct.error):
        return False


def _says(p: Path, markers: tuple[bytes, ...]) -> bool:
    try:
        if p.stat().st_size > _READ_MAX:
            return False
        low = p.read_bytes().lower()
    except OSError:
        return False
    wide = low.replace(b"\0", b"")
    return any(m in low or m in wide for m in markers)


def identify(picked: list[Path]) -> tuple[str, dict[str, Path]]:
    """Which project the picked files are, and {name it goes in under: file}.

    A partner file the person did not pick (dlssg_sm86.ini beside the
    version.dll they chose) is taken from the same folder."""
    picked = [Path(p) for p in picked if str(p)]
    if not picked:
        raise OwnFgError("no file was picked")
    folder = picked[0].parent
    by_name = {p.name.lower(): p for p in picked}

    def find(name: str) -> Path | None:
        p = by_name.get(name.lower())
        if p is None and (folder / name).is_file():
            p = folder / name
        return p

    dlls = [p for p in picked if p.suffix.lower() == ".dll"]
    if not dlls:
        ini = find("dlssg_sm86.ini")
        if ini is not None and find("version.dll") is not None:
            dlls = [find("version.dll")]
        else:
            raise OwnFgError("pick the .dll you downloaded (version.dll) - an .ini alone is not "
                             "enough")
    dll = dlls[0]
    if not _is_x64_dll(dll):
        raise OwnFgError(f"{dll.name} is not a 64-bit Windows dll")
    key = ""
    for r in RECIPES.values():
        if dll.name.lower() in r.names or _says(dll, r.markers):
            key = r.key
            break
    if not key and find("dlssg_sm86.ini") is not None:
        key = "sm86"
    if key == "sm86" and dll.name.lower() in SM86_ALTERNATIVES:
        key = "sm86-" + dll.name.lower()[:-4]
    elif key == "sm86" and not dll.name.lower().startswith("version"):
        # Renamed to version.dll it would load where the person chose it not
        # to (gate 2.0.7); dinput8.dll is REFramework's and the ASI loaders'.
        raise OwnFgError(
            f"{dll.name} is a dlssg_for_sm86 proxy this tool does not place - pick version.dll, "
            f"or one of {', '.join(SM86_ALTERNATIVES)} from its alternatives folder")
    if not key:
        raise OwnFgError(
            f"{dll.name} is neither dlssg_for_sm86 (version.dll with dlssg_sm86.ini beside it) nor "
            f"DLSS Enabler (its version.dll, or dlss-enabler-headless.dll) - the two this tool "
            f"knows how to place")
    r = RECIPES[key]
    out: dict[str, Path] = {}
    for src, dst in r.files:
        if src == r.files[0][0]:
            out[dst] = dll
            continue
        p = find(src)
        if p is None:
            # dlssg_for_sm86 keeps its alternatives\ proxies in a folder of
            # their own, without the ini, and one file dialog cannot pick from
            # two folders (gate 2.0.7).
            raise OwnFgError(f"{src} was not beside {dll.name}. Copy it from the "
                             f"{r.label.split(' (')[0].split(' as ')[0]} download into the "
                             f"folder {dll.name} is in, then pick {dll.name} again")
        out[dst] = p
    return key, out


def store(key: str, files: dict[str, Path]) -> Path:
    """Copy the picked files into the tool's own folder, replacing an older set."""
    if key not in RECIPES or set(files) != set(dests(key)):
        raise OwnFgError("The frame generation files do not match a known complete recipe.")
    from . import net
    from .installer import _atomic_copy
    with prefs.mutation_lock():
        d = net.inside(prefs.FILE.parent, str(store_dir(key).absolute()), absolute_ok=True)
        d.parent.mkdir(parents=True, exist_ok=True)
        new = Path(tempfile.mkdtemp(prefix=key + ".new-", dir=d.parent))
        old = None
        try:
            # Unique staging plus the profile lock prevents competing imports from deleting one another.
            for dst, src in files.items():
                _atomic_copy(Path(src), new / dst)
            if d.exists():
                old = Path(tempfile.mkdtemp(prefix=key + ".old-", dir=d.parent))
                old.rmdir()
                d.rename(old)
            try:
                new.rename(d)
            except OSError:
                if old is not None and old.is_dir() and not d.exists():
                    old.rename(d)
                raise
            if old is not None:
                shutil.rmtree(old)
        finally:
            if new.is_dir():
                shutil.rmtree(new)
        have = prefs.get(FORGOTTEN) or []
        if isinstance(have, list) and key in have:
            prefs.set_(FORGOTTEN, [k for k in have if k != key])
        return d


FORGOTTEN = "own_fg_forgotten"


def forgotten(key: str) -> bool:
    """Did the person press 'forget them' on this set (and not add it again)?

    The tool's copy is shared by every game, and a game whose record names
    the set rebuilt the choice from that record on its next visit, so the
    next install kept the files - 'forget them' undone (gate 2.0.7). A
    forgotten set reads as none there, and the install takes the files out."""
    try:
        return key in (prefs.get(FORGOTTEN) or [])
    except Exception:
        return False


def forget(key: str) -> None:
    if key not in RECIPES:
        raise OwnFgError("This frame generation recipe is not known.")
    from . import net
    with prefs.mutation_lock():
        folder = net.inside(prefs.FILE.parent, str(store_dir(key).absolute()), absolute_ok=True)
        if folder.exists():
            shutil.rmtree(folder)
        previous = prefs.get(FORGOTTEN)
        have = [k for k in (previous if isinstance(previous, list) else []) if isinstance(k, str)]
        if key not in have:
            prefs.set_(FORGOTTEN, have + [key])


def recorded(man: dict | None) -> tuple[str, list[str]]:
    """(recipe, names) an earlier install of ours placed, from its manifest."""
    rec = (man or {}).get("own_fg") or {}
    if not isinstance(rec, dict):
        return "", []
    files = [str(f) for f in (rec.get("files") or []) if isinstance(f, str)]
    return str(rec.get("recipe") or ""), files


def refusal(root: Path, key: str, opti_proxy: str, man: dict | None, route_changes: bool,
            is_optiscaler=None) -> str:
    """Why an install with these files must not start, or "".

    Asked at the top of install(), before the previous route is taken out,
    so a refusal leaves a working install as it was."""
    r = RECIPES.get(key)
    if r is None:
        return f"'frame generation files' names {key!r}, which this build does not know"
    kept_key, kept = recorded(man)
    have = stored(key)
    if not have and not (kept_key == key and not route_changes
                         and all((root / n).is_file() for n in dests(key))):
        return (f"The {r.label} files you added are no longer in the tool's folder "
                f"({store_dir(key)}). Add them again with 'add your own...' beside 'frame generation "
                f"files', or set it to none.")
    ours = {str(f).replace("\\", "/").lower() for f in ((man or {}).get("files") or [])
            if isinstance(f, str)}
    for n in dests(key):
        if opti_proxy and n.lower() == opti_proxy.lower():
            return (f"OptiScaler would load as {opti_proxy} here, the name "
                    f"{r.label.split(' (')[0].split(' as ')[0]} "
                    f"needs. Choose another name in 'loads as' and install again.")
        p = root / n
        if not p.is_file():
            continue
        if n.lower() in {k.lower() for k in kept}:
            continue                    # ours from last time
        if n.lower() in ours and route_changes:
            continue                    # the previous route's uninstall takes it out
        if is_optiscaler is not None and is_optiscaler(p):
            continue                    # OptiScaler moves its own other copies aside
        src = have.get(n)
        try:
            if src is not None and src.read_bytes() == p.read_bytes():
                continue                # the same file, put there by hand
        except OSError:
            pass
        what = "a file of this tool's from another option" if n.lower() in ours \
            else "a file this tool did not put there (another mod's, or a copy placed by hand)"
        return (f"{n} is already in the game folder and it is {what}, not the "
                f"{r.label.split(' (')[0].split(' as ')[0]} "
                f"file you added. Move it out of {root} and install again, or set 'frame generation "
                f"files' to none.")
    return ""


def remove_leftovers(root: Path, man: dict | None, keep: str, log=None) -> list[str]:
    """Take out what an earlier install placed that this one does not want.

    A reinstall on the same route skips the full uninstall, so without this
    the files stayed while the new record said the option was off. The file
    of the person's own that was under that name goes back. Returns the
    relative names removed (the caller drops them from `preinstalled`)."""
    log = log or (lambda *_: None)
    from . import net
    from .installer import BACKUP_SUFFIX, _atomic_copy, _displace, _record_hash
    _, names = recorded(man)
    want = {n.lower() for n in dests(keep)}
    gone: list[str] = []
    for n in names:
        if n.lower() in want:
            continue
        p = net.inside(root, n)
        bak = p.with_name(p.name + BACKUP_SUFFIX)
        net.inside(root, str(bak.absolute()), absolute_ok=True)
        backup_name = n + BACKUP_SUFFIX
        original = _record_hash(man or {}, backup_name)
        if original and not bak.is_file() and p.is_file() and net.sha256(p) == original:
            # A prior run restored the original but stopped before the new manifest was saved.
            gone.extend((n, backup_name))
            continue
        if original and (not bak.is_file() or net.sha256(bak) != original):
            raise OSError(f"The original backup of {n} is missing or changed; it was preserved.")
        written = _record_hash(man or {}, n)
        if p.is_file() and not written and not bak.is_file():
            log(f"      kept {n}: its ownership is unproven")
            continue
        if p.is_file() and (not written or net.sha256(p) != written):
            kept = _displace(p)
            log(f"      kept changed {n} as {kept.name}")
        if bak.is_file():
            _atomic_copy(bak, p)
            gone.append(n)
            if original:
                bak.unlink()
                gone.append(backup_name)
            else:
                log(f"      kept legacy {bak.name}: its original bytes cannot be verified")
            log(f"      put your own {n} back")
        elif p.is_file():
            p.unlink()
            gone.append(n)
    if gone:
        log(f"      frame generation files off: removed {', '.join(gone)}")
    return gone
