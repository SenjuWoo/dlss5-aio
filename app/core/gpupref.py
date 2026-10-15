r"""Windows' per-program graphics preference, for laptops with two GPUs (#427).

A laptop has the processor's own graphics and an NVIDIA card, and Windows
decides per program which one draws. NGX - and with it every DLSS 5 route -
exists only on the NVIDIA card, so a game or the feeder's 64-bit helper put
on the other one runs without it. Settings > System > Display > Graphics is
where a person sets this by hand; it lands here:

    HKCU\Software\Microsoft\DirectX\UserGpuPreferences
        <full path to the exe>  =  (REG_SZ) "GpuPreference=2;"

2 is "High performance". The value is shared: Windows keeps other per-program
switches in the same string ("SwapEffectUpgradeEnable=1;" from "Optimizations
for windowed games", Auto HDR), so this reads the string, adds or removes the
one token, and leaves every other token exactly as it found it.

Rules, because this is written outside the game folder:
  - only on a machine with an NVIDIA card AND another GPU. On one card the
    preference does nothing, so it is not written;
  - a GpuPreference the person already chose - any value - is left alone and
    never recorded as ours;
  - what was added is recorded in the install record, and uninstall takes the
    token back out only while it still says 2. If the person has changed it
    since, it is theirs now.
"""
from __future__ import annotations

import functools
from pathlib import Path

KEY = r"Software\Microsoft\DirectX\UserGpuPreferences"
TOKEN = "GpuPreference"
HIGH = "2"

_NVIDIA = 0x10DE
# The processor's own graphics, the other half of a hybrid machine.
_OTHER_GPU = {0x8086: "Intel", 0x1002: "AMD", 0x1022: "AMD"}


class _WinReg:
    """HKCU through winreg. Tests replace `backend` with a dict-backed one."""

    def get(self, name: str) -> str | None:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as k:
                value, kind = winreg.QueryValueEx(k, name)
        except OSError:
            return None
        return value if isinstance(value, str) else None

    def set(self, name: str, value: str) -> None:
        import winreg
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, KEY, 0,
                                winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)

    def delete(self, name: str) -> None:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0,
                                winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, name)
        except FileNotFoundError:
            pass


class Memory:
    """A registry that is a dict - for the test suites, which install for
    real and must never leave a value in the machine's own HKCU."""

    def __init__(self):
        self.values: dict[str, str] = {}

    def get(self, name: str) -> str | None:
        return self.values.get(name)

    def set(self, name: str, value: str) -> None:
        self.values[name] = value

    def delete(self, name: str) -> None:
        self.values.pop(name, None)


backend = _WinReg()


# ------------------------------------------------------------ the machine

def _dxgi_vendors() -> list[int] | None:
    """PCI vendor ids of the hardware adapters DXGI lists, or None.

    DXGI lists only adapters that are present and enabled; the registry's
    display class also keeps cards that were taken out years ago."""
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16),
                        ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]

        class DESC1(ctypes.Structure):
            _fields_ = [("Description", ctypes.c_wchar * 128),
                        ("VendorId", wintypes.UINT), ("DeviceId", wintypes.UINT),
                        ("SubSysId", wintypes.UINT), ("Revision", wintypes.UINT),
                        ("DedicatedVideoMemory", ctypes.c_size_t),
                        ("DedicatedSystemMemory", ctypes.c_size_t),
                        ("SharedSystemMemory", ctypes.c_size_t),
                        ("LuidLow", wintypes.DWORD), ("LuidHigh", wintypes.LONG),
                        ("Flags", wintypes.UINT)]

        # IID_IDXGIFactory1 {770aae78-f26f-4dba-a829-253c83d1b387}
        iid = GUID(0x770AAE78, 0xF26F, 0x4DBA,
                   (ctypes.c_ubyte * 8)(0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87))
        dxgi = ctypes.WinDLL("dxgi")
        factory = ctypes.c_void_p()
        if dxgi.CreateDXGIFactory1(ctypes.byref(iid), ctypes.byref(factory)) != 0:
            return None

        def method(obj, index, *argtypes):
            vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
            proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)
            return proto(vtbl[index])

        vendors: list[int] = []
        try:
            enum1 = method(factory, 12, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p))
            for i in range(16):
                adapter = ctypes.c_void_p()
                if enum1(factory, i, ctypes.byref(adapter)) != 0:
                    break                    # DXGI_ERROR_NOT_FOUND: the end
                try:
                    desc = DESC1()
                    if method(adapter, 10, ctypes.POINTER(DESC1))(adapter, ctypes.byref(desc)) == 0:
                        if not desc.Flags & 2:          # DXGI_ADAPTER_FLAG_SOFTWARE
                            vendors.append(int(desc.VendorId))
                finally:
                    method(adapter, 2)(adapter)         # Release
        finally:
            method(factory, 2)(factory)
        return vendors
    except Exception:
        return None


def _registry_vendors() -> list[int]:
    """The same answer from adapter names, when DXGI cannot be asked."""
    from . import gpu
    out: list[int] = []
    for name in gpu._adapters():
        low = name.lower()
        if gpu.sm_for_name(name) is not None or "nvidia" in low:
            out.append(_NVIDIA)
        elif "intel" in low:
            out.append(0x8086)
        elif any(k in low for k in ("radeon", "amd ", "advanced micro")):
            out.append(0x1002)
    return out


@functools.lru_cache(maxsize=1)
def other_gpu() -> str:
    """"Intel" / "AMD" when an NVIDIA card shares this machine with another
    GPU (a laptop, or a desktop with the processor's graphics on), else ""."""
    vendors = _dxgi_vendors()
    if vendors is None:
        vendors = _registry_vendors()
    if _NVIDIA not in vendors:
        return ""
    for v in vendors:
        if v in _OTHER_GPU:
            return _OTHER_GPU[v]
    return ""


def hybrid() -> bool:
    return bool(other_gpu())


# ------------------------------------------------------------ the value

def _tokens(value: str | None) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for part in str(value or "").split(";"):
        part = part.strip()
        if not part:
            continue
        k, _, v = part.partition("=")
        out.append((k.strip(), v.strip()))
    return out


def _join(tokens: list[tuple[str, str]]) -> str:
    return "".join(f"{k}={v};" for k, v in tokens)


def chosen(exe) -> str | None:
    """The GpuPreference set for this exe, or None when there is none."""
    for k, v in _tokens(backend.get(str(exe))):
        if k.lower() == TOKEN.lower():
            return v
    return None


def _same(a, b) -> bool:
    return str(a).replace("/", "\\").lower() == str(b).replace("/", "\\").lower()


def apply(exes, before=()) -> tuple[list[dict], list[str]]:
    """Set High performance for each exe. Returns (records, theirs).

    A record is {"exe", "was", "wrote"}: the string before this tool touched
    it (None when there was no value) and the string it wrote, so uninstall
    can put the value back byte for byte while nobody has changed it since.
    `before` holds the records of an earlier install; our own 2 found again
    on a reinstall keeps its first record instead of being read as the
    person's choice. `theirs` names the exes where the person had already
    chosen, which are left exactly as they were."""
    records: list[dict] = []
    theirs: list[str] = []
    for exe in exes:
        path = str(exe)
        have = chosen(path)
        if have is not None:
            old = next((r for r in before or () if isinstance(r, dict)
                        and _same(r.get("exe", ""), path)), None)
            if have == HIGH and old is not None:
                records.append(old)     # our own 2 from the last install
            else:
                theirs.append(path)     # chosen by the person, or changed since
            continue
        was = backend.get(path)
        tokens = _tokens(was)
        tokens.append((TOKEN, HIGH))
        wrote = _join(tokens)
        try:
            backend.set(path, wrote)
        except OSError:
            continue                    # not written, so not recorded
        records.append({"exe": path, "was": was, "wrote": wrote})
    return records, theirs


def restore(records) -> list[str]:
    """Take our preference back out. Returns the exes that were changed.

    Untouched since the install: the old string goes back exactly (or the
    value goes, when there was none). Something else in the string changed
    since - Windows toggling Auto HDR, say: only our token comes out. Our
    token changed or gone: the person's now, left alone."""
    done: list[str] = []
    for rec in records or ():
        if not isinstance(rec, dict) or not rec.get("exe"):
            continue
        path = str(rec["exe"])
        now = backend.get(path)
        tokens = _tokens(now)
        mine = [t for t in tokens if t[0].lower() == TOKEN.lower()]
        if not mine or mine[-1][1] != HIGH:
            continue
        was = rec.get("was")
        if now == rec.get("wrote"):
            if isinstance(was, str) and was:
                backend.set(path, was)
            else:
                backend.delete(path)
        else:
            rest = [t for t in tokens if t[0].lower() != TOKEN.lower()]
            if rest:
                backend.set(path, _join(rest))
            else:
                backend.delete(path)
        done.append(path)
    return done
