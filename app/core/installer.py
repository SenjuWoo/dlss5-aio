r"""Install engine: 64-bit, 32-bit and DX9 paths.

64-bit layout (next to the game executable):
    <proxy>.dll                 ReShade64.dll  (dxgi.dll or opengl32.dll)
    dlss5-feed.addon64          (feeder route)
    renodx-dlss5.addon64        (feeder / native / bridge routes)
    renodx-dlss.addon64         (renodx route - ShortFuse's SF build)
    nvngx.dll.addon64           (upstream route - neural-upstream, no renodx add-on)
    standalone-dlssnr.addon64   (standalone route - kibblerz's own feed, no renodx add-on)
    nvngx.dll                   (standalone route - the add-on's caller-identity bridge)
    nvngx_dlssnr.dll
    nvngx_dlss.dll
    nvngx_dlssg.dll             (standalone route - frame generation)
    ReShade.ini / ReShadePreset.ini / dlss5-feed.cfg
    reshade-shaders/Shaders/{headers, DLSS5_Feed.fx, lumenite_*.fx}
    reshade-shaders/Shaders/{DLSS5_AIO_Feed.fx, vort_Motion.fx}   (standalone)
    reshade-shaders/Shaders/include/lumenite_*.fxh
    reshade-shaders/Shaders/Includes/vort_*.fxh                    (standalone)
    reshade-shaders/Textures/lumenite_bluenoise256.png
    reshade-shaders/Textures/vort_BlueNoise.png                    (standalone)

32-bit: a 32-bit process cannot load 64-bit NGX, so a helper process is
needed. The game gets 32-bit ReShade + addon32; host64/ holds its own 64-bit
ReShade and all the DLSS parts.

DX9: DXVK translates to Vulkan first, then the 32-bit path applies.

REMIX: none of the above. The mod's own Remix runtime does the work, so the
only things written are inside its `.trex` folder -

    .trex/nvngx_dlssnr.dll      the neural-rendering snippet
    .trex/d3d9.dll              only when swapping the runtime itself
    .trex/remix_nvngx.dll       its caller-identity bridge, same swap

- plus one line in the game's rtx.conf. No ReShade, no add-on, no proxy DLL:
a ReShade proxy in a Remix game's folder crashes it before it draws.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import struct
import tempfile
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

from . import (emulators, anticheat, dlss, dxvk, feedcfg, gamelock, games, gpu, gpupref, mfg, net,
               optiscaler, ownfg, pe, prefs, reengine, refw, remix, reshade_ini,
               sources, update, vulkan)
# Imported by name as well: inside the Options class body the field
# `dlss: str | None` shadows the module, so `dlss.FEEDER` would read the
# field's default (None) instead of the module attribute.
from .dlss import BRIDGE, FEEDER, NATIVE, OPTI, STANDALONE, UPSTREAM
from .dlss import RENODX as ROUTE_RENODX   # the route; RENODX below is a file name
from .dlss import REMIX as ROUTE_REMIX

MANIFEST = "dlss5-autopilot.json"

FEEDER_ADDON64 = "dlss5-feed.addon64"
FEEDER_ADDON32 = "dlss5-feed.addon32"
FEEDER_HOST = "dlss5-feed-host64.exe"
FEEDER_FX = "DLSS5_Feed.fx"
RENODX = "renodx-dlss5.addon64"
# ShortFuse's add-on - the "SF" build - which hooks D3D9/D3D11/D3D12 itself.
RENODX_SF = "renodx-dlss.addon64"

UPSTREAM_ADDON = "nvngx.dll.addon64"
# kibblerz's DLSS5-Reshade-AIO. The add-on runs the whole pipeline on a
# private NGX session; the plain nvngx.dll beside it is its caller-identity
# bridge - the same "the caller's path must contain nvngx.dll" rule that
# neural-upstream satisfies with its file name. Without it the add-on logs
# "required private runtime dependency missing" and does nothing. Three
# files with nvngx.dll in the name, three routes: nvngx.dll.addon64
# (upstream), nvngx.dll (standalone), nvngx.dll_dlssnr.dll (OptiScaler).
STANDALONE_ADDON = "standalone-dlssnr.addon64"
STANDALONE_BRIDGE = "nvngx.dll"
STANDALONE_FX = "DLSS5_AIO_Feed.fx"
DLSSG = "nvngx_dlssg.dll"
# Ray reconstruction. Only ever swapped, never added: a game that does
# not ship it does not ask for it, and dropping one in changes nothing.
DLSSD = "nvngx_dlssd.dll"
# Vortigern's optical-flow shader the standalone add-on schedules for real
# motion vectors; without it the add-on runs on zero-motion guides.
VORT_FX = "vort_Motion.fx"
VORT_TEXTURE = "vort_BlueNoise.png"

# Other hooks on the same NGX entry points. A game with one of these plus
# our add-on gets two things rewriting the same calls: flicker, frame-gen
# multipliers greyed out, or nothing at all (Cyberpunk 2077 with OptiScaler
# and a frame-gen unlocker, issue #3). Not refused - stated.
OTHER_NGX_HOOKS = ("OptiScaler.ini", "nvngx.ini", "fakenvapi.ini",
                   "dlss-enabler.dll", "dlss-enabler-upscaler.dll",
                   "nvngx-wrapper.dll", "dlssg_to_fsr3_amd_is_better.dll",
                   "dlssg_to_fsr3.ini", "nvngx.dll_dlssnr.dll",
                   # sdli1995/dlssg_for_sm86: frame generation on RTX 30,
                   # shipped as a version.dll proxy with DLSSG 310.1 inside
                   # it. That is the same file name the MFG unlock's loader
                   # and one of the OptiScaler proxies use, so a folder
                   # holding both has two things in one slot - and the .ini
                   # is what says which one is there.
                   "dlssg_sm86.ini",
                   # xenmods/DLSSNR-Cost-Scaler: a proxy that replaces
                   # nvngx_dlssnr.dll with its own and adds a model-resolution
                   # dial. It brings an add-on of its own, so a folder with
                   # both has two things hooking the model and the runtime
                   # beside the game is not the one this tool put there.
                   "dlssnr-companion.addon64", "nvngx_dlssnr.ini",
                   # NGX loads a plain nvngx.dll from the game folder before
                   # the driver's: an OptiScaler installed by hand under its
                   # old name, or the standalone route's caller bridge.
                   STANDALONE_BRIDGE)


def other_ngx_hooks(root: Path, path: str = "") -> list[str]:
    """Files in the folder that belong to another DLSS/NGX hook.

    `path` is the route being looked at: the standalone route's own nvngx.dll
    is part of that route, and a foreign hook on every other.
    """
    found: list[str] = []
    try:
        names = {f.name.lower(): f.name for f in root.iterdir() if f.is_file()}
    except OSError:
        return found
    # Frame generation files the person added through this tool (#370) are
    # on its own record: dlssg_sm86.ini is on the list above for the copy
    # somebody put in by hand, not for this one.
    try:
        for n in ownfg.recorded(_previous_manifest(root))[1]:
            names.pop(n.lower(), None)
    except Exception:
        pass
    for n in OTHER_NGX_HOOKS:
        if path == STANDALONE and n.lower() == STANDALONE_BRIDGE.lower():
            continue
        if n.lower() in names:
            found.append(names[n.lower()])
    # A ReShade add-on we did not write - another RenoDX build, say - is
    # loaded by ReShade regardless and hooks the same swap chain.
    ours = {"dlss5-feed.addon64", "dlss5-bridge.addon64",
            RENODX.lower(), RENODX_SF.lower(), UPSTREAM_ADDON.lower(),
            STANDALONE_ADDON.lower(), "rtx40mfg-ui.addon64"}
    for low, orig in names.items():
        if low.endswith(".addon64") and low not in ours:
            found.append(orig)
    # A name that is both in OTHER_NGX_HOOKS and an add-on of somebody
    # else's was counted twice, and the warning read
    # "dlssnr-companion.addon64, ..., dlssnr-companion.addon64" (#190).
    return list(dict.fromkeys(found))


def hook_warning(root: Path, path: str) -> str:
    """One sentence, or "" when the folder is clean."""
    if path == OPTI:
        found = [n for n in other_ngx_hooks(root) if n.lower() != "optiscaler.ini"
                 and n.lower() != "nvngx.dll_dlssnr.dll"]
    else:
        found = other_ngx_hooks(root, path)
    if not found:
        return ""
    return (f"another DLSS hook is already in this folder ({', '.join(found[:5])}"
            f"{', ...' if len(found) > 5 else ''}). Two things rewriting the "
            f"same NGX calls means flicker, greyed-out frame-gen multipliers "
            f"or nothing happening. If it misbehaves, remove that mod (or "
            f"uninstall this) and try one at a time.")
DLSSNR = "nvngx_dlssnr.dll"
DLSS = "nvngx_dlss.dll"
HOST_DIR = "host64"

# The RTX Remix route. Nothing of ours goes beside the executable: the
# runtime lives in the mod's .trex folder and everything we write goes in
# there, plus one line in rtx.conf.
REMIX_RUNTIME = remix.RUNTIME_DLL          # .trex/d3d9.dll - the runtime
REMIX_NVNGX = remix.REMIX_NVNGX            # the caller-identity bridge

SHADERS = Path("reshade-shaders") / "Shaders"
INCLUDE = SHADERS / "include"
VORT_INCLUDE = SHADERS / "Includes"    # VORT's own folder name, its .fx includes it
TEXTURES = Path("reshade-shaders") / "Textures"

BRIDGE_ADDON = "dlss5-bridge.addon64"
# The bridge's 1.0.x name. ReShade loads it as a separate add-on, so every
# ReShade route takes it out of the way (#439).
LEGACY_BRIDGE_ADDON = "dlss5-dx11-bridge.addon64"
BRIDGE_CFG = "dlss5-bridge.cfg"

BACKUP_SUFFIX = ".dlss5-autopilot-backup"
# A backup of a runtime a mod has since replaced with its own: kept, but
# under a name uninstall does not restore (it would put the older one back).
SUPERSEDED_SUFFIX = ".dlss5-autopilot-superseded"

# Files a game ships that break the neural pass when Windows loads them in
# preference to System32's copy. They are renamed, not deleted, and the
# manifest records it so uninstall puts them back. MPC-HC and a number of
# older games bundle a D3DCompiler_47.dll that rejects the cs_5_1 target the
# DLSS 5 add-on compiles with; the feed then reports frames delivered while
# neural rendering silently does nothing.
SIDELINE = ("d3dcompiler_47.dll",)
SIDELINE_SUFFIX = ".dlss5-off"
# An add-on from another route, moved out of the way. A separate suffix on
# purpose: BACKUP_SUFFIX means "put this back on uninstall", which is the one
# thing that must not happen to a file that was causing a conflict.
ORPHAN_SUFFIX = ".dlss5-autopilot-orphan"

# Written by the components while the game runs, so they exist only because
# something was installed - but they are created after the install, which
# means the manifest has never heard of them and uninstall used to leave every
# one behind. Each is regenerated from scratch on the next launch, so removing
# them loses nothing even in the unlikely case one predates us.
RUNTIME_ARTIFACTS = (
    "ReShade.log",              # ReShade, every launch
    "dlss5-feed.log",           # the feeder add-on
    "dlss5-feed-host.log",
    "dlss5-bridge.log",
    "OptiScaler.log",
    "nvngx.log",                # NGX itself
    "nvngx_dlssnr.log",
    "nvngx_dlss.log",
)

# OptiScaler keeps its logs in a folder of its own. A game could plausibly
# have a folder by that name, so only OptiScaler's own files are taken out of
# it, and the folder itself only if that empties it.
OPTI_LOG_DIR = "Logs"

# The project was called "dlss5kur" up to v1.1. Anyone upgrading has installs
# recorded under the old names; without these the new build would not see them
# and Uninstall would leave files behind.
LEGACY_MANIFESTS = ("dlss5kur-kurulum.json", "dlss5-installer.json")
LEGACY_BACKUP_SUFFIXES = (".dlss5kur-yedek", ".dlss5-installer-backup")


class InstallError(Exception):
    pass


@dataclass
class Options:
    provider: int = 3                       # DLSS5_MV_PROVIDER
    renodx: str | None = sources.RENODX_DEFAULT
    renodx_local: Path | None = None        # user's own build
    dlssnr: str | None = None               # None = auto-pick for this GPU
    dlss: str | None = None                 # None = newest
    # Ray reconstruction, for a game that already ships it: "" leaves the
    # game's own alone, a label swaps in that build. Never installed into a
    # game that does not have one - nothing would ask for it.
    dlssd: str = ""
    keep_game_dlss: bool = True             # leave the game's own nvngx_dlss.dll alone
    feed: dict = field(default_factory=dict)   # dlss5-feed.cfg settings
    ignore_gpu_mismatch: bool = False
    path: str = FEEDER                      # native / bridge / feeder
    opti_proxy: str = ""                    # "" = pick a free name for this game
    opti_build: str = ""                    # key of optiscaler.BUILDS
    reshade_proxy: str = ""                 # "" = choose from the API
    native_dlss: bool = False               # game ships its own DLSS
    # "fsr" / "xess" / "": the upscaler a game WITHOUT DLSS ships. On the
    # OptiScaler route its calls become OptiScaler's input and DLSS runs in
    # their place, so the tool also puts a nvngx_dlss.dll in the folder.
    upscaler: str = ""
    # The feeder's pre-releases are where support for the newest DLSS 5
    # add-on generations lands first. "newest release" means the release
    # line (#325, #348); this asks for the beta line instead.
    feeder_prerelease: bool = False
    feeder_tag: str = ""                    # "" = stable or newest pre-release
    dxvk: bool = False                      # run a D3D11 game on Vulkan via DXVK
    nr: dict = field(default_factory=dict)  # OptiScaler [DlssNr] settings
    # OptiScaler route, D3D12: FSR 3.1 frame generation from the libraries
    # OptiScaler ships, on any card. Off by default - it adds latency and
    # every game's HUD reacts differently.
    fg: bool = False
    # ReShade routes, RTX 40, D3D12/Vulkan games that ship DLSS Frame
    # Generation: dashdogy's RTX40MFG-Unlock for 3x/4x multipliers. Research
    # software; off by default and only offered where mfg.applies() says so.
    mfg: bool = False
    # ReShade routes: register ReShade's OpenXR layer as well, so the pass
    # runs on the image the VR headset shows rather than the desktop mirror
    # (#33). Global for the user, like the Vulkan layer. Not tried with a
    # headset by the author.
    vr: bool = False
    # REMIX route: replace the mod's Remix runtime with a community build
    # that HAS the neural pass. Off by default and deliberately opt-in - a
    # mod's runtime is often a fork carrying game-specific fixes, and
    # swapping it can break the mod itself.
    remix_swap: bool = False
    # OptiScaler route: frame generation files the person downloaded
    # themselves (#370) - a key of ownfg.RECIPES, "" for none. The files
    # come from the tool's own copy (ownfg.store_dir), never a download.
    own_fg: str = ""
    # A machine with an NVIDIA card and another GPU (a laptop): set Windows'
    # graphics preference to High performance for the game and our helper,
    # so neither lands on the card NGX does not exist on (#427). Nothing is
    # written on a machine with one GPU, or where the person already chose.
    gpu_pref: bool = True


@dataclass
class Report:
    written: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # component name -> version installed, recorded in the manifest so a
    # game set up weeks ago can be told what has moved on since.
    components: dict = field(default_factory=dict)
    # Relative paths a PREVIOUS install of ours put in this folder. They must
    # never be backed up as "the game's own file" - see _backup.
    preinstalled: set = field(default_factory=set)
    # Game files renamed out of the way (see SIDELINE), relative paths.
    sidelined: list[str] = field(default_factory=list)
    # REMIX route: {"conf", "key", "trex", "flavour"}. rtx.conf is the user's
    # file and is never listed in `written` (uninstall deletes those); the
    # key is recorded here so uninstall can take exactly that line back out.
    remix: dict = field(default_factory=dict)
    # Windows graphics preferences this install added (gpupref records), or
    # None when the step did not run - _write_manifest then carries the
    # earlier record forward, so a failed install never loses one.
    gpu_pref: list | None = None
    game_root: Path | None = None
    sidelined_hashes: dict = field(default_factory=dict)
    hashes: dict = field(default_factory=dict)
    checkpoint: object | None = None
    layer_pending: bool = False


# ---------------------------------------------------------------- reliability

# Measured on real games, not guessed. DLSS 5 feeding was designed around
# DXGI; everything else is a bolt-on and fails far more often.
STABLE, BETA, EXPERIMENTAL = "stable", "beta", "experimental"

def reliability(g: games.Game, path: str = FEEDER,
                upscaler: str = "", remix_swap: bool = False) -> tuple[str, str]:
    """(level, explanation) - how likely this route is to actually work.

    `upscaler` is set on the OptiScaler route when the game has no DLSS and
    OptiScaler is redirecting its FSR/XeSS calls instead - one more hook
    that has to land, so it says so.

    `remix_swap` is set on the REMIX route when the mod's own Remix runtime
    is being replaced, which is a different risk from merely switching the
    neural pass on in a runtime that already has one.
    """
    if path == ROUTE_REMIX:
        if remix_swap:
            return EXPERIMENTAL, (
                "The Remix runtime installed by this mod has no neural pass, "
                "so it is being replaced with a community build that does. "
                "That build is not the mod author's: a mod's runtime is often "
                "a fork carrying fixes for this exact game, and swapping it "
                "can break them. Its author reports it running in Portal "
                "with RTX (RTX 4090, Linux); it has not been run on this "
                "tool's test machine. Reports say the game did not start "
                "after the swap, or stopped at the Remix console. The old "
                "one is backed up and "
                "'uninstall' puts it back.")
        return BETA, (
            "The Remix runtime already installed here has the DLSS 5 neural "
            "pass built in; all this does is put nvngx_dlssnr.dll beside it "
            "and switch the pass on in rtx.conf. Nothing is injected into "
            "the game. Only a handful of Remix mods ship a runtime "
            "with the pass at all.")
    if g.api == "DX10":
        return BETA, ("Direct3D 10 through the feeder's private D3D11 relay "
                      "device (feeder 0.13.1 and newer). A D3D10 game "
                      "installs like a D3D11 one.")
    if path == NATIVE:
        return STABLE, ("The game's own DLSS is hooked directly - no synthetic "
                        "contract, no motion-vector shaders, and your in-game "
                        "DLSS quality setting still applies.")
    if path == UPSTREAM:
        return BETA, ("neural-upstream runs the network at render resolution, "
                      "before the game's own DLSS. Its author tested two "
                      "games (GTA V Enhanced, Bright Memory Infinite).")
    if path == STANDALONE:
        return EXPERIMENTAL, ("standalone-dlssnr does everything itself - own "
                              "feed, DLAA or DLSS Super Resolution, frame "
                              "generation - and shows the result through a "
                              "topmost window of its own. That window trick "
                              "is the fragile part: resolution or display-mode "
                              "changes need a restart, and some games hang at "
                              "start. Few games tested.")
    if path == ROUTE_RENODX:
        if g.api == "DX9":
            return BETA, ("64-bit DirectX 9 through the renodx-dlss add-on: it "
                          "evaluates the presentation backbuffer with no "
                          "motion vectors, so expect a softer result.")
        return EXPERIMENTAL, ("The renodx-dlss add-on hooks the game in-process. "
                              "Reported not working in many "
                              "games. Try the recommended route first.")
    if path == OPTI and upscaler:
        return BETA, ("FSR/XeSS redirected into DLSS by OptiScaler - works in "
                      "many games, not all. OptiScaler has to hook the game's "
                      f"{'FSR 2/3' if upscaler == 'fsr' else 'XeSS'} calls "
                      "first; a game that links its upscaler statically gives "
                      "it nothing to hook, and the feeder is the fallback."
                      + (" On D3D11 it needs a bridged upscaler (FSR on D3D12) "
                         "in place of DLSS." if g.api == "DX11" else ""))
    if path == OPTI:
        return BETA, ("OptiScaler replaces the upscaler and runs the model over "
                      "its output. The game must already use DLSS; the author "
                      "tested RTX 50 only, older cards run the community runtime."
                      + (" On D3D11 it needs a bridged upscaler (FSR on D3D12) "
                         "in place of DLSS." if g.api == "DX11" else ""))
    if path == BRIDGE:
        if g.api == "Vulkan":
            return BETA, ("The bridge mirrors the game's DLSS contract onto a "
                          "private D3D12 session - the route for Vulkan games "
                          "that ship DLSS; the feeder is the fallback.")
        return BETA, ("The bridge reproduces the DLSS contract on a private "
                      "D3D12 session. Fewer moving parts than the feeder, but "
                      "less proven.")
    if g.api == "DX8":
        return EXPERIMENTAL, (
            "DirectX 8 through DXVK's d3d8.dll, then the same path as a 32-bit "
            "DirectX 9 game. It has not been run here - if you try it, "
            "'share the result' under "
            "'did it work?' tells the next person how it went.")
    if g.api == "DX9":
        return EXPERIMENTAL, (
            "DirectX 9 is the least reliable path. The game runs through "
            "DXVK translation and then the 32-bit helper process; the "
            "DLSS feature frequently fails to create on top of that. Expect "
            "it not to work.")
    if g.api == "Vulkan":
        return BETA, ("Vulkan works through ReShade's layer registration and "
                      "the component's own D3D12 interop. Newer than the "
                      "DirectX paths, and it has met fewer real games.")
    if g.bitness == 32:
        return EXPERIMENTAL, (
            "32-bit games go through a cross-process helper (host64). "
            "Upstream marks this beta and it often fails to start the DLSS "
            "feature.")
    if g.api == "OpenGL":
        return BETA, (
            "OpenGL needs interop extensions the driver may not expose to "
            "this game, and the game must render on the NVIDIA card. Verified "
            "on six games with VORT motion vectors and add-on 4.60, which the "
            "tool applies.")
    if g.api in ("DX11", "DX12", "Unknown"):
        return STABLE, "DirectX 11/12 is the path DLSS 5 feeding is built around."
    return BETA, "Untested path."


# ---------------------------------------------------------------- helpers

def _is_reshade(path: Path) -> bool:
    """A ReShade proxy DLL carries the literal string "ReShade" and is >1 MB."""
    try:
        if not path.is_file() or path.stat().st_size < (1 << 20):
            return False
        return b"ReShade" in path.read_bytes()
    except OSError:
        return False


# The names ReShade can be installed under. It is the same DLL each time; the
# name decides which system library it stands in for, and therefore when in
# start-up the game loads it.
#
# This matters more than it looks. A game that imports dxgi.dll statically -
# MGS V does - has our proxy loaded by Windows before any of its own code
# runs, which is the earliest and least forgiving moment. One that loads dxgi
# later through LoadLibrary - Total War: Warhammer III does - picks it up when
# it is good and ready. When a game will not start, changing the name it
# comes in under is the first thing to try.
RESHADE_PROXIES = ("dxgi.dll", "d3d11.dll", "d3d12.dll", "d3d10.dll",
                   "d3d9.dll", "opengl32.dll")

RESHADE_PROXY_HELP = {
    "dxgi.dll": "default for Direct3D 10/11/12",
    "d3d11.dll": "try this if a D3D11 game will not start with dxgi",
    "d3d12.dll": "D3D12 alternative to dxgi",
    "d3d10.dll": "D3D10 only",
    "d3d9.dll": "DirectX 9 (rarely useful - DX9 goes through DXVK)",
    "opengl32.dll": "the only option for OpenGL",
}
# dinput8.dll is NOT offered here: it used to be, as a ReShade proxy name to
# try on RE Engine games, but that was the wrong fix. The real one is
# REFramework, a separate mod that installs itself under that exact name and
# patches around RE Engine's own tamper checks - see refw.py. ReShade
# claiming the same name would collide with it.


def _proxy_name(api: str, chosen: str = "") -> str:
    if api == "Vulkan":
        # No proxy DLL at all: ReShade reaches a Vulkan game as a layer.
        return VULKAN_LAYER
    if chosen in RESHADE_PROXIES:
        return chosen
    return "opengl32.dll" if api == "OpenGL" else "dxgi.dll"


# What the manifest and the labels say where a proxy name would go when the
# game is reached through the Vulkan layer instead. Never a file.
VULKAN_LAYER = "(vulkan layer)"


def _known_api(g: games.Game) -> str:
    """The API to fall back on when the shown one cannot be used.

    Normally what detection read. For the games known to close themselves on
    a ReShade DLL it is DX11 whatever detection managed, because detection
    can read nothing at all from a protected or unreadable executable - and
    those are exactly the folders where being wrong means the game quits.
    """
    detected = getattr(g, "api_detected", "") or ""
    if detected in dxvk.APIS:
        return detected
    return "DX11" if dxvk.wanted(g.exe) else detected


def wants_dxvk(g: games.Game) -> str | None:
    """The game's name when it is known to need DXVK, else None.

    These games close themselves the moment ReShade hooks D3D11 - no crash,
    no message. Through DXVK they render on Vulkan and ReShade stays outside.

    A game whose API has been set to Vulkan by hand still counts: Vulkan is
    what this route produces, and reading it as the game's own API took the
    tick off the one game that must have it (see dxvk_api).
    """
    api = g.api
    detected = _known_api(g)
    if api not in dxvk.APIS and detected in dxvk.APIS and dxvk.wanted(g.exe):
        # a hand-set API hides it: MGS V arrived with DX10 in the settings and
        # Vulkan in the library, both set by hand over a DX11 detection, and
        # either one turned off the only transport the game works on
        api = detected
    return dxvk.wanted(g.exe) if api in dxvk.APIS else None


def uses_dxvk(g: games.Game, opt: "Options") -> bool:
    """Is this install going through DXVK? D3D11 or D3D9, on the ReShade
    routes only - OptiScaler is itself the dxgi.dll DXVK would need to be,
    and ShortFuse's renodx-dlss hooks D3D9 in-process. The standalone add-on
    reaches Vulkan only with an extra boundary shader and a per-launch layer
    script; its D3D11 path is the tested one, so it stays on D3D11.

    On D3D11 this is a choice. On DirectX 9 it is not: the feed needs a
    D3D11/D3D12 device to build its contract on, ReShade on a raw D3D9
    device cannot give it one, and DXVK is the only translation left since
    dgVoodoo2 was dropped. So a DX9 game takes it whether or not the box is
    ticked - the routes that handle D3D9 themselves are excluded above. A
    DX8 game the same: DXVK's d3d8.dll runs on its own d3d9.dll (#403).
    """
    return bool(dxvk_api(g, opt))


def dxvk_api(g: games.Game, opt: "Options") -> str:
    """Which DirectX this install translates to Vulkan, or "" for none.

    Normally the game's API. The exception is a game whose API somebody has
    set to Vulkan by hand: that is what this route PRODUCES, not what the
    game is. MGS V arrived that way - the tool says "the game will render on
    Vulkan", the person set Vulkan to match, and DXVK, the one transport MGS
    V works on, quietly switched itself off; the install then wrote the
    ReShade dxgi.dll that makes MGS V close itself. So when the detected API
    is one DXVK translates, and either the box is ticked or the executable is
    one of the games known to need it, that detected API is used.
    """
    if opt.path in (OPTI, ROUTE_RENODX, UPSTREAM, STANDALONE, ROUTE_REMIX):
        return ""
    api = g.api
    if api not in dxvk.APIS:
        detected = _known_api(g)
        known = bool(dxvk.wanted(g.exe))
        if detected in dxvk.APIS and (known or (api == "Vulkan" and opt.dxvk)):
            api = detected
        else:
            return ""
    # the tick still decides (--no-dxvk, and the box in the game's settings);
    # what the fix above restores is the default, not the choice
    return api if (opt.dxvk or api in ("DX9", "DX8")) else ""


def via_dxvk(g: games.Game, opt: "Options") -> games.Game:
    """The game as the rest of the install sees it: a Vulkan game."""
    if not uses_dxvk(g, opt):
        return g
    return replace(g, api="Vulkan", api_why=f"DXVK: {dxvk_api(g, opt) or g.api} -> Vulkan")


def check_supported(g: games.Game) -> tuple[bool, str]:
    """Can this game be set up automatically?"""
    if not g.exe:
        return False, "No game executable found."
    if g.error:
        return False, g.error
    if g.exe_warning and (g.bitness not in (32, 64) or g.api not in games.APIS):
        return False, ("Choose this game's 'architecture' and 'graphics api' in "
                       "the game's settings - Windows protects its "
                       "executable, so they cannot be read from it.")
    if g.bitness not in (32, 64):
        return False, "Could not read the architecture."
    if g.api == "DX8" and g.bitness == 64:
        # Set by hand: detection never says DX8 for a 64-bit exe, because
        # there is no 64-bit Direct3D 8 (gate 2.0.5).
        return False, ("DirectX 8 is 32-bit only, and this executable is "
                       "64-bit - set 'graphics api' to the one it really "
                       "draws with in the game's settings.")
    if g.api == "Vulkan":
        # Reachable since the bridge landed: it mirrors the game's DLSS
        # contract onto a private D3D12 session. ReShade still has to be
        # attached to the Vulkan runtime, which its own installer does.
        return True, ""
    return True, ""


def _entry_key(value) -> str:
    return str(value).replace("\\", "/").lower()


def _record_hash(data: dict, rel, field: str = "hashes") -> str:
    rows = data.get(field)
    if not isinstance(rows, dict):
        return ""
    return next((v for k, v in rows.items() if _entry_key(k) == _entry_key(rel)
                 and isinstance(v, str) and len(v) == 64), "")


def _safe_target(root: Path, dst: Path, game_root=None) -> Path:
    """Check the actual destination, including existing directory junctions."""
    for base in (root, game_root):
        if base is None:
            continue
        try:
            net.inside(base, str(dst.absolute()), absolute_ok=True)
            return dst
        except net.OutsideError:
            pass
    raise net.OutsideError(f"{dst} points outside the game folder - refused.")


def _atomic_copy(src: Path, dst: Path) -> None:
    """A failed or short copy must leave the previous destination whole."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    destination_before = net.sha256(dst) if dst.exists() else None
    fd, name = tempfile.mkstemp(prefix=dst.name + ".", suffix=".aio-part", dir=dst.parent)
    os.close(fd)
    part = Path(name)
    try:
        before = net.sha256(src)
        shutil.copyfile(src, part)
        if net.sha256(part) != before or net.sha256(src) != before:
            raise OSError(f"the copy of {src.name} failed byte verification")
        with part.open("r+b") as handle:
            os.fsync(handle.fileno())
        destination_now = net.sha256(dst) if dst.exists() else None
        if destination_now != destination_before:
            raise OSError(f"{dst.name} changed while its replacement was being staged; nothing was replaced")
        os.replace(part, dst)
    finally:
        try:
            part.unlink(missing_ok=True)
        except OSError:
            pass


def _displace(path: Path) -> Path:
    """Keep later personal bytes under an unused name before replacement."""
    for number in range(10000):
        candidate = path.with_name(path.name + ".dlss5-aio-displaced" + (f".{number}" if number else ""))
        if not candidate.exists():
            _atomic_copy(path, candidate)
            return candidate
    raise OSError(f"Too many preserved copies of {path.name}; nothing was replaced.")


def _rel_file(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path.absolute())


def _checkpoint(rep: Report) -> None:
    if rep.checkpoint is not None and not rep.checkpoint():
        raise OSError("The recovery record could not be saved; no further files were replaced.")


def _prepare_write(dst: Path, rep: Report, root: Path) -> None:
    _backup(dst, rep, root)
    rel = _rel_file(root, dst)
    if rel not in rep.written:
        rep.written.append(rel)
    _checkpoint(rep)


def _wrote(dst: Path, rep: Report, root: Path) -> None:
    rel = _rel_file(root, dst)
    if rel not in rep.written:
        rep.written.append(rel)
    rep.hashes[rel] = net.sha256(dst)
    _checkpoint(rep)


def _backup(dst: Path, rep: Report, root: Path) -> None:
    """Preserve the game's own file before overwriting it.

    If the game ships its own nvngx_dlss.dll and we replace it, uninstalling
    must be able to put it back - otherwise the game loses its DLSS for good.

    A file a PREVIOUS install of ours wrote is emphatically not the game's.
    Backing one up made uninstall RESTORE it instead of deleting it, so after
    installing twice the folder came out of an uninstall still fully set up -
    dxgi.dll, the add-ons and a 165 MB nvngx_dlssnr.dll all put back. That is
    the "uninstall does not remove everything" people were seeing.
    """
    _safe_target(root, dst, rep.game_root)
    if not dst.is_file():
        return
    bak = dst.with_name(dst.name + BACKUP_SUFFIX)
    _safe_target(root, bak, rep.game_root)
    try:
        rel = str(bak.relative_to(root))
    except ValueError:
        rel = str(bak)
    try:
        key = str(dst.relative_to(root))
    except ValueError:
        # A .trex outside the install folder is recorded by absolute path;
        # asked only relative, a file of ours there was backed up as if it
        # were the game's own.
        key = str(dst)
    # Repeated config merges in this install must not back up our own intermediate output.
    current_digest = _record_hash({"hashes": rep.hashes}, key)
    if current_digest and _entry_key(key) in {_entry_key(value) for value in rep.written}:
        original_digest = _record_hash({"hashes": rep.hashes}, rel)
        if original_digest and not bak.is_file():
            raise OSError(f"The original backup of {dst.name} is missing; no replacement was made.")
        if bak.is_file() and original_digest and net.sha256(bak) != original_digest:
            raise OSError(f"The original backup of {dst.name} changed; no replacement was made.")
        if net.sha256(dst) != current_digest:
            kept = _displace(dst)
            rep.notes.append(f"kept changed {dst.name} as {kept.name}")
        if bak.is_file() and rel not in rep.written:
            rep.written.append(rel)
        return
    try:
        if _entry_key(key) in {_entry_key(value) for value in rep.preinstalled}:
            previous = _previous_manifest(root) or {}
            digest = _record_hash(previous, key)
            backup_digest = _record_hash(previous, rel)
            if backup_digest and not bak.is_file():
                raise OSError(f"The original backup of {dst.name} is missing; no replacement was made.")
            if bak.is_file() and backup_digest and net.sha256(bak) != backup_digest:
                raise OSError(f"The original backup of {dst.name} changed; no replacement was made.")
            if not digest or net.sha256(dst) != digest:
                kept = _displace(dst)
                rep.notes.append(f"kept changed or legacy {dst.name} as {kept.name}")
            # Ours from last time, so not backed up again - but the game's
            # original may already sit beside it from the FIRST install, and
            # the new record has to carry it. Returning without that dropped
            # the backup from every reinstall ("update all"), and uninstall
            # then deleted our file and left the game's own unrestored: the
            # swapped Remix runtime came out of an uninstall missing (#148).
            if bak.is_file() and rel.replace("\\", "/") not in \
                    {w.replace("\\", "/") for w in rep.written}:
                rep.written.append(rel)
            return
    except ValueError:
        pass
    # A backup left by an older release sits under a different suffix; adopt
    # it so this manifest can restore it, instead of orphaning a 50+ MB file.
    for old_s in LEGACY_BACKUP_SUFFIXES:
        legacy = dst.with_name(dst.name + old_s)
        _safe_target(root, legacy, rep.game_root)
        if legacy.is_file() and not bak.exists():
            try:
                legacy.rename(bak)
                rep.notes.append(f"adopted an older backup of {dst.name}")
            except OSError:
                pass
    if bak.exists():
        _safe_target(root, bak, rep.game_root)
        if net.sha256(dst) != net.sha256(bak):
            kept = _displace(dst)
            rep.notes.append(f"kept current {dst.name} as {kept.name} beside its earlier original backup")
        # Already backed up by an earlier install. Do NOT copy again - that
        # would overwrite the game's original with our own file. But the entry
        # must still go into this manifest, otherwise a later uninstall reads
        # a manifest with no backup listed and never restores it.
        if rel not in rep.written:
            rep.written.append(rel)
            rep.notes.append(f"existing backup of {dst.name} kept")
        return
    _safe_target(root, bak, rep.game_root)
    rep.hashes[rel] = net.sha256(dst)
    if rel not in rep.written:
        rep.written.append(rel)
    _checkpoint(rep)
    _atomic_copy(dst, bak)
    rep.notes.append(f"backed up the game's own {dst.name}")


def _overlay_key_pref() -> int:
    """The overlay key from the settings, or 0. Never raises.

    prefs.json is a file a person can edit, so it is untrusted input like
    any other: a hand-typed "F10" in there used to end the install with a
    ValueError at the last step.
    """
    try:
        return int(prefs.get("overlay_key") or 0)
    except (TypeError, ValueError):
        return 0


def _find_runtime(root: Path, name: str,
                  folder: Path | None = None) -> Path | None:
    """Where the game keeps this runtime, or None if it does not have one.

    Games do not keep these beside the executable - Unreal buries them under
    Engine/Plugins/..., so the same bounded walk the route detection uses
    finds them. `folder` is the game's own root, which is where the window
    looked: without it a game whose executable sits in a subfolder was
    offered the swap and then told it had no runtime. The FIRST one wins: a
    game with two copies is rare, and replacing one it does not load would
    be silent.
    """
    for base in (root, folder):
        if base is None:
            continue
        base = Path(base)
        if (base / name).is_file():
            return base / name
        try:
            hits = dlss.find_dlss_files(base, names=(name,))
        except Exception:
            hits = []
        if hits:
            return base / hits[0]
    return None


def _nested_game_dlss(root: Path, g, opt: "Options", x64: bool = True,
                      ours=()) -> Path | None:
    """The game's own nvngx_dlss.dll to replace, when it is not beside the exe.

    Unreal keeps it under Plugins/.../ThirdParty and loads it from there, so
    a copy put beside the executable is never the one that runs. #225 unticked
    "keep the game's own", picked 310.9.1, and the overlay still said 3.7.20:
    the choice was taken and nothing was swapped. None when the person keeps
    the game's own, when one sits beside the exe (the existing paths handle
    that), or on a 32-bit game.
    """
    # native_dlss is what the window read when the game was picked: with no
    # DLSS anywhere in the game there is nothing to swap, and the walk
    # below would run on the Tk thread for every preview (gate 1.9.1).
    if opt.keep_game_dlss or not x64 or opt.path == UPSTREAM \
            or not opt.native_dlss:
        return None
    mine = {str(o).replace("\\", "/") for o in ours or ()}
    beside = root / DLSS
    if beside.is_file() and DLSS not in mine:
        return None          # the game's own is beside the exe: swapped there
    # Our own copy beside the exe from an earlier install is not the game's:
    # without looking past it, the second install ("update all", a new pick)
    # left the nested runtime on the first install's build (gate 1.9.1).
    bases = [root]
    folder = getattr(g, "folder", None)
    if folder is not None:
        f_ = Path(folder)
        # One walk when the exe's folder sits inside the game's: walking
        # both covered the same tree twice, on the Tk thread for a preview.
        bases = [f_] if (f_ == root or f_ in root.parents) else [root, f_]
    for base in bases:
        # The remembered walk, never a fresh one: preview() runs on the Tk
        # thread, and a walk of a big engine tree costs the whole 6-second
        # budget there with the window frozen - which is what #8, #18 and
        # #32 were about. Detection already walked this folder with this
        # very key (dlss.py's `walked(folder, skip_dir=install_dir)`), so
        # the answer is in hand; when it is not, this pays for it once and
        # every later click reads the cache.
        try:
            hits = [h for h in dlss.walked(Path(base), skip_dir=root)
                    if os.path.basename(str(h)).lower() == DLSS]
            # Detection's walk looks for five runtime names and stops after
            # six matches, so "it found no nvngx_dlss.dll" is only an answer
            # when it did not stop early. When it did, ask the same
            # remembered walk the narrower question - once, and kept.
            # ...and it stops on two more: 6000 folders and 6 seconds. None
            # of the three is distinguishable from "there is nothing there",
            # so the narrow question is simply always asked when the broad
            # answer is empty. It is cached under its own key and preview()
            # runs on a worker now, so it is paid once, off the Tk thread.
            if not hits:
                hits = [h for h in dlss.walked(Path(base), skip_dir=root,
                                               names=(DLSS,))
                        if os.path.basename(str(h)).lower() == DLSS]
        except Exception:
            hits = []
        for h in hits:
            found = Path(base) / h
            # Compared as real paths: `base` is the folder as it was given
            # (a junction, an 8.3 name) and `h` came back from a walk that
            # resolved its root, so two spellings of one file would read as
            # two files - and the install would "swap" what it just wrote.
            if _same_path(found, beside):
                continue
            # And never a copy an earlier install of OURS put somewhere else
            # in this game: swapping it would back up our own file, and the
            # other install's uninstall would then hand the game ours as
            # its original. Our own files are never game evidence.
            if dlss._ours(found.parent, DLSS):
                continue
            return found
    return None


def _same_path(a: Path, b: Path) -> bool:
    try:
        return os.path.normcase(os.path.realpath(str(a))) == \
            os.path.normcase(os.path.realpath(str(b)))
    except OSError:
        return os.path.normcase(str(a)) == os.path.normcase(str(b))


def _opti_dlss_target(root: Path, g, opt: "Options", ours=()) -> Path | None:
    """The game's nvngx_dlss.dll to swap on the OptiScaler route.

    Nothing else on this route writes one, so the game's own beside the
    executable is swapped here too - not only a nested one (gate 1.9.1).
    """
    mine = {str(o).replace("\\", "/") for o in ours or ()}
    beside = root / DLSS
    # Spelled as the rest of this file spells it: "is it 64-bit", not "is it
    # not 32-bit" - a game whose bitness could not be read is neither, and
    # it must take the same answer a 32-bit one takes (#190). Applied to
    # BOTH branches, so the guard does not rest on "OptiScaler never gets a
    # 32-bit folder today" staying true (gate 1.9.1).
    x64 = getattr(g, "bitness", None) == 64
    # A backup beside it means an earlier install swapped this very file:
    # the reinstall swaps it again. Detection reads that file as ours by
    # then, so native_dlss is not asked for in that case (gate 1.9.1).
    swapped_before = (root / (DLSS + BACKUP_SUFFIX)).is_file()
    if x64 and not opt.keep_game_dlss and beside.is_file() and (
            (opt.native_dlss and DLSS not in mine) or swapped_before):
        return beside
    return _nested_game_dlss(root, g, opt, x64=x64, ours=ours)


def _preview_swap(write, pv, root: Path, have: Path, name: str) -> None:
    """List a swapped runtime in the preview, as the RR swap is listed."""
    try:
        write(str(have.relative_to(root)))
    except ValueError:
        write(str(have))
        pv.outside.append(f"replaces the game's own {name} at {have} - outside "
                          f"the install folder, backed up beside itself")


def _swap_nested_dlss(have: Path, fam: list, opt: "Options", rep, root: Path,
                      dl, log) -> None:
    """Replace the game's nested nvngx_dlss.dll, the way the RR swap does."""
    try:
        was = pe.file_version(have)
        e = _place_family(fam, opt.dlss, have, rep, root, dl, DLSS, "dlss", log)
    except PermissionError:
        raise
    except (sources.RateLimited, sources.Unavailable):
        raise
    except Exception as ex:
        log(f"      nvngx_dlss could not be fetched ({ex}) - the game keeps "
            f"the one it shipped")
        rep.warnings.append("nvngx_dlss.dll was not swapped: the download did "
                            "not arrive. The game keeps the runtime it "
                            "shipped, and everything else installed normally.")
        rep.skipped.append(DLSS)
        return
    try:
        where = have.relative_to(root)
    except ValueError:
        where = have
    log(f"      nvngx_dlss {_swapped(was, e['label'])}  ({where})")
    # The dlss page keeps the game's own file as <name>.dlss5-dlss-original
    # (core/dlssupdate.py; named here, not imported - it imports this
    # module). With one beside it, what this install backed up is the
    # page's update, and that is what uninstall brings back.
    if have.with_name(have.name + ".dlss5-dlss-original").is_file():
        rep.notes.append(f"dlss version: {e['label']} (the build the dlss page put in at {where} "
                         f"is backed up and comes back on uninstall; the game's own stays "
                         f"beside it for that page's restore)")
    else:
        rep.notes.append(f"dlss version: {e['label']} (the game's own at {where} "
                         f"is backed up and comes back on uninstall)")
    rep.components["dlss"] = e["label"]


def _is_win64_dll(p: Path, least: int = 200_000) -> tuple[bool, str]:
    """(ok, why not) - is this really a 64-bit Windows DLL of a sane size?

    A plain download can come back as an error page, an HTML redirect, or
    half a file from a connection that dropped; a zip at least fails loudly
    when it is not a zip. This runs before anything overwrites a runtime the
    game needs to start.
    """
    try:
        size = p.stat().st_size
    except OSError as e:
        return False, f"the download could not be read ({e})"
    if size < least:
        return False, (f"the download is only {size} bytes, which is not a "
                       f"runtime - usually an error page from the download "
                       f"server, or a connection that was cut")
    try:
        with open(p, "rb") as f:
            head = f.read(0x40)
            if len(head) < 0x40 or head[:2] != b"MZ":
                return False, "the download is not a Windows binary at all"
            (off,) = struct.unpack_from("<I", head, 0x3C)
            f.seek(off)
            sig = f.read(6)
            if len(sig) != 6 or sig[:4] != b"PE\0\0":
                return False, "the download is not a Windows binary at all"
            if struct.unpack_from("<H", sig, 4)[0] != 0x8664:
                return False, "the download is not an x64 binary"
    except OSError as e:
        return False, f"the download could not be read ({e})"
    return True, ""


# The last install that failed, and the folder it was for. log.last_error()
# is the last traceback ANYWHERE in the session - the update check failing
# offline is one - and a rule that reads it as "this install crashed" told
# somebody with no install at all that their install had crashed.
LAST_FAILURE: dict = {}


def note_failure(root, exc: BaseException) -> None:
    """Record that an install into `root` stopped with this error."""
    import traceback as _tb
    LAST_FAILURE.clear()
    LAST_FAILURE.update({
        "root": str(root), "at": time.time(),
        "text": "".join(_tb.format_exception(type(exc), exc,
                                             exc.__traceback__))[-4000:]})


# An hour: long enough for a slow download that died and a person who went
# to make tea, short enough that yesterday's failure is not offered as an
# explanation for today's folder.
FAILURE_KEEP = 3600.0


def clear_failure(root) -> None:
    """Forget this folder's failure - an install into it has just worked."""
    try:
        if LAST_FAILURE and Path(LAST_FAILURE.get("root") or "") == Path(root):
            LAST_FAILURE.clear()
    except OSError:
        pass


def last_failure(root) -> str:
    """The traceback of an install into this folder, or "".

    Scoped to the folder on purpose: "what went wrong in this session" is
    not the same question as "what went wrong with THIS install", and the
    diagnosis is only ever asked the second one.
    """
    if not LAST_FAILURE:
        return ""
    if time.time() - float(LAST_FAILURE.get("at") or 0) > FAILURE_KEEP:
        return ""
    try:
        same = Path(LAST_FAILURE.get("root") or "").resolve() == Path(root).resolve()
    except OSError:
        same = str(LAST_FAILURE.get("root") or "") == str(root)
    return str(LAST_FAILURE.get("text") or "") if same else ""


def _roll_back(g, root: Path, rep: "Report", fresh: bool, log,
               keep_note: str = "", rewrite=None, replaced: str = "",
               recorded: bool = True) -> str:
    """Take a failed FRESH install back out; the sentence that says so.

    A failed install used to leave what it had written and record it for
    'Uninstall'. Recorded is not removed: the game then starts with half a
    chain in it - #438 ran AC2 on DXVK with no ReShade and got "glitches in
    shaders" from a folder the person never chose to change. Every route
    writes in a different order, so the rule is not about order: whatever a
    fresh install wrote, a failure takes back out, through the uninstall
    that already knows every file, backup, sidelined name, layer and
    emulator setting an install can leave.

    Only a fresh one. An install over an earlier one of ours (the same
    route again, an "update all") keeps the old behaviour: rolling it back
    would take a working install away over a network blip. And only when
    the record was written - uninstall without one cleans up by known file
    names, which can reach a file that is not ours.

    `rewrite` puts back a record holding only the reason (`keep_note`: a
    full drive, the install's own refusal), so the diagnosis still says
    why; the record's file list is empty by then.

    `replaced` is the route this install took out before it began (a switch
    of route). That one is gone either way, and "the game runs as it did
    before" would be untrue: it is said instead (gate 2.0.6).
    """
    wrote = bool(rep.written or rep.sidelined or rep.remix or rep.layer_pending
                 or getattr(g, "emu", None) is not None)
    kept = ("What was written so far is recorded, so 'uninstall' can take it "
            "back out.")
    gone = (f" The previous {replaced} install was taken out before this one "
            f"began and is not put back - install it again to return to it."
            if replaced else "")
    if not wrote:
        return "Nothing was written into the game folder." + gone
    if not recorded or not (root / MANIFEST).is_file():
        # The record itself could not be written (a full drive): "recorded"
        # would send the person to an uninstall that finds nothing (gate 2.0.6).
        # Installing again would take these for the game's own files and
        # back them up, so the way out is by hand. The backups are the
        # game's own originals and never go on the delete list (gate 2.0.7).
        return NO_RECORD_HEAD + _no_record_text(rep) + gone
    if not fresh:
        return kept + gone
    try:
        uninstall(g, on_log=lambda s: None)
    except Exception as e:           # never let the clean-up hide the cause
        log(f"      could not take the partial install back out ({e})")
        return kept + gone
    if (root / MANIFEST).is_file():
        # uninstall keeps a record of the files it could not remove
        return ("Part of what it wrote could not be removed - a file is in "
                "use. Close the game and press 'uninstall'." + gone)
    log("      what this install had written was taken back out"
        + (f" (the previous {replaced} install stays removed)" if replaced
           else " - the folder is as it was before"))
    if keep_note and rewrite is not None:
        rep.written.clear()
        rep.sidelined = []
        rep.remix = {}
        rep.preinstalled = set()
        # Nothing of the components is left either: a record still naming
        # DXVK made the report list its files as MISSING (gate 2.0.6).
        rep.components = {}
        if net.ROLLED_BACK_NOTE not in rep.notes:
            rep.notes.append(net.ROLLED_BACK_NOTE)
        try:
            rewrite()
        except Exception:
            pass
    if replaced:
        return ("Nothing of the new install was left in the game folder: what "
                "it had written was taken back out." + gone)
    return ("Nothing of it was left in the game folder: what it had written "
            "was taken back out, so the game runs as it did before.")


NO_RECORD_HEAD = "No record of this install could be saved, so 'uninstall' has no list of it. "
RECORD_LOST_HEAD = "The install finished and its files are in place, but "


def _no_record_text(rep: "Report") -> str:
    """What a failed install without a record left, and how to undo it by
    hand: every file it wrote (never a backup of the game's own), the game
    files it renamed aside, and the backups to rename back."""
    backups = (BACKUP_SUFFIX,) + LEGACY_BACKUP_SUFFIXES
    ours = [n for n in rep.written if not n.endswith(backups)]
    kept = [n for n in rep.written if n.endswith(BACKUP_SUFFIX)]
    out = []
    if ours:
        out.append(f"Delete what it wrote: {', '.join(ours)}.")
    if kept:
        out.append(f"Then rename the backups it made of the game's own files, "
                   f"taking '{BACKUP_SUFFIX}' off the end: {', '.join(kept)}.")
    if rep.sidelined:
        out.append(f"It also renamed {', '.join(rep.sidelined)} by adding "
                   f"'{SIDELINE_SUFFIX}' - rename {'them' if len(rep.sidelined) > 1 else 'it'} back.")
    if rep.remix.get("conf"):
        out.append(f"It added the line '{rep.remix.get('key')} = True' to "
                   f"{rep.remix['conf']} - take that one line out.")
    for note in rep.notes:
        if note.startswith("registered ReShade as a Vulkan layer"):
            out.append("It also registered ReShade as a Vulkan layer for this "
                       "Windows user, which loads into every Vulkan application.")
        elif note.startswith("registered ReShade as an OpenXR layer"):
            out.append("It also registered ReShade as an OpenXR layer for this "
                       "Windows user, which loads into every OpenXR application.")
    if not out:
        out.append("It may have changed a setting of RTX Remix or of the "
                   "emulator, and wrote no file into the game folder.")
    return " ".join(out)


def _finish_record(recorded: bool, rep: "Report", log) -> None:
    """A successful install whose record could not be saved must not end in a
    plain 'Done': uninstall would find nothing (gate 2.0.7). The warning is
    what the autopilot and 'update all' read."""
    if recorded:
        return
    text = ("The install finished and its files are in place, but "
            + NO_RECORD_HEAD[0].lower() + NO_RECORD_HEAD[1:] + _no_record_text(rep))
    log(f"      !! {text}")
    rep.warnings.append(text)


def _verify_written(root: Path, rep: Report, log) -> None:
    """A vanished payload is an incomplete install, whatever removed it."""
    missing = [rel for rel in dict.fromkeys(rep.written)
               if not rel.endswith((BACKUP_SUFFIX,) + LEGACY_BACKUP_SUFFIXES)
               and not (root / rel).is_file()]
    if not missing:
        return
    names = ", ".join(missing[:4]) + ("..." if len(missing) > 4 else "")
    text = (f"Installation is incomplete: {len(missing)} written file(s) are missing: {names}. "
            "Inspect the application log, file permissions and any antivirus quarantine records before retrying. "
            "The remaining recovery record was kept for uninstall.")
    rep.warnings.append(text)
    log(text)
    _checkpoint(rep)
    raise InstallError(text)


def record_lost(rep) -> bool:
    return any(str(w).startswith(RECORD_LOST_HEAD) for w in getattr(rep, "warnings", ()))


# The sentences _roll_back opens an install error with. The cause comes after
# them (the result card reads the whole text), so a caller that keeps one line
# - the autopilot's reason, update all's log - takes it with cause_of.
ROLLBACK_HEADS = ("Nothing of it was left", "Nothing of the new install was left",
                  "What was written so far is recorded", NO_RECORD_HEAD,
                  "Part of what it wrote could not be removed",
                  "Nothing was written into the game folder")


def cause_of(err) -> str:
    """One line that says why an install stopped.

    The rollback sentence went first in 2.0.7's locked-file message, and the
    autopilot, which reads the first line, stopped recognising a game that
    holds a file open (gate 2.0.7)."""
    text = str(err).strip()
    if not text:
        return type(err).__name__
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paras) > 1 and paras[0].startswith(ROLLBACK_HEADS):
        return " ".join(ln.strip() for ln in paras[1].splitlines() if ln.strip())
    return paras[0].splitlines()[0]


def _ask_for_the_pass(root: Path, opt, log) -> None:
    """Set the DLSS 5 add-on's own switch, after ReShade.ini is ours.

    Its default is on, so this is for one case and it is the silent one:
    somebody who switched the pass off in the overlay once. ReShade.ini
    keeps that per game forever.

    After the backup, never before: Ini.save() creates the file, and asking
    for the switch first made the install back up a ReShade.ini it had just
    written itself - which uninstall would then put back.
    """
    if opt.path == ROUTE_RENODX:
        return                      # ShortFuse's add-on, its own section
    try:
        if reshade_ini.enable_dlss5_addon(root):
            log(f"      [{reshade_ini.ADDON_SECTION}] "
                f"{reshade_ini.ADDON_SWITCH}=1 (the add-on's own switch)")
    except OSError:
        pass                        # a folder we cannot write is said elsewhere


def _swapped(was: str, label: str) -> str:
    """"310.2.1 -> 310.9.1 (NVIDIA SDK)", or the build alone when nothing moved.

    A swap that says only what it put there leaves the person with no way
    to see what it was worth - and no way to notice, next time, that a
    launcher has quietly put the old runtime back.

    The two sides are written differently and have to be compared as
    numbers: `was` is the version stamped in the file on disk ("310.4.0"),
    the label is the catalog's ("310.4.0 (NVIDIA SDK)"). Comparing the
    strings printed an arrow between a build and itself on every reinstall.
    """
    num = re.match(r"[\d.]+", label or "")
    return label if (not was or (num and _ver(was) == _ver(num.group(0)))) \
        else f"{was} -> {label}"


def _ver(s: str) -> tuple:
    """(310, 10, 0) from "310.10.0.0" - trailing zeroes dropped.

    Numbers, not text: "310.10.0".rstrip(".0") and "310.1.0".rstrip(".0")
    are the same string, so a swap between two different builds printed as
    if nothing had moved.
    """
    parts = [int(n) for n in re.findall(r"\d+", s or "")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def _place_family(entries: list, want, dest: Path, rep, root: Path, dl,
                  member: str, prefix: str, log) -> dict:
    """Install the chosen build, falling back to the next source if need be.

    Verified builds come first, with a publisher SDK fallback fetched from
    a different host (raw.githubusercontent.com) than the mirror.
    That host being blocked - a corporate proxy, a DNS filter -
    would otherwise abort the install after ReShade and the add-ons are
    already on disk. So when the chosen entry cannot be downloaded at all,
    the next one in the family is tried, and the log says what happened.
    """
    e = sources.pick(entries, want)
    tries = [e] + [x for x in entries if x is not e][:1]
    last = None
    first_err = None
    for i, entry in enumerate(tries):
        name = f"{prefix}-{entry['label']}" + (".dll" if entry.get("raw")
                                               else ".zip")
        try:
            _place_entry(entry, dest, rep, root, dl, member, name)
            if i:
                log(f"      {member}: {tries[0]['label']} could not be "
                    f"downloaded ({last}) - used {entry['label']} instead")
            return entry
        except InstallError as ex:
            # A proxy or a DNS filter blocking the download host answers 200
            # with an HTML page, which arrives here as "not a Windows binary
            # at all" - the exact failure this fallback exists for. So it is
            # tried like any other, and only the last one is raised.
            last = ex
            if first_err is None:
                first_err = ex
            if i == len(tries) - 1:
                if i:
                    # Both failed. The publisher's reason is the useful one
                    # - a proxy serving an HTML page, say - and only the
                    # fallback's is raised, so say the first one out loud
                    # before it is lost. `last` is this iteration's error by
                    # now, which is why it is kept separately.
                    log(f"      the first source said: {first_err}")
                raise
        except Exception as ex:
            last = ex
            if first_err is None:
                first_err = ex
            if i == len(tries) - 1:
                if i:
                    log(f"      the first source said: {first_err}")
                raise
    raise last if last else RuntimeError(f"{member}: nothing to install")


def _place_entry(e: dict, dest: Path, rep, root: Path, dl, member: str,
                 cache_name: str) -> None:
    """Put one catalog entry on disk, archive or plain file.

    NVIDIA publishes its runtimes as the DLL itself; the community mirror
    publishes zips. Both arrive here so the callers do not have to know
    which is which - and a plain file is checked before it is allowed to
    overwrite anything.
    """
    family = e.get("verified_family")
    raw = bool(family) or bool(e.get("raw"))
    if family:
        from . import runtimecatalog
        got = runtimecatalog.resolve(e, family)
    else:
        got = dl(e["url"], cache_name)
    if raw:
        ok, why = _is_win64_dll(got)
        if not ok:
            try:
                got.unlink()          # never serve it from the cache again
            except OSError:
                pass
            raise InstallError(
                f"{member} was not installed: {why}.\n\n"
                f"That file was not written and the download was thrown "
                f"away. Try again - it is fetched fresh - or pick another "
                f"build.")
    if raw:
        _copy(got, dest, rep, root)
    else:
        _extract(got, member, dest, rep, root)
    try:
        rep.written.append(str(dest.relative_to(root)))
    except ValueError:
        # A runtime the game keeps above the install folder - the nested
        # executable layout _find_runtime searches for. _backup() and
        # _copy() record the absolute path in the same case, and uninstall
        # accepts it as long as it resolves inside the game.
        rep.written.append(str(dest))


def _extract(zpath: Path, member: str, dst: Path, rep: Report, root: Path) -> None:
    """Extract one member, preserving anything already at the destination."""
    with tempfile.TemporaryDirectory(prefix="aio-extract-") as tmp:
        source = Path(tmp) / dst.name
        net.extract_one(zpath, member, source)
        _copy(source, dst, rep, root)


def _copy(src: Path, dst: Path, rep: Report, root: Path) -> None:
    before = net.sha256(dst) if dst.exists() else None
    _prepare_write(dst, rep, root)
    rep.hashes[_rel_file(root, dst)] = net.sha256(src)
    _checkpoint(rep)
    if (net.sha256(dst) if dst.exists() else None) != before:
        raise OSError(f"{dst.name} changed while its original was being preserved; nothing was replaced")
    _atomic_copy(src, dst)
    _wrote(dst, rep, root)


def _remove_for_install(dst: Path, rep: Report, root: Path) -> None:
    """Retire a conflicting file without losing later edits or its original."""
    before = net.sha256(dst)
    _backup(dst, rep, root)
    _checkpoint(rep)
    if net.sha256(dst) != before:
        raise OSError(f"{dst.name} changed while it was being preserved; it was kept")
    dst.unlink()
    key = _entry_key(_rel_file(root, dst))
    rep.written = [rel for rel in rep.written if _entry_key(rel) != key]
    rep.preinstalled = {rel for rel in rep.preinstalled if _entry_key(rel) != key}
    _checkpoint(rep)


def _forget_restored(rel: str, rep: Report) -> None:
    """A restored original must stop being owned by this installation."""
    key = _entry_key(rel)
    rep.preinstalled = {value for value in rep.preinstalled if _entry_key(value) != key}
    rep.written = [value for value in rep.written if _entry_key(value) != key]
    rep.hashes = {name: digest for name, digest in rep.hashes.items() if _entry_key(name) != key}


def _write_bytes(content: bytes, dst: Path, rep: Report, root: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="aio-content-") as tmp:
        source = Path(tmp) / dst.name
        source.write_bytes(content)
        _copy(source, dst, rep, root)


def _remix_option(conf: Path, key: str, rep: Report, root: Path) -> None:
    """Keep the exact old key lines in the journal before changing the config."""
    _safe_target(root, conf, rep.game_root)
    content = conf.read_bytes() if conf.is_file() else b""
    matching = [line for line in content.splitlines(keepends=True) if remix._line_re(key).match(line)]
    previous = (_previous_manifest(root) or {}).get("remix")
    if (isinstance(previous, dict) and previous.get("key") == key
            and _entry_key(previous.get("conf")) == _entry_key(rep.remix.get("conf"))
            and isinstance(previous.get("original_lines"), list) and matching
            and all(line.rstrip(b"\r\n") == f"{key} = True".encode("ascii") for line in matching)):
        # A reinstall must keep the first original, not our own enabled value.
        for field in ("original_lines", "conf_before_sha256", "conf_final_newline"):
            rep.remix[field] = previous.get(field)
    else:
        rep.remix["original_lines"] = [line.decode("latin1") for line in matching]
        rep.remix["conf_before_sha256"] = net.sha256(conf) if conf.is_file() else ""
    _checkpoint(rep)
    with tempfile.TemporaryDirectory(prefix="aio-remix-") as tmp:
        staged = Path(tmp) / conf.name
        staged.write_bytes(content)
        if not remix.set_option(staged, key, "True"):
            raise OSError(f"Could not prepare {conf.name}")
        if (conf.read_bytes() if conf.is_file() else b"") != content:
            raise OSError(f"{conf.name} changed while its option was being prepared")
        _atomic_copy(staged, conf)


def _restore_remix(conf: Path, record: dict) -> bool:
    """Restore only our unchanged key, leaving later user settings in place."""
    key = record.get("key")
    originals = record.get("original_lines")
    if key not in {value + ".enable" for value in remix.PREFIX.values()} or not isinstance(originals, list) or not all(isinstance(line, str) for line in originals):
        raise OSError("the recorded Remix key's previous value cannot be verified")
    if not conf.is_file():
        return False
    content = conf.read_bytes()
    pattern = remix._line_re(key)
    lines = content.splitlines(keepends=True)
    matching = [line for line in lines if pattern.match(line)]
    expected = f"{key} = True".encode("ascii")
    if not matching or any(line.rstrip(b"\r\n") != expected for line in matching):
        return False
    output = []
    inserted = False
    for line in lines:
        if pattern.match(line):
            if not inserted:
                output.extend(value.encode("latin1") for value in originals)
                inserted = True
        else:
            output.append(line)
    result = b"".join(output)
    if not record.get("conf_final_newline", True):
        import hashlib
        trimmed = result.rstrip(b"\r\n")
        if hashlib.sha256(trimmed).hexdigest() == record.get("conf_before_sha256"):
            result = trimmed
    with tempfile.TemporaryDirectory(prefix="aio-remix-") as tmp:
        staged = Path(tmp) / conf.name
        staged.write_bytes(result)
        if conf.read_bytes() != content:
            raise OSError(f"{conf.name} changed while its original option was being restored")
        _atomic_copy(staged, conf)
    return True


def _configure(root: Path, rep: Report, function, *args, names=("ReShade.ini", "ReShadePreset.ini"), record_root=None, **kwargs):
    """Merge configuration in isolation, then commit each complete result."""
    with tempfile.TemporaryDirectory(prefix="aio-config-") as tmp:
        staged = Path(tmp)
        originals = {}
        for name in names:
            target = _safe_target(root, root / name, rep.game_root)
            if target.is_file():
                _atomic_copy(target, staged / name)
                originals[name] = net.sha256(staged / name)
            else:
                originals[name] = None
        result = function(staged, *args, **kwargs)
        if result is False:
            return False
        for name in names:
            target = _safe_target(root, root / name, rep.game_root)
            if (net.sha256(target) if target.is_file() else None) != originals[name]:
                raise OSError(f"{name} changed while its configuration was being prepared; it was kept")
        for name in names:
            source = staged / name
            if source.is_file() and (not (root / name).is_file() or net.sha256(source) != net.sha256(root / name)):
                _copy(source, root / name, rep, record_root or root)
        return result


# ---------------------------------------------------------------- plan

def _opti_proxy_for(root: Path, opt: Options) -> str:
    """The name OptiScaler goes in under: the one picked, or a free one that
    is not a name the person's own frame generation files need."""
    return opt.opti_proxy or optiscaler.suggest_proxy(
        root, avoid=ownfg.dests(opt.own_fg) if opt.path == OPTI else ())


def _own_fg_refusal(root: Path, opt: Options) -> str:
    """Why these frame generation files cannot go in here, or "" (also "" on
    a route that does not place them)."""
    if opt.path != OPTI or not opt.own_fg:
        return ""
    man = _previous_manifest(root) or {}
    prev = _previous_route(root)
    return ownfg.refusal(root, opt.own_fg, _opti_proxy_for(root, opt), man,
                         route_changes=bool(prev and prev != OPTI),
                         is_optiscaler=optiscaler.is_optiscaler)


def _place_own_fg(root: Path, opt: Options, rep: "Report", log, begin) -> None:
    """The OptiScaler route's last files: the person's own frame generation
    files when they added some, and an earlier set taken out when not."""
    man = _previous_manifest(root) or {}
    restored = ownfg.remove_leftovers(root, man, opt.own_fg, log)
    for gone in restored:
        _forget_restored(gone, rep)
    if restored:
        _checkpoint(rep)
    if not opt.own_fg:
        return
    recipe = ownfg.RECIPES[opt.own_fg]
    begin(f"frame generation files ({recipe.label.split(' (')[0]})")
    with prefs.mutation_lock():
        have = ownfg.stored(opt.own_fg)
        if have:
            for dst, src in have.items():
                _copy(src, root / dst, rep, root)
                log(f"      {dst} (your file)")
        else:
            # The store is gone, so the previous installed recipe stays recorded.
            log(f"      {', '.join(ownfg.dests(opt.own_fg))} kept from the last install "
                f"(the copies in the tool's folder are gone)")
    rep.components["own_fg"] = opt.own_fg
    rep.warnings.append(f"frame generation files ({recipe.label}): {ownfg.UNTRIED}")
    rep.notes.append(f"frame generation: {recipe.label}, from files you downloaded; "
                     f"{recipe.tip}. 'uninstall' takes them out and puts back anything "
                     f"they replaced")


def _opti_needs_dlss(opt: Options) -> bool:
    """OptiScaler running DLSS in place of the game's FSR/XeSS: the game
    ships no nvngx_dlss.dll, so the route has to bring one."""
    return opt.path == OPTI and bool(opt.upscaler) and not opt.native_dlss


def remix_runtime(g: games.Game) -> Path | None:
    """The game's `.trex` folder, looked for beside the executable first."""
    return remix.find_runtime(g.install_dir) or remix.find_runtime(g.folder)


def remix_state(g: games.Game, opt: Options) -> tuple[Path | None, str, bool]:
    """(.trex folder, fork flavour, are we replacing the runtime?).

    The flavour is read out of the runtime binary, so this is the one place
    that decides whether the route can work as-is or needs the swap.
    """
    trex = remix_runtime(g)
    if trex is None:
        return None, "", False
    flavour = remix.runtime_flavour(trex)
    if not opt.remix_swap:
        return trex, flavour, False
    # A runtime this tool swapped in has the pass, so "has none" alone would
    # skip it on every later install: "update all" cleared the update mark,
    # kept the old runtime, and dropped the swap from the record. One we put
    # there is ours to renew; a mod's own runtime with the pass is never
    # replaced.
    return trex, flavour, not flavour or _remix_runtime_is_ours(g, trex)


def _runtime_stamp(p: Path) -> list | None:
    """Size and modification time: cheap, and enough to see a file replaced.

    A hash would read 150-230 MB, and this is asked on the Tk thread when a
    route is drawn.
    """
    try:
        st = p.stat()
        return [st.st_size, st.st_mtime_ns]
    except OSError:
        return None


def _remix_swap_record(g: games.Game) -> dict:
    try:
        prev = _previous_manifest(g.install_dir) or {}
        comp = prev.get("components") or {}
        return comp if comp.get("remix_runtime") else {}
    except Exception:
        return {}


def _remix_runtime_is_ours(g: games.Game, trex: Path) -> bool:
    """Is the runtime in .trex the one this tool swapped in?

    The record alone is not enough: a mod can update its own runtime after
    our swap, and the record would still say "ours" - "update all" would
    then replace the mod's new runtime. So the swapped file's size and time
    are recorded, and it is ours while it still matches. A record from
    before that stamp existed has only the record to go on.
    """
    rec = _remix_swap_record(g)
    if not rec:
        return False
    return not _remix_runtime_replaced(g, trex)


def _remix_runtime_replaced(g: games.Game, trex: Path) -> bool:
    """We swapped it once, and the mod has put its own runtime there since.

    By size alone: the time moves without the file changing (FAT32 across
    daylight saving, a folder moved or restored), and a wrong "replaced"
    costs the backup of the mod's original. Two different 150-230 MB
    runtimes of the same size to the byte is not the case to design for.
    """
    rec = _remix_swap_record(g)
    want = rec.get("remix_runtime_stamp")
    # A stamp that is not [size, time] - an edited or damaged record - is no
    # stamp at all, as in a record from before stamps.
    if not (isinstance(want, list) and want and isinstance(want[0], int)):
        return False
    now = _runtime_stamp(trex / remix.RUNTIME_DLL)
    return now is not None and now[0] != want[0]


def plan(g: games.Game, opt: Options) -> list[str]:
    """The steps for this game on the selected path.

    The three paths need very different things. Only the feeder builds a
    synthetic contract out of ReShade shaders, so only it needs the shader
    headers, the .fx and a motion-vector provider.
    """
    if opt.path == ROUTE_REMIX:
        # Nothing goes beside the executable, and no ReShade at all: the
        # runtime the mod already installed does the work, so the whole
        # install is one runtime file, one config line - unless the runtime
        # has no neural pass and the user opted into replacing it.
        _trex, _flav, swap = remix_state(g, opt)
        return (["RTX Remix runtime (DLSS 5 build)"] if swap else []) \
            + [DLSSNR, remix.CONF]

    steps: list[str] = []
    if reengine.detected(g.install_dir):
        steps.append("REFramework (RE Engine - so ReShade survives)")
    if uses_dxvk(g, opt):
        steps.append(f"DXVK ({dxvk_api(g, opt) or g.api} -> Vulkan)")
        g = via_dxvk(g, opt)
    if opt.path == OPTI:
        # OptiScaler replaces ReShade entirely - it is the proxy DLL itself.
        # A game with DLSS keeps its own nvngx_dlss.dll; one whose FSR/XeSS
        # calls are being redirected has none, so one goes in. REFramework
        # still has to go in first on an RE Engine game - OptiScaler is a
        # proxy DLL too, and RE Engine's tamper checks do not care which one.
        return (steps[:1] if steps[:1] and steps[0].startswith("REFramework") else []) \
            + [f"OptiScaler ({optiscaler.BUILDS.get(opt.opti_build, optiscaler.BUILDS['']).split('  -  ')[0]})",
               "nvngx_dlssnr.dll"] \
            + (["nvngx_dlss.dll"] if _opti_needs_dlss(opt) else []) \
            + ["OptiScaler configuration"] \
            + ([f"frame generation files ({ownfg.label(opt.own_fg).split(' (')[0]})"]
               if opt.own_fg in ownfg.RECIPES else [])
    steps.append("ReShade (Vulkan layer)" if g.api == "Vulkan" else "ReShade")

    if opt.path == UPSTREAM:
        # neural-upstream does the neural rendering itself, so no renodx
        # add-on beside it (two NGX hooks), and the game's nvngx_dlss.dll is
        # never replaced: its DLSS is what the network feeds.
        return steps + ["neural-upstream", "nvngx_dlssnr.dll",
                        *([DLSSD] if opt.dlssd else []),
                        "ReShade configuration"]

    if opt.path == STANDALONE:
        # The add-on brings its own feed and runs the network itself: no
        # renodx add-on (it would process the frame twice), but the shader
        # headers, its companion shader with VORT for motion vectors, and
        # the three NVIDIA runtimes it loads privately.
        return steps + ["ReShade shader headers", "standalone-dlssnr",
                        "VORT Motion (motion vectors)", "nvngx_dlssnr.dll",
                        "nvngx_dlss.dll", "nvngx_dlssg.dll",
                        *([DLSSD] if opt.dlssd else []),
                        "ReShade configuration"]

    if opt.path == FEEDER:
        steps.append("ReShade shader headers")
        steps.append("DLSS5-Feeder")
        # install() moves an OpenGL game's provider to VORT before it plans,
        # so the switch is already visible here.
        provider = 2 if g.api == "OpenGL" and opt.provider in (3, 4) else opt.provider
        if provider in (3, 4):
            steps.append("LumeniteFX (motion vectors)")
        elif provider == 2:
            steps.append("VORT Motion (motion vectors)")
    elif opt.path == BRIDGE:
        steps.append("dlss5-bridge")

    steps += ["DLSS 5 add-on (renodx-dlss SF)" if opt.path == ROUTE_RENODX
              else "DLSS 5 add-on (renodx)",
              "nvngx_dlssnr.dll", "nvngx_dlss.dll"] \
        + ([DLSSD] if opt.dlssd else [])
    if opt.path == FEEDER and g.bitness == 32:
        steps.append("host64 helper process")
    if opt.mfg and mfg.applies(gpu.detect()[1], g.api, g.install_dir, g.folder)[0] \
            and (mfg.loader_name(g.exe,
                                 {refw.DINPUT8} if reengine.detected(g.install_dir) else set(),
                                 g.install_dir)
                 or mfg.existing_plugins(g.install_dir)):
        steps.append("RTX 40 multi-frame generation")
    steps.append("ReShade configuration")
    if opt.path == FEEDER:
        steps.append("dlss5-feed.cfg")
    elif opt.path == BRIDGE:
        steps.append("dlss5-bridge.cfg")
    return steps


# ---------------------------------------------------------------- preview

@dataclass
class Preview:
    """What an install would do to this folder, worked out without doing it.

    Every list holds relative paths (or one-line descriptions where a path
    does not exist, such as the Vulkan layer). `blockers` non-empty means
    install() would raise before writing anything.
    """
    steps: list[str] = field(default_factory=list)      # from plan()
    writes: list[str] = field(default_factory=list)     # created / overwritten
    backups: list[str] = field(default_factory=list)    # kept as *.backup first
    removes: list[str] = field(default_factory=list)    # cleaned up beforehand
    outside: list[str] = field(default_factory=list)    # written outside the folder
    blockers: list[str] = field(default_factory=list)   # would make install() raise
    warnings: list[str] = field(default_factory=list)   # anti-cheat, reliability


def _cached_zip_members(pattern: str) -> list[str] | None:
    """Member names of the newest download matching `pattern` in the cache,
    or None when nothing is cached. Read-only: the preview may look at what an
    earlier install fetched, but it never fetches anything itself."""
    try:
        zips = sorted(net.CACHE.glob(pattern), key=lambda p: p.stat().st_mtime)
        if not zips:
            return None
        import zipfile
        with zipfile.ZipFile(zips[-1]) as z:
            return [n for n in z.namelist() if not n.endswith("/")]
    except Exception:
        return None


def launcher_warning(g: games.Game) -> str:
    """Said before and after an install that is going in front of a launcher.

    A launcher starts the game in a new process and then hands over: the
    files go beside a program that never draws a frame, nothing loads, and
    the report comes back "it never started" with every file present -
    GTAVLauncher.exe was the whole of #191, and there is no way to tell it
    from a game that ignores its proxy once the install is done. So it is
    said at the one moment it can still be acted on.
    """
    exe = getattr(g, "exe", None)
    if exe is None or not pe.launcher_like(exe):
        return ""
    # `or None`: an empty list is not "nothing recorded" to real_exe_for -
    # it is "these are the candidates", and it then skips the walk that
    # finds the executable that actually draws.
    real = pe.real_exe_for(exe, list(getattr(g, "candidates", None) or [])
                           or None)
    return (f"{exe.name} looks like a launcher, not the game. A launcher "
            f"starts the game as a separate program, and nothing installed "
            f"beside it is loaded by the game."
            + (f" {real.name} in this folder looks like the one that draws: "
               f"pick it in the game's details and install again."
               if real else
               " Find the executable the game itself runs from - it is "
               "usually under a Binaries or Bin folder - and install "
               "there."))


# What the RTX 40 MFG package needs from the game, as install() records it
# and the preview says it beforehand - one wording, two readers.
MFG_NO_DLSSG = ("the RTX 40 MFG unlock acts on the game's own DLSS "
                "frame generation, and this game ships none - the "
                "neural pass still runs, multi-frame generation "
                "will not appear")
MFG_FSR_FG = ("'frame generation' (FSR 3.1) is on: FSR "
              "frame generation takes the place of DLSS "
              "frame generation, so the RTX 40 MFG unlock "
              "has nothing to act on - untick it to use MFG")


def _mfg_warnings(g, opt: "Options", root: Path, written=()) -> list[str]:
    """The MFG package's warnings that can be known before it is unpacked.

    The FSR frame-generation one is not here: install() says it only once
    enable_fg() has really switched FSR frame generation on."""
    if opt.path != OPTI or opt.opti_build != optiscaler.PRESR_MFG:
        return []
    try:
        fg_file = mfg.has_dlssg(Path(getattr(g, "folder", None) or root), root,
                                written=written)
    except Exception:
        fg_file = "?"
    return [] if fg_file else [MFG_NO_DLSSG]


def preview(g: games.Game, opt: Options) -> Preview:
    """Everything install() would write, back up, remove or touch outside
    the game folder - without a single network request or write.

    People want to know "did this delete my files?" BEFORE they press
    Install, so this mirrors install() step by step and reports its
    decisions on the folder as it is now. Anything whose exact file list
    only a download reveals (LumeniteFX shaders, the OptiScaler package) is
    read from the download cache when an earlier install left one there,
    and described by pattern otherwise.
    """
    pv = Preview()
    root = g.install_dir
    if g.exe_warning:
        pv.warnings.append(games.XBOX_EXE_CHOSEN)
    note = launcher_warning(g)
    if note:
        pv.warnings.append(note)

    ok, why = check_supported(g)
    if not ok:
        pv.blockers.append(why)
    # Same hard rule install() enforces: a Remix game only ever takes the
    # remix route. Without this the preview would describe a plan (DXVK,
    # ReShade...) that install() actually refuses outright.
    if opt.path != ROUTE_REMIX and remix.is_remix_game(root):
        pv.blockers.append(
            "This game has an RTX Remix mod installed (its .trex runtime is "
            "in the folder). Only the remix route works here - every other "
            "route installs ReShade, which crashes a Remix game before it "
            "draws a frame, and on DirectX 9 it would write over the Remix "
            "runtime itself. Choose the remix route, or uninstall the "
            "Remix mod first.")
    # The RTX 40 MFG package on another card: install() refuses it before
    # anything is written, so the preview says the same - it described a
    # plan the install then turned down (gate 2.0.5).
    if opt.path == OPTI:
        try:
            _why_card = optiscaler.card_refusal(opt.opti_build, gpu.detect()[1])
        except Exception:
            _why_card = ""
        if _why_card:
            pv.blockers.append(_why_card)
    pv.steps = plan(g, opt)
    x64 = g.bitness == 64
    if opt.path == FEEDER and g.api == "OpenGL" and opt.provider in (3, 4):
        opt = replace(opt, provider=2)       # as install() does: VORT on GL
    dxvk_from = dxvk_api(g, opt)
    g = via_dxvk(g, opt)
    proxy = _proxy_name(g.api, opt.reshade_proxy)

    def rel(*parts) -> str:
        return "/".join(str(p).replace("\\", "/") for p in parts if str(p))

    def add(lst: list[str], item: str) -> None:
        if item not in lst:
            lst.append(item)

    try:
        _gp = _gpu_pref_line(root, g, opt)
    except Exception:
        _gp = ""
    if _gp:
        pv.outside.append(_gp)

    # Blockers: the checks preflight() and install() make, minus the write
    # probe - os.access instead, because a preview must not create files.
    if not games._isdir(root):
        pv.blockers.append(f"{root} does not exist.")
        return pv
    if not os.access(root, os.W_OK):
        pv.blockers.append(f"No permission to write into {root} - close the "
                           f"game if it is running, or run as administrator.")
    if g.exe and g.exe.name.lower() in _running_processes():
        pv.blockers.append(f"{g.exe.name} is running. Close the game first.")

    # Warnings, worded as install() records them.
    trex, flavour, swap = remix_state(g, opt) if opt.path == ROUTE_REMIX \
        else (None, "", False)
    level, why_rel = reliability(g, opt.path,
                                 "" if opt.native_dlss else opt.upscaler,
                                 remix_swap=swap)
    if level != STABLE:
        pv.warnings.append(f"{level}: {why_rel}")
    hw = hook_warning(root, opt.path)
    if hw:
        pv.warnings.append(hw)
    ac = anticheat.detect(root, g.folder)
    if ac.present:
        pv.warnings.append(
            f"{ac.summary} detected ({', '.join(ac.evidence)}). ReShade "
            f"add-ons and anti-cheat do not coexist: expect the game not to "
            f"start, or nothing to happen, or a ban. Do not use this online.")
    if opt.path != ROUTE_REMIX and reengine.detected(root):
        pv.warnings.append(reengine.message())

    preinstalled = _previously_ours(root)

    # What the previous-route uninstall takes away first. Worked out before
    # anything else: a file it removes will not be there to back up later.
    gone: set[str] = set()
    previous = _previous_route(root)
    if previous and previous != opt.path:
        data = _previous_manifest(root) or {}
        files = [str(f).replace("\\", "/")
                 for f in (data.get("files") or data.get("dosyalar") or [])]
        suffixes = (BACKUP_SUFFIX,) + LEGACY_BACKUP_SUFFIXES
        restored = set()
        for f in files:
            s = next((s for s in suffixes if f.endswith(s)), None)
            if s and (root / f).is_file():
                restored.add(f[:-len(s)])
                add(pv.removes, f"{f[:-len(s)]} (put back from its backup)")
                gone.add(f)
        for f in files:
            if any(f.endswith(s) for s in suffixes) or f in restored:
                continue
            if (root / f).is_file():
                add(pv.removes, f"{f} (previous {previous} install)")
                gone.add(f)
        if (root / HOST_DIR).is_dir():
            add(pv.removes, f"{HOST_DIR}/ (previous {previous} install)")
            gone.update(rel(p.relative_to(root))
                        for p in (root / HOST_DIR).rglob("*"))
        for name in RUNTIME_ARTIFACTS:
            if (root / name).is_file():
                add(pv.removes, f"{name} (log)")
                gone.add(name)

    def present(r: str) -> bool:
        """Will this file still be there when install() reaches it?"""
        return (root / r).is_file() and r not in gone

    def backup(r: str) -> None:
        """_backup's decision: the game's own file is kept, ours is not."""
        if present(r) and r not in preinstalled:
            add(pv.backups, r)

    def plain_backup(r: str) -> None:
        """dxvk keeps a copy whenever no backup exists yet."""
        if present(r) and not (root / (r + BACKUP_SUFFIX)).exists():
            add(pv.backups, r)

    def write(r: str, keep: bool = True) -> None:
        if keep:
            backup(r)
        add(pv.writes, r)

    # --- the RTX Remix route: everything goes inside the mod's .trex -------
    if opt.path == ROUTE_REMIX:
        if trex is None:
            pv.blockers.append(
                "No RTX Remix runtime (a '.trex' folder) was found in this "
                "game. This route is only for a game that already has an RTX "
                "Remix mod installed.")
            return pv
        try:
            tdir = rel(trex.relative_to(root))
        except ValueError:
            tdir = rel(trex)
        if not flavour and not swap:
            pv.blockers.append(
                "The RTX Remix runtime installed here has no DLSS 5 neural "
                "pass (NVIDIA's own runtime has none). Turn on 'swap the Remix "
                "runtime' to replace it with a community build that does - "
                "experimental: it also replaces any game-specific fixes the "
                "mod's own runtime carries.")
            return pv
        # A ReShade proxy left in the folder kills the game outright: a
        # 32-bit ReShade dxgi.dll took GTAIV.exe down with 0xc0000005 before
        # the window appeared. Every one goes, whatever name it is under.
        for name in RESHADE_PROXIES:
            if not present(name) or not _is_reshade(root / name):
                continue
            if name in preinstalled:
                add(pv.writes, name + ORPHAN_SUFFIX)
                add(pv.removes, f"{name} (our ReShade - it crashes a Remix game)")
            else:
                backup(name)
                add(pv.removes, f"{name} (a ReShade proxy - it crashes a "
                                f"Remix game)")
        if swap:
            write(rel(tdir, REMIX_RUNTIME))
            write(rel(tdir, REMIX_NVNGX))
            pv.warnings.append(
                "the mod's own Remix runtime is being replaced; it is backed "
                "up and 'uninstall' puts it back")
        write(rel(tdir, DLSSNR))
        try:
            crel = rel(remix.conf_path(root, trex).relative_to(root))
        except ValueError:
            crel = rel(remix.conf_path(root, trex))
        key = remix.enable_key(flavour or remix.NEURAL)
        add(pv.writes, f"{crel} ({key} = True - this one line, nothing else "
                       f"in the file is touched)")
        for r in sorted(preinstalled):
            if present(r):
                add(pv.writes, r)
        write(MANIFEST, keep=False)
        return pv

    # Another injector already under the proxy name?
    if opt.path != OPTI and proxy != VULKAN_LAYER:
        existing = root / proxy
        if existing.is_file() and not _is_reshade(existing):
            if optiscaler.is_optiscaler(existing):
                backup(proxy)
                add(pv.removes, f"{proxy} (an OptiScaler installed by hand)")
                for extra in (optiscaler.FORWARDER, optiscaler.INI):
                    if (root / extra).is_file():
                        backup(extra)
                        add(pv.removes, f"{extra} (OptiScaler, installed by hand)")
            else:
                pv.blockers.append(
                    f"{proxy} already exists but is not ReShade (DXVK, Special "
                    f"K or another injector?). Remove it first, then try again.")

    # A ReShade under another name.
    if opt.path != OPTI:
        for name in RESHADE_PROXIES:
            if name == proxy or not present(name) or not _is_reshade(root / name):
                continue
            if name in preinstalled:
                add(pv.writes, name + ORPHAN_SUFFIX)
                add(pv.removes, f"{name} (our ReShade under another name)")
            else:
                backup(name)
                add(pv.removes, f"{name} (a second ReShade copy)")

    # Add-ons of another route.
    for route, name in _foreign_addons(opt.path):
        if not present(name):
            continue
        if name in preinstalled:
            add(pv.writes, name + ORPHAN_SUFFIX)
        else:
            backup(name)
        add(pv.removes, f"{name} ({route} add-on)")

    # The game's too-old compiler goes aside; uninstall brings it back.
    if opt.path != OPTI:
        try:
            for f in root.iterdir():
                if f.is_file() and f.name.lower() in SIDELINE:
                    add(pv.backups, f"{f.name} -> {f.name}{SIDELINE_SUFFIX}")
        except OSError:
            pass

    # 0) REFramework (RE Engine games only - see reengine.py/refw.py)
    if reengine.detected(root):
        plain_backup(refw.DINPUT8)
        write(refw.DINPUT8, keep=False)

    # 0b) DXVK
    if dxvk_from:
        # A Source engine game takes it in bin, where its renderer looks (#224).
        dsub = dxvk.target_dir(root, x64, dxvk_from)
        for name in dxvk.files_for(dxvk_from) or dxvk.FILES:
            plain_backup(rel(dsub, name))
            write(rel(dsub, name), keep=False)

    # OptiScaler: the whole route in one go.
    if opt.path == OPTI:
        # The MFG package's warnings, before it is chosen for real rather
        # than in the finished-install notes only (gate 2.0.5).
        for w in _mfg_warnings(g, opt, root):
            add(pv.warnings, w)
        if opt.opti_build == optiscaler.PRESR_MFG and opt.fg and g.api == "DX12":
            add(pv.warnings, MFG_FSR_FG)
        oproxy = _opti_proxy_for(root, opt)
        for other in optiscaler.find_existing(root, ignore=oproxy):
            backup(other.name)
            add(pv.removes, f"{other.name} (another OptiScaler copy)")
        for old in optiscaler.find_legacy(root):
            backup(old.name)
            add(pv.removes, f"{old.name} (pre-0.9 OptiScaler leftover)")
        # Which archive this build installs, so the preview lists that one
        # and not whichever OptiScaler zip happens to be in the cache: with
        # two forks cached, the glob alone described the wrong package
        # (their file lists differ - docs, redistributables, weights).
        # A .7z cannot be listed at all, and neither can a build nobody has
        # downloaded yet; both fall through to naming the folders instead.
        arch = optiscaler.archive_name(opt.opti_build)
        members = (_cached_zip_members(arch)
                   if arch.lower().endswith(".zip") else None)
        if members:
            for m in members:
                if Path(m).name in optiscaler.SKIP:
                    continue
                write(oproxy if m == optiscaler.MAIN_DLL else m)
        else:
            write(oproxy)
            write(optiscaler.FORWARDER)
            write(optiscaler.INI)
            add(pv.writes, "OptiScaler/* and Licenses/* (the rest of the package)")
        write(DLSSNR)
        if _opti_needs_dlss(opt) and not (present(DLSS) and opt.keep_game_dlss
                                          and DLSS not in preinstalled):
            write(DLSS)
        elif not _opti_needs_dlss(opt):
            _nd = _opti_dlss_target(root, g, opt, ours=preinstalled)
            if _nd is not None:
                _preview_swap(write, pv, root, _nd, DLSS)
        # The person's own frame generation files, the way _place_own_fg
        # puts them in (and takes an earlier set out).
        _why_fg = _own_fg_refusal(root, opt)
        if _why_fg:
            pv.blockers.append(_why_fg)
        _fg_key, _fg_had = ownfg.recorded(_previous_manifest(root))
        for n in _fg_had:
            if n.lower() not in {d.lower() for d in ownfg.dests(opt.own_fg)} \
                    and present(n):
                _back = (root / (n + BACKUP_SUFFIX)).is_file()
                add(pv.removes, f"{n} (frame generation files are off now"
                    + ("; your own file goes back in its place)" if _back else ")"))
                preinstalled = preinstalled - {n}
        if opt.own_fg:
            for n in ownfg.dests(opt.own_fg):
                write(n)
            pv.warnings.append(f"frame generation files ({ownfg.label(opt.own_fg)}): "
                               f"{ownfg.UNTRIED}")
        for r in sorted(preinstalled):
            if present(r):
                add(pv.writes, r)
        write(MANIFEST, keep=False)
        return pv

    if getattr(g, "emu", None) is not None:
        pv.outside.append(f"{g.emu.name}: its own config is switched to the "
                          f"render backend ReShade can reach (backed up beside "
                          f"it; 'uninstall' restores it)")
    # 1) ReShade
    if g.api == "Vulkan":
        found = vulkan.existing_registration()
        if found is not None and not vulkan.is_ours(found):
            pv.outside.append(f"reuses the existing ReShade Vulkan layer ({found})")
        else:
            pv.outside.append(
                f"Vulkan layer: {vulkan.LAYER_NAME} registered for this user "
                f"(files in {vulkan.layer_dir()}) - it loads into EVERY Vulkan "
                f"application until 'uninstall' removes it")
            pv.warnings.append("the Vulkan layer is global; 'uninstall' "
                               "removes it again")
    else:
        write(proxy)
    if opt.vr and x64:
        from . import openxr
        xr_found = openxr.existing_registration()
        if xr_found is not None and not openxr.is_ours(xr_found):
            pv.outside.append(f"reuses the existing ReShade OpenXR layer ({xr_found})")
        else:
            pv.outside.append(
                f"OpenXR layer (VR): {openxr.LAYER_NAME} registered for this "
                f"user (files in {openxr.layer_dir()}) - it loads into EVERY "
                f"OpenXR application until the last VR install is removed")
        pv.warnings.append("VR through OpenXR has not been tried with a "
                           "headset by the author; OpenXR games only")
    elif opt.vr:
        pv.warnings.append("VR: the OpenXR layer is 64-bit only - nothing is "
                           "registered for this 32-bit game")
    host = HOST_DIR
    if not x64 and opt.path == FEEDER:
        add(pv.writes, rel(host, "dxgi.dll"))

    # 2) the path-specific middle
    if opt.path == BRIDGE:
        write(BRIDGE_ADDON)
        if present(LEGACY_BRIDGE_ADDON):
            add(pv.removes, f"{LEGACY_BRIDGE_ADDON} (older bridge, conflicts)")
    elif present(LEGACY_BRIDGE_ADDON):
        add(pv.removes, f"{LEGACY_BRIDGE_ADDON} (an older bridge add-on - "
                        f"ReShade would load it beside this route's; it comes "
                        f"back on uninstall)")
    if opt.path == FEEDER:
        for h in sources.RESHADE_HEADERS:
            write(rel(SHADERS, h))
        write(FEEDER_ADDON64 if x64 else FEEDER_ADDON32)
        write(rel(SHADERS, FEEDER_FX))
        if not x64:
            add(pv.writes, rel(host, FEEDER_HOST))
        if opt.provider in (3, 4) and foreign_lumenite(root, _previously_ours(root)):
            pv.warnings.append("LumeniteFX is already installed here - your "
                               "copy is used, nothing duplicated")
        elif opt.provider in (3, 4):
            listed = False
            for m in _cached_zip_members("LumeniteFX-mainline.zip") or []:
                parts = m.split("/")[1:]        # drop the archive root
                if len(parts) not in (2, 3):
                    continue
                tail = parts[-1].lower()
                where = "/".join(parts[:-1]).lower()
                if where == "shaders" and tail.endswith(".fx"):
                    if tail != LUMENITE_PROVIDER_FX.get(opt.provider, "lumenite_kernel.fx").lower():
                        continue
                    add(pv.writes, rel(SHADERS, parts[-1]))
                elif where == "shaders/include" and tail.endswith(".fxh"):
                    add(pv.writes, rel(INCLUDE, parts[-1]))
                elif where == "textures" and tail.endswith(".png"):
                    add(pv.writes, rel(TEXTURES, parts[-1]))
                else:
                    continue
                listed = True
            if not listed:
                add(pv.writes, rel(SHADERS, LUMENITE_PROVIDER_FX.get(opt.provider, "lumenite_Kernel.fx")))
                add(pv.writes, rel(INCLUDE, "lumenite_*.fxh"))
                add(pv.writes, rel(TEXTURES, "lumenite_*.png"))
        elif opt.provider == 2 or g.api == "OpenGL":
            if not foreign_lumenite(root, preinstalled, marker=VORT_FX):
                add(pv.writes, rel(SHADERS, VORT_FX))
                add(pv.writes, rel(VORT_INCLUDE, "vort_*.fxh"))
                add(pv.writes, rel(TEXTURES, VORT_TEXTURE))

    # 5/6/7) DLSS parts: in host64/ on the 32-bit feeder path
    dlss_dir = "" if (x64 or opt.path != FEEDER) else host
    if opt.path == UPSTREAM:
        write(UPSTREAM_ADDON)
    elif opt.path == STANDALONE:
        for h in sources.RESHADE_HEADERS:
            write(rel(SHADERS, h))
        write(STANDALONE_ADDON)
        write(STANDALONE_BRIDGE)
        write(rel(SHADERS, STANDALONE_FX))
        if foreign_lumenite(root, preinstalled, marker=VORT_FX):
            pv.warnings.append("VORT is already installed here - your copy "
                               "is used, nothing duplicated")
        else:
            write(rel(SHADERS, VORT_FX))
            listed = False
            for m in _cached_zip_members(sources.VORT_ZIP_NAME) or []:
                parts = m.split("/")[1:]        # drop the archive root
                if (len(parts) == 3 and parts[0].lower() == "shaders"
                        and parts[1].lower() == "includes"
                        and parts[2].lower().endswith(".fxh")):
                    add(pv.writes, rel(VORT_INCLUDE, parts[2]))
                    listed = True
            if not listed:
                add(pv.writes, rel(VORT_INCLUDE, "vort_*.fxh"))
            write(rel(TEXTURES, VORT_TEXTURE))
    else:
        write(rel(dlss_dir, RENODX_SF if opt.path == ROUTE_RENODX else RENODX))
    write(rel(dlss_dir, DLSSNR))
    game_has = present(DLSS)
    if opt.path != UPSTREAM and not (x64 and game_has and opt.keep_game_dlss):
        write(rel(dlss_dir, DLSS))
        _nd = _nested_game_dlss(root, g, opt, x64, ours=preinstalled)
        if _nd is not None and not _same_path(_nd, root / rel(dlss_dir, DLSS)):
            _preview_swap(write, pv, root, _nd, DLSS)
    if opt.path == STANDALONE and not (present(DLSSG) and opt.keep_game_dlss):
        write(DLSSG)
    if opt.dlssd:
        rr = _find_runtime(root, DLSSD, g.folder)
        if rr is not None:
            try:
                write(str(rr.relative_to(root)))
            except ValueError:
                # The game keeps it above the install folder, which is what
                # pv.outside exists to say out loud.
                write(str(rr))
                pv.outside.append(
                    f"replaces the game's own {DLSSD} at {rr} - outside the "
                    f"install folder, backed up beside itself")

    # 8b) RTX 40 multi-frame generation, when it applies here
    if opt.mfg and mfg.applies(gpu.detect()[1], g.api, root, g.folder)[0]:
        lname = mfg.loader_name(g.exe,
                                {refw.DINPUT8} if reengine.detected(root) else set(),
                                root)
        plug = mfg.existing_plugins(root) if lname is None else None
        if lname is None and plug is None:
            pv.warnings.append(
                f"multi-frame generation will be skipped: {g.exe.name if g.exe else 'the executable'} "
                f"imports none of {', '.join(mfg.LOADER_NAMES)} that is free here, so the ASI "
                f"loader has no name it would be loaded under")
        elif lname is None:
            # Another mod's loader is already here and its name is not
            # ours to take: the unlock goes into its plugins folder (#137).
            for n in mfg.PLUGIN_FILES:
                write(f"{mfg.PLUGINS_DIR}/{n}", keep=False)
            write(mfg.UI_ADDON, keep=False)
        else:
            for n in mfg.FILES:
                write(n, keep=False)
            plain_backup(lname)
            write(lname, keep=False)
            write(lname[:-4] + ".ini")
    elif not opt.mfg:
        # The same list remove_leftovers and the manifest-less uninstall use:
        # an unlock that went into another loader's plugins folder is removed
        # from there too, and the preview has to say so.
        _pre_low = {p.lower() for p in preinstalled}
        # remove_leftovers returns early unless one of the unlock's own files
        # is on the record, so the loader only comes out with them. The
        # preview must promise exactly that and no more.
        _unlock_here = any(
            n.lower() in _pre_low for n in
            [*mfg.FILES] + [f"{mfg.PLUGINS_DIR}/{x}" for x in mfg.PLUGIN_FILES])
        for n in [*mfg.FILES] + [f"{mfg.PLUGINS_DIR}/{x}"
                                 for x in mfg.PLUGIN_FILES]:
            if n in preinstalled or n.lower() in _pre_low:
                add(pv.removes, f"{n} (multi-frame generation is off now)")
        # ...and the loader itself, which remove_leftovers also takes out -
        # with the file of theirs that was under that name going back. That
        # is the line a person reads the preview for.
        for n in mfg.LOADER_NAMES if _unlock_here else []:
            if n.lower() not in _pre_low:
                continue
            # One line, not two: the same name listed twice - once as a
            # removal and once as a restore - reads as two files.
            _back = (root / (n + mfg.BACKUP_SUFFIX)).is_file()
            add(pv.removes,
                f"{n} (the ASI loader, multi-frame generation is off now"
                + ("; your own file goes back in its place)" if _back else ")"))
            # remove_leftovers unlinks the loader's ini as well, and the
            # preview's ON branch writes it - so the OFF branch names it.
            _lini = n[:-4] + ".ini"
            if _lini.lower() in _pre_low:
                add(pv.removes, f"{_lini} (the loader's settings)")
    # A pinned feeder build older than the D3D10 relay is a blocker, and
    # needs no network to say so.
    if opt.path == FEEDER and g.api == "DX10" and opt.feeder_tag and \
            sources.feeder_key(opt.feeder_tag) < sources.feeder_key(sources.FEEDER_DX10_MIN):
        pv.blockers.append(f"DLSS5-Feeder {opt.feeder_tag} refuses Direct3D 10 games - "
                           f"pick {sources.FEEDER_DX10_MIN} or newer in 'feeder build'")

    # 8/9/10) host64, ReShade configuration, the cfg
    if not x64 and opt.path == FEEDER:
        add(pv.writes, rel(host, "ReShade.ini"))
    write("ReShade.ini")
    if opt.path == FEEDER:
        write("ReShadePreset.ini")
        write(feedcfg.NAME)
    elif opt.path == BRIDGE:
        write(feedcfg.BRIDGE_NAME)

    # The manifest carries forward what an earlier install of ours left and
    # this one does not touch, so those are recorded as well.
    for r in sorted(preinstalled):
        if present(r):
            add(pv.writes, r)
    write(MANIFEST, keep=False)
    return pv


def preview_lines(pv: Preview) -> list[str]:
    """The preview as short lines for the log widget."""
    out: list[str] = []
    for b in pv.blockers:
        out.append(f"cannot install: {b}")
    if pv.blockers:
        return out
    for w in pv.warnings:
        out.append(f"warning: {w}")
    if pv.removes:
        out.append(f"will clean up first: {', '.join(pv.removes)}")
    n = len(pv.writes)
    shown = ", ".join(pv.writes[:3]) + (", ..." if n > 3 else "")
    out.append(f"will write {n} file{'s' if n != 1 else ''} ({shown})")
    if pv.backups:
        out.append(f"will back up: {', '.join(pv.backups)}")
    else:
        out.append("nothing of yours is overwritten - no backups needed")
    if pv.outside:
        for o in pv.outside:
            out.append(f"outside: {o}")
    else:
        out.append("nothing is written outside this folder")
    return out


def _install_feeder_parts(g, opt, root: Path, host: Path, x64: bool,
                          rep: "Report", begin, dl, log) -> None:
    """Shader headers, the feeder add-on and the motion-vector provider.

    Only the feeder path needs any of this: it is the only one that builds a
    DLSS contract out of ReShade shaders. The native and bridge paths hook the
    game's real NGX calls instead.
    """
    begin("ReShade shader headers")
    for h in sources.RESHADE_HEADERS:
        dest = root / SHADERS / h
        dest.parent.mkdir(parents=True, exist_ok=True)
        _backup(dest, rep, root)
        _write_bytes(net.fetch_text(sources.RESHADE_HEADERS_BASE + h), dest, rep, root)
        rep.written.append(str(Path(SHADERS) / h))
    log(f"      {', '.join(sources.RESHADE_HEADERS)}")

    begin("DLSS5-Feeder")
    tag, assets = sources.resolve_feeder(prerelease=opt.feeder_prerelease,
                                         tag=opt.feeder_tag)
    log(f"      DLSS5-Feeder {tag}"
        + ("  (this exact build, as requested)" if opt.feeder_tag
           else "  (pre-release, as requested)" if opt.feeder_prerelease else ""))
    rep.components["feeder"] = tag
    if g.api == "DX10" and sources.feeder_key(tag) < sources.feeder_key(sources.FEEDER_DX10_MIN):
        raise InstallError(
            f"DLSS5-Feeder {tag} refuses Direct3D 10 games. Pick "
            f"{sources.FEEDER_DX10_MIN} or newer in 'feeder build' - that is "
            f"the first build with the D3D10 relay - and install again.")
    addon = FEEDER_ADDON64 if x64 else FEEDER_ADDON32
    needed = (addon, FEEDER_FX) + ((FEEDER_HOST,) if not x64 else ())
    # From 0.10.0 the feeder ships one zip instead of loose files.
    zurl = next((u for n, u in assets.items()
                 if n.lower().endswith(".zip") and "feeder" in n.lower()), None)
    zpath = None
    if zurl and any(n not in assets for n in needed):
        zpath = dl(zurl, f"{tag}-{zurl.rsplit('/', 1)[-1]}")
    for name in needed:
        dest = (root / SHADERS / name) if name.endswith(".fx") else \
               (host / name if name == FEEDER_HOST else root / name)
        if name in assets:
            f = dl(assets[name], f"{tag}-{name}")
            _copy(f, dest, rep, root)
        elif zpath is not None:
            _extract(zpath, name, dest, rep, root)
            rep.written.append(str(dest.relative_to(root)))
        else:
            raise InstallError(f"The DLSS5-Feeder release has no {name}.")
        log(f"      {dest.relative_to(root)}")

    if opt.provider in (3, 4):
        begin("LumeniteFX (motion vectors)")
        theirs = foreign_lumenite(root, rep.preinstalled)
        if theirs:
            # ReShade loads every .fx under reshade-shaders, whatever the
            # subfolder; a second lumenite_Kernel.fx beside theirs is two
            # copies of the same technique and a red error in the overlay.
            # Theirs wins - it is their install, and the technique name
            # in ReShade.ini matches by file name, not by path.
            rel_t = theirs.relative_to(root)
            rep.notes.append(f"LumeniteFX is already installed at {rel_t.parent} "
                             f"- your copy is used, nothing duplicated")
            rep.skipped.append("LumeniteFX (already installed)")
            log(f"      already installed at {rel_t.parent} - using your copy, "
                f"no duplicate")
            return
        z = dl(sources.LUMENITE_ZIP, "LumeniteFX-mainline.zip")
        want_fx = LUMENITE_PROVIDER_FX.get(opt.provider, "lumenite_Kernel.fx")
        w = net.extract_tree(z, "Shaders", str(SHADERS), root, only_ext=(".fx",),
                             only_names=(want_fx,), writer=lambda src, dst: _copy(src, dst, rep, root))
        w += net.extract_tree(z, "Shaders/include", str(INCLUDE), root,
                              only_ext=(".fxh",), writer=lambda src, dst: _copy(src, dst, rep, root))
        w += net.extract_tree(z, "Textures", str(TEXTURES), root,
                              only_ext=(".png",), writer=lambda src, dst: _copy(src, dst, rep, root))
        # Effects an earlier install of ours dropped in are taken back out:
        # they were compiling for nothing.
        for old in sorted((root / SHADERS).glob("lumenite_*.fx")):
            rel_old = str(old.relative_to(root))
            if old.name.lower() != want_fx.lower() and rel_old.replace("\\", "/") in {
                    p.replace("\\", "/") for p in rep.preinstalled}:
                try:
                    _remove_for_install(old, rep, root)
                    rep.notes.append(f"removed {old.name} - an effect the feed does "
                                     f"not use, left by an earlier install")
                except OSError:
                    pass
        for p_ in w:
            rep.written.append(str(p_.relative_to(root)))
        log(f"      {want_fx} + includes + texture ({len(w)} files) - only the "
            f"provider the feed reads, not the whole pack")
    elif opt.provider == 2:
        _install_vort(root, rep, dl, log, begin)


def _install_vort(root: Path, rep: "Report", dl, log, begin) -> None:
    """VORT Motion beside the game: the .fx, its includes and its texture.

    A copy the person installed themselves is used as it is - a second
    vort_Motion.fx under reshade-shaders is two techniques of one name and
    a red error in the overlay.
    """
    begin("VORT Motion (motion vectors)")
    theirs = foreign_lumenite(root, rep.preinstalled, marker=VORT_FX)
    if theirs:
        rel_t = theirs.relative_to(root)
        rep.notes.append(f"VORT is already installed at {rel_t.parent} "
                         f"- your copy is used, nothing duplicated")
        rep.skipped.append("VORT (already installed)")
        log(f"      already installed at {rel_t.parent} - using your "
            f"copy, no duplicate")
        return
    z = dl(sources.VORT_ZIP, sources.VORT_ZIP_NAME)
    _extract(z, "Shaders/" + VORT_FX, root / SHADERS / VORT_FX, rep, root)
    rep.written.append(str(SHADERS / VORT_FX))
    w = net.extract_tree(z, "Shaders/Includes", str(VORT_INCLUDE),
                         root, only_ext=(".fxh",), writer=lambda src, dst: _copy(src, dst, rep, root))
    for p_ in w:
        rep.written.append(str(p_.relative_to(root)))
    _extract(z, "Textures/" + VORT_TEXTURE,
             root / TEXTURES / VORT_TEXTURE, rep, root)
    rep.written.append(str(TEXTURES / VORT_TEXTURE))
    log(f"      {VORT_FX} + {len(w)} includes + {VORT_TEXTURE} "
        f"(Vortigern, MIT)")


# ---------------------------------------------------------------- install

LUMENITE_MARKER = "lumenite_Kernel.fx"

# Only the motion-vector provider the feed will read, never the whole pack.
# LumeniteFX ships eight heavy effects (RTAO, SSSR, TRAA, bloom...) that the
# feed does not use; ReShade compiled them all at start-up, and on a 32-bit
# game behind a translation layer the compile stall was long enough for the game to
# crash on its own (Bayonetta, issue #2, confirmed from the dump by the
# feeder's author). The provider's own includes are small and all needed.
LUMENITE_PROVIDER_FX = {3: "lumenite_Kernel.fx", 4: "lumenite_QuantMotion.fx"}
LUMENITE_INCLUDES = ("lumenite_Projections.fxh", "lumenite_Helpers.fxh",
                     "lumenite_Compute.fxh", "lumenite_ColorManagement.fxh")
LUMENITE_TEXTURES = ("lumenite_bluenoise256.png",)


def foreign_lumenite(root: Path, preinstalled=(),
                     marker: str = LUMENITE_MARKER) -> Path | None:
    """A LumeniteFX the person installed themselves, anywhere under
    reshade-shaders - or None. A copy an earlier install of OURS wrote (in
    the manifest) does not count: that one is overwritten as usual.

    `marker` makes the same question askable of VORT (vort_Motion.fx): the
    standalone route ships it, and a second copy beside the person's own is
    two techniques of the same name and a red error in the overlay."""
    base = root / "reshade-shaders"
    try:
        hits = sorted(base.rglob(marker))
    except OSError:
        return None
    ours = {str(Path(p)).replace("\\", "/").lower() for p in preinstalled}
    for h in hits:
        try:
            rel = str(h.relative_to(root)).replace("\\", "/").lower()
        except ValueError:
            continue
        if rel in ours:
            continue
        if h.parent == root / SHADERS and not preinstalled:
            # Same place we would write to, and no record of ours: theirs.
            return h
        if h.parent != root / SHADERS:
            return h
    return None


def _previous_manifest(root: Path) -> dict | None:
    """The install record already in this folder, ours or an older release's."""
    for name in (MANIFEST,) + LEGACY_MANIFESTS:
        p = root / name
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            continue
    return None


def _previous_route(root: Path) -> str | None:
    """Which route is recorded as installed here, if any."""
    data = _previous_manifest(root)
    if data is None:
        return None
    # A record a failed first install left holding only its reason: that
    # route is not in the folder, and "removing the previous X install" /
    # "replaced a previous X install" over it were untrue (gate 2.0.7).
    if net.ROLLED_BACK_NOTE in (data.get("notes") or []) \
            and not (data.get("files") or data.get("dosyalar")):
        return None
    # v1.0-v1.2 wrote no route at all; everything then was the feeder.
    return data.get("path") or FEEDER


def _previously_ours(root: Path) -> set:
    """Relative paths an earlier install of ours wrote here.

    Read before anything is touched, because these must be overwritten rather
    than "preserved" - preserving one turns uninstall into a reinstall.
    """
    data = _previous_manifest(root) or {}
    files = data.get("files") or data.get("dosyalar") or []
    out = set()
    for f in files:
        f = str(f).replace("\\", "/")
        if any(f.endswith(s) for s in (BACKUP_SUFFIX,) + LEGACY_BACKUP_SUFFIXES):
            continue
        out.add(f)
    return out


# Every add-on this tool ever installs, and the route each belongs to.
# ReShade loads EVERY .addon64 in the folder, so two of these present at once
# means two of them try to establish a DLSS contract in the same process.
# Only the add-ons themselves: a stray .cfg conflicts with nothing, and
# removing one would be taking away a file that may well be the user's.
# The standalone route's nvngx.dll is not an add-on, but NGX loads it from
# the game folder ahead of the driver's own - as much a hook as any of these.
ROUTE_ADDONS = {
    FEEDER: (FEEDER_ADDON64, FEEDER_ADDON32),
    BRIDGE: (BRIDGE_ADDON,),
    ROUTE_RENODX: (RENODX_SF,),
    UPSTREAM: (UPSTREAM_ADDON,),
    STANDALONE: (STANDALONE_ADDON, STANDALONE_BRIDGE),
}


def _foreign_addons(keep: str) -> list[tuple[str, str]]:
    """(route, filename) of every add-on that must not sit beside `keep`."""
    out = [(r, n) for r, names in ROUTE_ADDONS.items() if r != keep for n in names]
    # renodx-dlss5 is shared by the native, bridge and feeder routes, so it is
    # not in the table - but it, ShortFuse's build and neural-upstream all
    # hook NGX, and two loaded together fight over the same entry points.
    # The standalone add-on runs the network itself; renodx-dlss5 beside it
    # would process the frame twice.
    if keep in (ROUTE_RENODX, UPSTREAM, STANDALONE, ROUTE_REMIX):
        out.append((NATIVE, RENODX))
    return out


def _clear_stale_reshade(root: Path, keep: str, rep: Report, log) -> None:
    """Move every ReShade proxy that is not the one being installed out of
    ReShade's reach. Ours go aside as orphans (uninstall deletes them); one we
    did not record is backed up first, so uninstall puts it back.

    `keep` = "" takes ALL of them out, which is what the REMIX route needs:
    a ReShade proxy of any name crashes a Remix game before it draws.

    d3d9.dll is in RESHADE_PROXIES and, in a Remix game, d3d9.dll IS the
    Remix runtime stub. _is_reshade() is consulted first for exactly that
    reason and the stub fails it (no "ReShade" string, and under a megabyte),
    so the runtime is never mistaken for a stale ReShade copy - but the check
    is spelled out here too, because getting it wrong deletes the mod.
    """
    for name in RESHADE_PROXIES:
        if name == keep:
            continue
        p = root / name
        if not _is_reshade(p):
            continue
        if name.lower() == "d3d9.dll" and remix.is_remix_game(root):
            continue
        try:
            _remove_for_install(p, rep, root)
        except OSError as e:
            log(f"      could not move {name} aside ({e}) - if the game will "
                f"not start, remove it by hand")
            raise InstallError(f"Could not safely move the conflicting {name} aside ({e}); the install stopped and recovery entries were kept.") from e
        rep.notes.append(f"moved aside a second ReShade copy: {name}")
        log(f"      moved {name} out of the way - a second ReShade under "
            f"another name would stop the game from starting")


def _purge_foreign_addons(root: Path, keep: str, rep: Report, log) -> None:
    """Remove add-ons belonging to a route we are not installing.

    Uninstalling the recorded route handles the ordinary case, but only when
    the manifest is accurate. An install interrupted half way, a manifest
    written by a release that did not record the route, or a folder set up
    twice can all leave an add-on behind that nothing knows about - and
    ReShade will still load it.

    Seen in the wild: MGS V had dlss5-bridge.addon64 recorded and
    dlss5-feed.addon64 orphaned beside it. Both registered, both tried to
    build a contract, and the game exited before it ever created a swapchain.
    """
    for route, name in _foreign_addons(keep):
        if True:
            p = root / name
            if not p.is_file():
                continue
            try:
                _remove_for_install(p, rep, root)
                rep.notes.append(f"moved aside an orphaned {route} add-on: {name}")
                log(f"      moved {name} out of the way - it is a {route} "
                    f"add-on and ReShade would load it alongside this one")
            except OSError as error:
                log(f"      WARNING: {name} belongs to the {route} route and "
                    f"could not be moved; the two will conflict")
                raise InstallError(f"Could not safely move the conflicting {name} aside ({error}); the install stopped and recovery entries were kept.") from error


def _write_manifest(root: Path, g: games.Game, opt: Options, rep: Report,
                    proxy: str, level: str, complete: bool) -> bool:
    """Record what was written; False when the record could not be saved.

    Also written when an install FAILS part way: without it the orphaned files
    could not be cleaned up afterwards. A failed write leaves the previous
    record whole, which may be an older attempt's - so the caller is told,
    rather than finding a record on disk and trusting it (gate 2.0.7).
    """
    # The remembered folder walk is dropped here rather than only at the
    # start of install(): the preview and the swap now READ that cache
    # mid-install, so an install that writes a runtime would otherwise
    # leave the pre-write picture behind for the rest of the session
    # (gate 1.9.1).
    try:
        dlss.forget_walk(g.folder)
        dlss.forget_walk(root)
    except Exception:
        pass
    # Carry forward what an earlier install left that this one did not touch.
    # Without this the record only covers the LAST install, so a file written
    # the first time and merely left alone the second - nvngx_dlss.dll, say -
    # was orphaned and no uninstall could ever remove it.
    # Compared with one separator: _copy records "a\b", the old record
    # read back as "a/b", and the same file went into the record twice.
    previous = _previous_manifest(root) or {}
    old_sidelined = previous.get("sidelined") or []
    old_sidelined_hashes = previous.get("sidelined_hashes") or {}
    if not isinstance(old_sidelined, list) or not all(isinstance(name, str) for name in old_sidelined) or not isinstance(old_sidelined_hashes, dict):
        raise InstallError("The previous recovery record has malformed sidelined originals; it was preserved.")
    rep.sidelined = list(dict.fromkeys(old_sidelined + rep.sidelined))
    rep.sidelined_hashes = dict(old_sidelined_hashes, **rep.sidelined_hashes)
    if not rep.remix and isinstance(previous.get("remix"), dict):
        rep.remix = dict(previous["remix"])
    rep.written = list(dict.fromkeys(rep.written))
    hashes = dict(rep.hashes)
    for rel in rep.written:
        if rel not in hashes:
            digest = _record_hash(previous, rel)
            if digest:
                hashes[rel] = digest
                rep.hashes[rel] = digest
    have = {w.replace("\\", "/") for w in rep.written}
    for rel in sorted(rep.preinstalled):
        try:
            _safe_target(root, root / rel, rep.game_root)
        except net.OutsideError:
            continue
        if rel.replace("\\", "/") in have:
            continue
        if (root / rel).exists():
            rep.written.append(rel)
            digest = _record_hash(previous, rel)
            if digest:
                hashes[rel] = digest
    # And the game's original beside any file on the record: whichever path
    # skipped _backup this time (a file of ours from last time, a step not
    # taken), the backup an earlier install made stays on the record, so
    # uninstall puts the original back. Losing it here is how a reinstall
    # left the swapped Remix runtime unrestored.
    have = {w.replace("\\", "/") for w in rep.written}
    for w in list(rep.written):
        if any(w.endswith(s) for s in (BACKUP_SUFFIX,) + LEGACY_BACKUP_SUFFIXES):
            continue
        b = w + BACKUP_SUFFIX
        if b.replace("\\", "/") not in have and (root / b).is_file():
            rep.written.append(b)
            have.add(b.replace("\\", "/"))
            digest = _record_hash(previous, b)
            if digest:
                hashes[b] = digest
                rep.hashes[b] = digest
    gpu_records = rep.gpu_pref
    if gpu_records is None:
        gpu_records = list((_previous_manifest(root) or {}).get("gpu_pref") or [])

    try:
        _write_atomic(root / MANIFEST, json.dumps({
            "version": 1,
            # Which BUILD of this tool set the folder up. The report carries
            # the version that is running now; nothing said what wrote the
            # install, so a folder built by 1.5.0 and diagnosed by 1.8.2
            # looked the same as one installed a minute ago (#215).
            "tool": update.VERSION,
            "complete": complete,
            "exe": g.exe.name if g.exe else None,
            "bitness": g.bitness,
            "api": g.api,
            "proxy": proxy,
            "opti_build": opt.opti_build if opt.path == OPTI else "",
            "provider": opt.provider,
            "path": opt.path,
            "reliability": level,
            "files": rep.written,
            "hashes": hashes,
            "skipped": rep.skipped,
            "notes": rep.notes,
            "warnings": rep.warnings,
            "feed_cfg": opt.feed,
            "nr": opt.nr,
            "fg": opt.fg,
            "mfg": opt.mfg,
            "vr": bool(opt.vr) and opt.path not in (OPTI, ROUTE_REMIX),
            "native_dlss": opt.native_dlss,
            "upscaler": opt.upscaler,
            "keep_game_dlss": opt.keep_game_dlss,
            "feeder_prerelease": opt.feeder_prerelease,
            "feeder_tag": opt.feeder_tag,
            "dxvk": rep.components.get("dxvk"),
            "components": rep.components,
            "kind": g.kind,
            "sidelined": rep.sidelined,
            "sidelined_hashes": rep.sidelined_hashes or previous.get("sidelined_hashes") or {},
            "remix": rep.remix,
            # which of the files above are the person's own frame generation
            # files: the diagnosis does not name them as another hook, and
            # a reinstall with the option off takes exactly these out
            "own_fg": ({"recipe": rep.components["own_fg"],
                        "files": ownfg.dests(rep.components["own_fg"])}
                       if rep.components.get("own_fg") else {}),
            "gpu_pref_on": bool(opt.gpu_pref),
            "gpu_pref": gpu_records,
        }, ensure_ascii=False, indent=2))
    except OSError:
        return False
    return True


def _write_atomic(path: Path, text: str) -> None:
    """Write beside, then replace: a failed write leaves the old file whole.

    write_text() empties the file first. On a full drive that lost the
    previous install's record - the list uninstall reads - and the note
    saying the drive was full was never written either.
    """
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".aio-part", dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        # An antivirus or the indexer holding the old file for a moment
        # makes the replace fail; a moment later it goes through.
        for attempt in range(3):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == 2:
                    raise
                time.sleep(0.1)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def options_from_manifest(root: Path) -> Options | None:
    """Rebuild the choices an earlier install was made with.

    This is what "update" means: the same route, provider, dials and
    add-on family, with every component fetched fresh. Versions are NOT
    pinned to what was installed - that is the point.
    """
    data = _previous_manifest(root)
    if not data:
        return None
    path = data.get("path") or FEEDER
    if path not in (NATIVE, BRIDGE, FEEDER, OPTI, ROUTE_RENODX, UPSTREAM,
                    STANDALONE, ROUTE_REMIX):
        return None
    upscaler = str(data.get("upscaler") or "")
    return Options(
        upscaler=upscaler,
        provider=int(data.get("provider") or 3),
        feed=dict(data.get("feed_cfg") or {}),
        nr=dict(data.get("nr") or {}),
        fg=bool(data.get("fg", False)),
        mfg=bool(data.get("mfg", False)),
        vr=bool(data.get("vr", False)),
        path=path,
        keep_game_dlss=bool(data.get("keep_game_dlss", True)),
        feeder_prerelease=bool(data.get("feeder_prerelease", False)),
        feeder_tag=str(data.get("feeder_tag") or ""),
        # OptiScaler used to imply the game's own DLSS; with an upscaler
        # recorded it is OptiScaler's DLSS in place of the game's FSR/XeSS.
        native_dlss=(path in (NATIVE, UPSTREAM) or (path == OPTI and not upscaler)
                     or bool(data.get("native_dlss", False))),
        opti_proxy=(data.get("proxy") or "") if path == OPTI else "",
        opti_build=str(data.get("opti_build") or "") if path == OPTI else "",
        # A set the person pressed 'forget them' on reads as none, so the
        # next install takes it out (gate 2.0.7).
        own_fg=(ownfg.recorded(data)[0] if path == OPTI
                and ownfg.recorded(data)[0] in ownfg.RECIPES
                and not ownfg.forgotten(ownfg.recorded(data)[0]) else ""),
        # A runtime we swapped last time must be swapped again on an update,
        # or the update would put the mod's neural-pass-less runtime back.
        remix_swap=bool((data.get("components") or {}).get("remix_runtime")),
        dlssd=str((data.get("components") or {}).get("dlssd") or ""),
        # DXVK ticked by hand and ReShade's name picked by hand ("try d3d11.dll
        # if dxgi does nothing") are what made the game work; an update that
        # dropped them put it back to the state that did not. The record
        # holds the DXVK version when it went in, and the proxy name used.
        dxvk=bool(data.get("dxvk")) and path in (NATIVE, BRIDGE, FEEDER),
        reshade_proxy=(str(data.get("proxy") or "")
                       if path not in (OPTI, ROUTE_REMIX)
                       and str(data.get("proxy") or "") in RESHADE_PROXIES else ""),
        gpu_pref=bool(data.get("gpu_pref_on", True)),
    )


def _gpu_exes(root: Path, g: games.Game, opt: Options) -> list[Path]:
    """The programs that have to draw on the NVIDIA card: the game, and the
    32-bit feeder's 64-bit helper, which is where NGX runs for it."""
    out: list[Path] = []
    if getattr(g, "exe", None):
        out.append(Path(g.exe))
    if opt.path == FEEDER and g.bitness != 64:
        out.append(root / HOST_DIR / FEEDER_HOST)
    return out


def _gpu_pref_line(root: Path, g: games.Game, opt: Options) -> str:
    """The preview's line for the graphics preference, or ""."""
    if not opt.gpu_pref:
        return ""
    other = gpupref.other_gpu()
    if not other:
        return ""
    names = [p.name for p in _gpu_exes(root, g, opt)]
    if not names:
        return ""
    return (f"Windows graphics setting: {' and '.join(names)} set to 'High "
            f"performance' (the NVIDIA card, not the {other} one) for this "
            f"user. A choice you already made there is kept. 'uninstall' "
            f"(--remove on the command line) takes it back out")


def _gpu_records(root: Path, g: games.Game, records) -> list[dict]:
    """A local recovery record can only restore this game's program settings."""
    out = []
    for row in records if isinstance(records, list) else ():
        if not isinstance(row, dict) or not isinstance(row.get("exe"), str):
            continue
        path = Path(row["exe"])
        if not path.is_absolute() or path.suffix.lower() != ".exe":
            continue
        try:
            _safe_target(root, path, g.folder)
        except net.OutsideError:
            continue
        out.append(row)
    return out


def _set_gpu_pref(root: Path, g: games.Game, opt: Options, rep: Report, log) -> None:
    """Apply - or take back, when the box is off - the graphics preference.

    Never stops an install: it is a convenience on top of files that are
    already in place."""
    before = _gpu_records(root, g, (_previous_manifest(root) or {}).get("gpu_pref"))

    def remember(records):
        rep.gpu_pref = list(records)
        for row in before:
            if not any(gpupref._same(row["exe"], item["exe"]) for item in rep.gpu_pref):
                rep.gpu_pref.append(row)
        _checkpoint(rep)

    try:
        if not opt.gpu_pref or not gpupref.hybrid():
            if gpupref.restore(before):
                log("      Windows graphics setting taken back out")
            rep.gpu_pref = []
            return
        exes = _gpu_exes(root, g, opt)
        for exe in exes:
            _safe_target(root, exe, g.folder)
        with prefs.mutation_lock():
            records, theirs = gpupref.apply(exes, before, checkpoint=remember)
        # An exe from an earlier install that this one no longer targets (the
        # person picked another executable): still ours, still on the record.
        for r in before:
            if not any(gpupref._same(r.get("exe", ""), x.get("exe", "")) for x in records) \
                    and gpupref.chosen(r.get("exe", "")) == gpupref.HIGH:
                records.append(r)
        rep.gpu_pref = records
        for exe in exes:
            if any(gpupref._same(exe, t) for t in theirs):
                log(f"      {exe.name}: your own Windows graphics setting is kept")
                rep.notes.append(f"{exe.name} already had a Windows graphics setting "
                                 f"(Settings > System > Display > Graphics); it was left as it is")
            elif any(gpupref._same(exe, r.get("exe", "")) for r in records):
                log(f"      {exe.name}: Windows graphics setting -> High performance")
        if any(r.get("exe") for r in records):
            rep.notes.append(
                f"Windows graphics setting 'High performance' is set for "
                f"{', '.join(Path(r['exe']).name for r in records)} - the NVIDIA "
                f"card, not the {gpupref.other_gpu()} one. 'uninstall' takes it "
                f"back out")
    except Exception as e:
        log(f"      Windows graphics setting could not be fully applied ({e}); recovery entries were kept")
        rep.warnings.append(f"could not set the Windows graphics setting to High "
                            f"performance ({e}); set it by hand in Settings > System > "
                            f"Display > Graphics if the game runs on the other GPU")
        if rep.gpu_pref is None:
            rep.gpu_pref = before


def _running_processes() -> set[str]:
    """Lower-cased names of running executables, best effort."""
    try:
        import subprocess
        out = subprocess.run(["tasklist", "/fo", "csv", "/nh"],
                             capture_output=True, text=True, timeout=15,
                             creationflags=0x08000000).stdout
        return {line.split('","')[0].lstrip('"').lower()
                for line in out.splitlines() if line.startswith('"')}
    except Exception:
        return set()


def preflight(g: games.Game) -> None:
    """Fail early and clearly instead of part way through with a traceback.

    A half-written install leaves the game in a worse state than not starting,
    so the two things that actually stop us - the folder not being writable
    and the game holding its files open - are checked up front.
    """
    root = g.install_dir
    if not games._isdir(root):
        raise InstallError(f"{root} does not exist.")

    try:
        with tempfile.NamedTemporaryFile(prefix=".dlss5-autopilot-write-test-",
                                         dir=root) as probe:
            probe.write(b"x")
    except PermissionError as e:
        if games.is_locked_store_path(root):
            # Xbox / Game Pass: the folder is owned by the system, and
            # elevation does not help - the Xbox app has the switch for it.
            from . import log
            log.write(f"preflight: cannot write into {root}: {e}", "warn")
            raise InstallError(
                f"No permission to write into:\n{root}\n\n"
                f"{games.XBOX_HINT}") from None
        raise InstallError(
            f"No permission to write into:\n{root}\n\n"
            f"Close the game if it is running, then try again. If that is not "
            f"it, right-click DLSS5-AIO.exe and choose 'Run as "
            f"administrator' - some games installed outside Steam or Epic sit "
            f"in folders only an administrator can write to.") from None
    except OSError as e:
        if net.is_disk_full(e):
            raise InstallError(net.disk_full_message(e, root, net.CACHE)) from None
        raise InstallError(f"Cannot write into {root}: {e}") from None

    if g.exe and g.exe.name.lower() in _running_processes():
        raise InstallError(
            f"{g.exe.name} is running. Close the game first - Windows will not "
            f"let anything replace files a running program has open, and a "
            f"half-finished install is worse than none.")

def _sideline(root: Path, rep: Report, log) -> None:
    """Move a game-shipped file that breaks the neural pass out of the way.

    Only when the file is really the game's: one a previous install of ours
    already moved has the suffix and is left alone. The rename is recorded
    under its own manifest key, never in `files`, because uninstall deletes
    everything in `files`.
    """
    try:
        present = {f.name.lower(): f for f in root.iterdir() if f.is_file()}
    except OSError:
        return
    for name in SIDELINE:
        f = present.get(name)
        if f is None:
            continue
        moved = f.with_name(f.name + SIDELINE_SUFFIX)
        try:
            _safe_target(root, f, rep.game_root)
            _safe_target(root, moved, rep.game_root)
            digest = net.sha256(f)
            rep.sidelined.append(f.name)
            rep.sidelined_hashes[f.name] = net.sha256(moved) if moved.is_file() else digest
            _checkpoint(rep)
            if moved.exists():
                if net.sha256(moved) != digest:
                    kept = _displace(f)
                    rep.notes.append(f"kept changed {f.name} as {kept.name}")
                f.unlink()
            else:
                f.rename(moved)
        except OSError as e:
            rep.warnings.append(f"{f.name} could not be moved aside ({e}); "
                                f"if it is too old for the neural pass, "
                                f"nothing will visibly happen in game")
            continue
        rep.notes.append(f"{f.name} renamed to {moved.name}: the game's copy "
                         f"is older than Windows' and the neural pass will not "
                         f"compile against it; uninstall puts it back")
        log(f"      {f.name} moved aside ({moved.name}) - the game's copy "
            f"is too old for the neural pass; Windows' own is used instead")


def _restore_sidelined(root: Path, names, log, hashes=None, failed=None) -> list[str]:
    """Undo _sideline: the game's file goes back under its own name."""
    back: list[str] = []
    cands = names if isinstance(names, list) else []
    hashes = hashes if isinstance(hashes, dict) else {}
    for name in cands:
        if not isinstance(name, str) or name.lower() not in SIDELINE:
            log(f"ignored an invalid sidelined file: {name}")
            continue
        moved = root / (name + SIDELINE_SUFFIX)
        orig = root / name
        try:
            _safe_target(root, moved)
            _safe_target(root, orig)
            digest = hashes.get(name)
            if not moved.is_file():
                if digest and orig.is_file() and net.sha256(orig) == digest:
                    continue
                raise OSError("its recorded original backup is missing; the recovery entry was kept")
            if not digest or net.sha256(moved) != digest:
                raise OSError("its original bytes cannot be verified; the moved file was kept")
            if orig.exists():
                if net.sha256(orig) != digest:
                    kept = _displace(orig)
                    log(f"kept changed {name} as {kept.name}")
            _atomic_copy(moved, orig)
            moved.unlink()
            back.append(name)
            log(f"restored: {name} (the game's own file, moved aside)")
        except (OSError, net.OutsideError) as e:
            log(f"could not restore: {name} ({e})")
            if failed is not None:
                failed.append(name + SIDELINE_SUFFIX)
    return back


@gamelock.exclusive
def install(g: games.Game, opt: Options, on_step=None, on_prog=None, on_log=None) -> Report:
    # "the version list is 14h old" is a sentence about one install. It was
    # module state that nothing ever cleared, so the next install in the
    # same session repeated it whether or not it had fallen back to
    # anything - and now that every component can fall back, it would be
    # repeated far more often.
    sources.last_fallback = None
    _safe_target(g.folder, g.install_dir)
    # The detection walk is remembered per folder; writing into it makes
    # that memory wrong.
    dlss.forget_walk(g.folder)
    dlss.forget_walk(g.install_dir)
    ok, why = check_supported(g)
    if not ok:
        raise InstallError(why)
    # Before a single byte is written: a Remix game takes the remix route and
    # nothing else. A ReShade proxy crashes it before it draws (seen on GTA
    # IV), and on DX9 our own d3d9.dll would land on top of the Remix
    # runtime itself.
    if opt.path != ROUTE_REMIX and remix.is_remix_game(g.install_dir):
        raise InstallError(
            "This game has an RTX Remix mod installed (its .trex runtime is "
            "in the folder).\n\nOnly the remix route works here: it puts DLSS 5 "
            "inside the Remix runtime. Every other route installs ReShade, "
            "which crashes a Remix game before it draws a frame - and on "
            "DirectX 9 it would write over the Remix runtime itself.\n\n"
            "Choose the remix route, or uninstall the Remix mod first.")
    preflight(g)

    log = on_log or (lambda *_: None)
    step = on_step or (lambda *_: None)
    prog = on_prog or (lambda *_: None)

    root = g.install_dir
    rep = Report(game_root=g.folder)
    x64 = g.bitness == 64
    if opt.path == FEEDER and g.api == "OpenGL" and opt.provider in (3, 4):
        # LumeniteFX reads 0% motion under OpenGL (perseval-BLR, six GL
        # games); VORT's optical flow is what works there.
        opt = replace(opt, provider=2)
        log("      OpenGL game: motion vectors from VORT (LumeniteFX gives "
            "none on GL)")
    # Through DXVK the game is a Vulkan game from here on: no proxy DLL, the
    # Vulkan layer instead. DXVK itself goes in at step 0, below.
    dxvk_from = dxvk_api(g, opt)
    steps = plan(g, opt)          # counted before the switch: DXVK is a step
    g = via_dxvk(g, opt)
    proxy = _proxy_name(g.api, opt.reshade_proxy)
    host = root / HOST_DIR
    trex, flavour, swap = remix_state(g, opt) if opt.path == ROUTE_REMIX \
        else (None, "", False)
    if opt.path == ROUTE_REMIX:
        # Nothing of ours is a proxy DLL on this route, and d3d9.dll here
        # belongs to Remix - recording it as "our proxy" would make the
        # diagnosis and uninstall reach for the mod's own file.
        proxy = ""

    level, why_rel = reliability(g, opt.path,
                                 "" if opt.native_dlss else opt.upscaler,
                                 remix_swap=swap)
    rep.preinstalled = _previously_ours(root)
    previous = _previous_route(root)
    rep.checkpoint = lambda: _write_manifest(root, g, opt, rep, proxy, level, complete=False)
    if level != STABLE:
        rep.warnings.append(f"{level}: {why_rel}")

    # Two executables in one folder (Medieval II and its Kingdoms expansion,
    # a game and its launcher) share one install. Say so, or uninstalling
    # "the other one" looks like it broke this one.
    other = games._recorded_exe(root)
    if other and g.exe and other.lower() != g.exe.name.lower():
        rep.notes.append(f"this folder was already set up for {other}; both "
                         f"executables share these files, and uninstalling "
                         f"either removes them for both")
        log(f"      note: {other} in this folder uses the same files")

    # Unreal and CryEngine games run from a subfolder; the executable in the
    # root is a launcher stub. Everything goes beside the real one, and the
    # store still starts the game the normal way - say so, because "I put
    # the files in the game folder" is the classic mistake here.
    try:
        if root.resolve() != g.folder.resolve():
            rel_dir = root.relative_to(g.folder)
            log(f"      installing into {rel_dir} - the game runs from there "
                f"(the exe in the root is a launcher). Start it from the store "
                f"as usual.")
            rep.notes.append(f"files are in {rel_dir}, beside the executable "
                             f"the game actually runs; start it from the store "
                             f"as usual")
    except (OSError, ValueError):
        pass

    lw = launcher_warning(g)
    if lw:
        rep.warnings.append(lw)
        log(f"      !! {lw.split('.')[0]}")
    hw = hook_warning(root, opt.path)
    if hw:
        rep.warnings.append(hw)
        log(f"      !! {hw.split('.')[0]}")
    ac = anticheat.detect(root, g.folder)
    if ac.present:
        # Not refused: single-player-only users sometimes want this anyway,
        # and it is their machine. But it is stated plainly, kept in the
        # manifest, and repeated in the finished-install notes.
        rep.warnings.append(
            f"{ac.summary} detected ({', '.join(ac.evidence)}). ReShade "
            f"add-ons and anti-cheat do not coexist: expect the game not to "
            f"start, or nothing to happen, or a ban. Do not use this online.")
        log(f"      !! {ac.summary} detected - see the warning above")
    if opt.path != ROUTE_REMIX and reengine.detected(root):
        rep.warnings.append(reengine.message())
        log("      !! RE Engine game detected - ReShade's add-on support is "
            "documented to crash this engine; see the warning above")

    # Refuse an occupied proxy before changing the previous working route.
    existing = root / proxy if proxy else root
    move_hand_opti = (opt.path not in (OPTI, ROUTE_REMIX) and existing.is_file()
                      and not _is_reshade(existing) and optiscaler.is_optiscaler(existing))
    if opt.path not in (OPTI, ROUTE_REMIX) and existing.is_file() and not _is_reshade(existing) and not move_hand_opti:
        raise InstallError(f"{proxy} already exists but is not ReShade (DXVK, Special K or another injector?). Remove it first, then try again.")

    # Switching routes must not leave the previous one behind. The routes put
    # very different things in the folder - the feeder alone drops 28 files,
    # including a ReShade.ini that would sit next to OptiScaler and confuse
    # everything - and the new manifest would not list them, so a later
    # uninstall could never clean them up either.

    if opt.path == FEEDER and g.api == "DX10":
        # Only feeder 0.13.1+ reaches D3D10. Checked here, before a single
        # file is written: raised from inside the feeder step it left a
        # bare ReShade behind (review, 1.7.0).
        tag0, _ = sources.resolve_feeder(prerelease=opt.feeder_prerelease,
                                         tag=opt.feeder_tag)
        if sources.feeder_key(tag0) < sources.feeder_key(sources.FEEDER_DX10_MIN):
            raise InstallError(
                f"DLSS5-Feeder {tag0} refuses Direct3D 10 games. Pick "
                f"{sources.FEEDER_DX10_MIN} or newer in 'feeder build' - that is "
                f"the first build with the D3D10 relay - and install again.")

    if opt.path == OPTI:
        # The same rule for the RTX 40 MFG package: raised inside the
        # OptiScaler step it came after the previous route was taken out,
        # so a working install was lost to a card check (gate 2.0.5).
        why_card = optiscaler.card_refusal(opt.opti_build, gpu.detect()[1])
        if why_card:
            raise InstallError(why_card)
        # Frame generation files of the person's own: the slot they need is
        # checked here too, for the same reason.
        why_fg = _own_fg_refusal(root, opt)
        if why_fg:
            raise InstallError(why_fg)

    # The route taken out below, named when a failure rolls this one back.
    switched = previous if previous and previous != opt.path else ""
    if previous and previous != opt.path:
        log(f"[0] removing the previous {previous} install first")
        for line in uninstall(g, on_log=lambda s: None):
            pass
        if (root / MANIFEST).is_file():
            raise InstallError("The previous install could not be fully restored. Its recovery record was kept; the new route was not installed.")
        rep.written.clear()
        rep.hashes.clear()
        rep.preinstalled.clear()
        log(f"    the {previous} route was removed; installing {opt.path}")
        rep.notes.append(f"replaced a previous {previous} install")

    # All destructive cleanup follows validation and the previous route's recovery.
    if move_hand_opti and existing.is_file():
        for target in (existing, root / optiscaler.FORWARDER, root / optiscaler.INI):
            if target.is_file():
                _remove_for_install(target, rep, root)
        rep.notes.append(f"hand-installed OptiScaler under {proxy} was backed up and moved aside")
    if opt.path != OPTI:
        _clear_stale_reshade(root, "" if opt.path == ROUTE_REMIX else proxy, rep, log)

    # Belt and braces: whatever the manifest said, no add-on from another
    # route may be left in the folder. ReShade loads them all.
    _purge_foreign_addons(root, opt.path, rep, log)
    if opt.path not in (OPTI, ROUTE_REMIX):
        _sideline(root, rep, log)
    # An emulator on the wrong render backend never gets a DXGI swap chain,
    # and ReShade then attaches to nothing. Switch it for them, say so, and
    # let uninstall put the config back.
    if getattr(g, "emu", None) is not None and g.exe:
        try:
            for line in emulators.set_backend(g.emu, g.exe):
                rep.notes.append(line)
                log(f"      {line}")
        except Exception as e:      # never let a config quirk stop the install
            rep.warnings.append(f"could not set the emulator's render backend "
                                f"({e}); {g.emu.renderer_hint}")

    n = len(steps)
    i = 0
    done = False

    def begin(name: str) -> None:
        nonlocal i
        step(i, n, name)
        log(f"[{i + 1}/{n}] {name}")
        i += 1

    def dl(url: str, fname: str) -> Path:
        def p(done: int, total: int) -> None:
            pct = int(done * 100 / total) if total else 0
            prog(pct, f"{fname} - {net.human(done)}"
                      + (f" / {net.human(total)}" if total else ""))
        return net.download(url, fname, progress=p)

    # Every step below can fail (network, rate limit, permissions). If it
    # does, we still record the files already written - otherwise they would
    # be orphaned in the game folder with no way to clean them up.
    # The name OptiScaler went in under, once it is chosen: a failure part way
    # must record THAT, not the ReShade proxy name - update and retry read
    # the record's proxy back as opti_proxy and would put OptiScaler under a
    # name the first attempt had avoided because it was taken.
    oproxy = ""
    # Was there an install of ours here when the first file of this one went
    # in? The previous route has been taken out by now, so "no" is a fresh
    # install - and a fresh install that fails is taken back out whole
    # (_roll_back). #438: the ReShade download died after DXVK's d3d9.dll
    # was in, and AC2 then ran on DXVK with nothing of ours on top of it -
    # "glitches in shaders", in a game that had worked before the install.
    fresh = not rep.preinstalled
    try:
        # --- 0) REFramework first, on an RE Engine game (see reengine.py) ---
        # Never on the remix route: Remix has already replaced the renderer
        # by the time this runs, and RE Engine's own tamper checks do not
        # apply to it - plan() already leaves this route out for the same
        # reason.
        if opt.path != ROUTE_REMIX and reengine.detected(root):
            begin("REFramework (RE Engine - so ReShade survives)")
            for f in refw.install(root, log, writer=lambda src, dst: _copy(src, dst, rep, root)):
                rep.written.append(f)
            rep.notes.append(
                "REFramework installed: it loads before the game's own "
                "tamper checks and patches around them, so ReShade (below) "
                "does not get killed the way it would on its own.")

        # --- 0b) DXVK: the game renders on Vulkan, ReShade stays outside -----
        # DirectX 9 arrives here too, and never on the remix route: Remix IS
        # the D3D9 implementation there, so a d3d9.dll of ours would land
        # straight on top of the Remix bridge client. Caught on the real
        # GTA IV install; uses_dxvk() excludes that route for the same reason.
        if dxvk_from:
            begin(f"DXVK ({dxvk_from} -> Vulkan)")
            ver, files = dxvk.install(root, x64, log, api=dxvk_from,
                                      writer=lambda src, dst: _copy(src, dst, rep, root))
            rep.written += files
            rep.components["dxvk"] = ver
            rep.notes.append(f"DXVK {ver} installed ({dxvk_from} -> Vulkan): the "
                             f"game renders on Vulkan and ReShade loads as a "
                             f"Vulkan layer, so nothing hooks the game itself. "
                             f"Use a borderless window, not exclusive fullscreen.")

        # --- the RTX Remix route ---------------------------------------
        if opt.path == ROUTE_REMIX:
            if trex is None:
                raise InstallError(
                    "No RTX Remix runtime (a '.trex' folder) was found in "
                    "this game. This route is only for a game that already "
                    "has an RTX Remix mod installed.")
            if not flavour and not swap:
                raise InstallError(
                    "The RTX Remix runtime installed here has no DLSS 5 "
                    "neural pass - NVIDIA's own runtime has none, and only "
                    "some community forks do.\n\nTurn on 'swap the Remix "
                    "runtime' to replace it with a build that has the pass. "
                    "That is experimental: a mod's runtime is often a fork "
                    "carrying fixes for this exact game, and replacing it "
                    "can break them. The old one is backed up either way.")
            conf = remix.conf_path(root, trex)

            def _rel(p: Path) -> str:
                try:
                    return str(p.relative_to(root))
                except ValueError:
                    return str(p)

            rec = _remix_swap_record(g)
            if not swap and rec:
                rt0 = trex / remix.RUNTIME_DLL
                try:
                    key0 = str(rt0.relative_to(root)).replace("\\", "/")
                except ValueError:
                    key0 = str(rt0).replace("\\", "/")
                if _remix_runtime_replaced(g, trex):
                    # The mod updated its own runtime, with the pass, since
                    # our swap: it is the mod's again, and so is whatever it
                    # brought beside it. Not ours to delete on uninstall.
                    # The backup of the older runtime would only put that
                    # one back - moved aside under a name uninstall does not
                    # restore, rather than deleted, in case this is wrong.
                    for name in sources.REMIX_RUNTIME_ASSETS:
                        p = trex / name
                        try:
                            k = str(p.relative_to(root)).replace("\\", "/")
                        except ValueError:
                            k = str(p).replace("\\", "/")
                        rep.preinstalled.discard(k)
                    stale = rt0.with_name(rt0.name + BACKUP_SUFFIX)
                    aside = stale.with_name(rt0.name + SUPERSEDED_SUFFIX)
                    if stale.is_file():
                        try:
                            _safe_target(root, stale, rep.game_root)
                            _safe_target(root, aside, rep.game_root)
                            if aside.exists():
                                aside = _displace(stale)
                            else:
                                _atomic_copy(stale, aside)
                            stale.unlink()
                            rep.notes.append(
                                f"{_rel(aside)} is the runtime this mod had "
                                f"before it updated - delete it if you do not "
                                f"need it")
                        except OSError as error:
                            raise InstallError(f"Could not preserve the superseded Remix original ({error}); it was kept.") from error
                    log("      the mod has its own DLSS 5 runtime now - "
                        "left as it is")
                else:
                    # Still the runtime we swapped in: the record keeps
                    # saying so, or the next update would not renew it.
                    rep.components["remix_runtime"] = rec["remix_runtime"]
                    if rec.get("remix_runtime_stamp"):
                        rep.components["remix_runtime_stamp"] = rec["remix_runtime_stamp"]

            if swap:
                begin("RTX Remix runtime (DLSS 5 build)")
                rtag, rurls = sources.resolve_remix_runtime()
                rt = trex / remix.RUNTIME_DLL
                if _remix_runtime_replaced(g, trex) and rt.is_file():
                    # The mod put its own runtime there after our swap. That
                    # one is now the game's own: it replaces the backup of
                    # the older one - written beside first and then moved
                    # over it, so a full drive never leaves neither. Only the
                    # runtime itself: a mod whose own runtime has no pass
                    # ships no remix_nvngx.dll, so ours stays ours here.
                    old_bak = rt.with_name(rt.name + BACKUP_SUFFIX)
                    try:
                        _safe_target(root, rt, rep.game_root)
                        _safe_target(root, old_bak, rep.game_root)
                        if old_bak.exists():
                            _displace(old_bak)
                        rep.hashes[_rel(old_bak)] = net.sha256(rt)
                        rep.written.append(_rel(old_bak))
                        _checkpoint(rep)
                        _atomic_copy(rt, old_bak)
                    except OSError as e:
                        raise InstallError(
                            f"Could not back up the mod's own runtime before "
                            f"replacing it ({e}). Nothing was replaced.") from e
                    log("      the mod updated its own runtime since the last "
                        "swap - that one is kept as the backup")
                for name in sources.REMIX_RUNTIME_ASSETS:
                    f_ = dl(rurls[name], f"remix-runtime-{rtag}-{name}")
                    _copy(f_, trex / name, rep, root)
                    log(f"      {_rel(trex / name)}")
                log(f"      dxvk-remix-plus-dlssnr {rtag}")
                if rtag == "latest":
                    log("      (GitHub's API was out of reach; took the "
                        "newest release by its download redirect)")
                rep.components["remix_runtime"] = rtag
                stamp = _runtime_stamp(rt)
                if stamp:
                    rep.components["remix_runtime_stamp"] = stamp
                rep.notes.append(f"remix runtime version: {rtag}")
                rep.notes.append(
                    "the mod's own Remix runtime was replaced with a "
                    "community build that has the neural pass; the original "
                    "is backed up beside it and 'uninstall' puts it back. If "
                    "the mod misbehaves after this, that swap is the reason.")
                flavour = remix.runtime_flavour(trex) or remix.NEURAL

            begin(DLSSNR)
            card, sm = gpu.detect()
            if card:
                log(f"      graphics card: {card} ({gpu.label(sm)})")
            catalog = sources.rhi_catalog()
            if sources.last_fallback:
                log(f"      {sources.last_fallback}")
                if sources.last_fallback not in rep.warnings:
                    rep.warnings.append(sources.last_fallback)
            tried: list[str] = []
            chosen = None
            candidates = ([sources.pick(catalog["dlssnr"], opt.dlssnr)]
                          if opt.dlssnr
                          else gpu.order_dlssnr(catalog["dlssnr"], sm))
            for e in candidates:
                f_ = dl(e["url"], f"dlssnr-{e['label']}.zip")
                _extract(f_, DLSSNR, trex / DLSSNR, rep, root)
                compat, why_gpu = gpu.check(trex / DLSSNR, sm)
                if compat is False and not opt.ignore_gpu_mismatch:
                    if opt.dlssnr:
                        raise InstallError(
                            f"Build {e['label']} will not run on "
                            f"{card or 'your card'}.\n\n{why_gpu}")
                    tried.append(e["label"])
                    log(f"      skipped {e['label']} - {why_gpu}")
                    continue
                chosen = (e, compat, why_gpu)
                break
            if chosen is None:
                raise InstallError(
                    f"No suitable nvngx_dlssnr build found for "
                    f"{card or 'your card'}.\n\nTried: {', '.join(tried)}")
            e, compat, why_gpu = chosen
            rep.written.append(_rel(trex / DLSSNR))
            log(f"      {_rel(trex / DLSSNR)}  (nvngx_dlssnr {e['label']})")
            log(f"      GPU check: {why_gpu}")
            rep.notes.append(f"dlssnr version: {e['label']}")
            rep.components["dlssnr"] = e["label"]
            tier = gpu.tier_note(sm, e["label"])
            if tier:
                log(f"      {tier}")
                rep.notes.append(tier)
            if compat is False:
                rep.warnings.append(f"dlssnr {e['label']} does not match your "
                                    f"card - installed anyway")

            begin(remix.CONF)
            key = remix.enable_key(flavour)
            # Whether it ended with a newline decides what uninstall has to
            # put back: set_option adds one when it is missing.
            had_nl = remix.ends_with_newline(conf)
            rep.remix = {"conf": _rel(conf), "key": key,
                         "trex": _rel(trex), "flavour": flavour,
                         "conf_final_newline": had_nl}
            _remix_option(conf, key, rep, root)
            log(f"      {_rel(conf)}: {key} = True")
            log("      (that one line; every other setting in rtx.conf is "
                "left exactly as it was)")
            rep.notes.append(
                f"{key} = True was set in {_rel(conf)}; 'uninstall' takes "
                f"that line back out and touches nothing else in the file")
            rep.notes.append(
                "In game: Alt+X opens the Remix menu -> Developer Settings "
                "Menu -> Post-Processing, where the neural pass can be "
                "toggled. It runs inside the Remix runtime, after DLSS, so "
                "the game's own DLSS/RR settings still apply.")
            rep.notes.append(
                "No ReShade, no feeder and no add-on go into a Remix game. A "
                "ReShade proxy DLL left in this folder crashes it before it "
                "draws a frame.")
            _verify_written(root, rep, log)
            clear_failure(root)     # this folder's last failure is history now
            _set_gpu_pref(root, g, opt, rep, log)
            _finish_record(_write_manifest(root, g, opt, rep, proxy, level, complete=True), rep, log)
            if not record_lost(rep):
                prefs.add_install(root)
            prog(100, "Done")
            return rep

        if opt.path == OPTI:
            begin("OptiScaler (DLSS-NR build)")
            # A game that ships its own dxgi.dll (an ENB, DXVK, its own
            # wrapper) gets a different proxy name rather than having that
            # file replaced, unless the user picked one explicitly.
            oproxy = _opti_proxy_for(root, opt)
            if oproxy != optiscaler.DEFAULT_PROXY and not opt.opti_proxy:
                log(f"      {optiscaler.DEFAULT_PROXY} is already taken here, "
                    f"installing as {oproxy} instead")
            # The RTX 40 MFG package on any other card was refused at the top
            # of install(), before the previous route came out.
            try:
                orel = optiscaler.resolve(opt.opti_build)
            except RuntimeError as e:
                # A sentence written to be read, not a crash: without this
                # it reaches the window as traceback.format_exc() and the
                # tool offers to file a bug report about its own refusal,
                # and the reason never reaches the manifest notes either.
                raise InstallError(str(e)) from e
            if opt.opti_build == optiscaler.FORK:
                log(f"      y4my4my4m's fork, {orel[0]}")
                rep.notes.append("OptiScaler is y4my4my4m's fork of the DLSS-NR "
                                 "build, with multi-frame generation on RTX 40 "
                                 "(OptiScaler.ini: [DLSSG] AdaMfgUnlock=true) and "
                                 "its own neural-pass changes. The rest is on the "
                                 "overlay. Development builds - if a "
                                 "game misbehaves, install again with the "
                                 "DLSS-NR build.")
            elif opt.opti_build == optiscaler.PRESR:
                log(f"      wilsjo2's fork, {orel[0]}")
                rep.notes.append("OptiScaler is wilsjo2's fork of the DLSS-NR "
                                 "build: the neural pass runs before super "
                                 "resolution rather than after it, over one to "
                                 "three passes (OptiScaler.ini: Passes=). Not "
                                 "run in a game here - if it misbehaves, "
                                 "install again with the DLSS-NR build.")
            elif opt.opti_build == optiscaler.JANBLADE:
                log(f"      Janblade's fork, {orel[0]}")
                rep.notes.append("OptiScaler is Janblade's fork of wilsjo2's "
                                 "build: the neural pass runs before super "
                                 "resolution rather than after it, over one to "
                                 "three passes (OptiScaler.ini: Passes=). Not "
                                 "run in a game here - if it misbehaves, "
                                 "install again with the DLSS-NR build.")
            elif opt.opti_build == optiscaler.PRESR_MFG:
                log(f"      wilsjo2's fork with RTX 40 MFG, {orel[0]}")
                rep.notes.append("OptiScaler is wilsjo2's RTX 40 MFG package: "
                                 "the neural pass runs before super resolution, "
                                 "over one to three passes (OptiScaler.ini: "
                                 "Passes=), and its RTX 40 unlock is switched "
                                 "on ([DLSSG] AdaMfgUnlock=true), so a game "
                                 "with its own DLSS frame generation can offer "
                                 "3x/4x on an RTX 40. Not run in a game here - "
                                 "if frame generation misbehaves, install again "
                                 "with \"wilsjo2's fork\" in 'optiscaler build'.")
            try:
                for f in optiscaler.install(root, proxy=oproxy, dl=dl, log=log,
                                            backup=lambda p: _prepare_write(p, rep, root),
                                            writer=lambda src, dst: _copy(src, dst, rep, root), release=orel):
                    rep.written.append(f)
            except RuntimeError as e:      # the archive carried no OptiScaler
                raise InstallError(str(e)) from e
            # After the files are down, not before: an install that is
            # refused (#364 - the release carried no OptiScaler package)
            # would otherwise leave a manifest naming a version this folder
            # never had, and the diagnosis reads that manifest. The other
            # components still record before their download, deliberately:
            # only this one has a refusal of its own that leaves the folder
            # untouched, and a manifest written complete=False already
            # outranks them all in the diagnosis.
            rep.components["optiscaler"] = orel[0]
            _, sm_ = gpu.detect()
            note = optiscaler.requirements_note(sm_)
            if note:
                rep.warnings.append(note)
                log(f"      !! {note}")

            begin("nvngx_dlssnr.dll")
            catalog_ = sources.rhi_catalog()
            e_ = sources.pick(gpu.order_dlssnr(catalog_["dlssnr"], sm_), opt.dlssnr)
            f_ = dl(e_["url"], f"dlssnr-{e_['label']}.zip")
            _extract(f_, DLSSNR, root / DLSSNR, rep, root)
            rep.written.append(DLSSNR)
            compat_, why_ = gpu.check(root / DLSSNR, sm_)
            log(f"      nvngx_dlssnr {e_['label']}")
            log(f"      GPU check: {why_}")
            rep.notes.append(f"dlssnr version: {e_['label']}")
            rep.components["dlssnr"] = e_["label"]
            tier_ = gpu.tier_note(sm_, e_["label"])
            if tier_:
                log(f"      {tier_}")
                rep.notes.append(tier_)
            if compat_ is False and not opt.ignore_gpu_mismatch:
                raise InstallError(
                    f"Build {e_['label']} will not run on your card.\n\n{why_}")

            if _opti_needs_dlss(opt):
                # The game has FSR/XeSS and no DLSS: OptiScaler will call
                # DLSS in their place, so the runtime has to be here. Same
                # pick as the ReShade routes - newest unless pinned - and a
                # copy someone put here by hand is kept, as everywhere else.
                begin("nvngx_dlss.dll")
                game_has = (root / DLSS).is_file() and DLSS not in rep.written \
                    and DLSS not in rep.preinstalled
                if game_has and opt.keep_game_dlss:
                    log("      a nvngx_dlss.dll is already here, left untouched")
                    rep.skipped.append(DLSS)
                else:
                    was_ = pe.file_version(root / DLSS)
                    e_ = _place_family(catalog_["dlss"], opt.dlss,
                                       root / DLSS, rep, root, dl, DLSS,
                                       "dlss", log)
                    log(f"      nvngx_dlss {_swapped(was_, e_['label'])} "
                        f"(the game has none: "
                        f"OptiScaler runs DLSS in place of its "
                        f"{'FSR' if opt.upscaler == 'fsr' else 'XeSS'})")
                    rep.notes.append(f"dlss version: {e_['label']}")
                    rep.components["dlss"] = e_["label"]
            else:
                nested_ = _opti_dlss_target(root, g, opt,
                                            ours=rep.preinstalled)
                if nested_ is not None:
                    begin("nvngx_dlss.dll")
                    _swap_nested_dlss(nested_, catalog_["dlss"], opt, rep,
                                      root, dl, log)

            begin("OptiScaler configuration")
            nr_settings = dict(opt.nr)
            if optiscaler.is_presr(opt.opti_build):
                # The build is offered for this placement; the placement is
                # a setting, and its default is off (#81).
                for k, v in optiscaler.PRESR_BEFORE_SR.items():
                    nr_settings.setdefault(k, v)
            _configure(root, rep, optiscaler.enable_nr, log, settings=nr_settings, names=(optiscaler.INI,))
            if opt.opti_build == optiscaler.PRESR_MFG:
                # The package ships its unlock switched off (#286).
                if not _configure(root, rep, optiscaler.enable_mfg_unlock, log, names=(optiscaler.INI,)):
                    # Silent until the 2.0.5 gate: the install then said
                    # nothing and the unlock was simply never there.
                    rep.warnings.append("the RTX 40 MFG unlock could not be switched on - "
                                        "OptiScaler.ini could not be written. Close the "
                                        "game and install again, or add AdaMfgUnlock=true "
                                        "under [DLSSG] in OptiScaler.ini by hand")
                # What the unlock needs from the game, said at install rather
                # than found out in it (gate 2.0.5): a DLSS frame-generation
                # runtime of the game's own.
                rep.warnings += _mfg_warnings(g, opt, root, written=rep.written)
            # A keyboard without an Insert key has no way into the overlay,
            # which is where neural rendering is switched on (#88).
            _configure(root, rep, optiscaler.set_overlay_key, _overlay_key_pref(), log, names=(optiscaler.INI,))
            for line in optiscaler.describe_nr(nr_settings):
                rep.notes.append(line)
            if opt.fg and g.api == "DX12":
                if _configure(root, rep, optiscaler.enable_fg, log, names=(optiscaler.INI,)):
                    if opt.opti_build == optiscaler.PRESR_MFG:
                        # Only once FSR frame generation is really on: with
                        # the libraries missing it is not, and the warning
                        # blamed a switch that had done nothing (gate 2.0.5).
                        # FGOutput=fsrfg leaves the unlock nothing to act on,
                        # and the note below would tell the same person to
                        # turn the game's own frame generation off - the one
                        # the unlock needs.
                        rep.warnings.append(MFG_FSR_FG)
                        rep.notes.append("frame generation: FSR 3.1 through "
                                         "OptiScaler, one generated frame per "
                                         "rendered one - in place of the MFG "
                                         "unlock, see the warning")
                    else:
                        rep.notes.append("frame generation: FSR 3.1 through "
                                         "OptiScaler, one generated frame per "
                                         "rendered one, on any RTX card. Turn the "
                                         "game's own frame generation OFF; expect "
                                         "added latency and check the HUD")
                    rep.components["fg"] = "fsr31"
            elif opt.fg:
                log("      frame generation needs a D3D12 game - not on this one")
                rep.warnings.append("frame generation was requested but the "
                                    "game is not D3D12; not enabled")
            if _opti_needs_dlss(opt):
                _configure(root, rep, optiscaler.enable_inputs, opt.upscaler, g.api, log, names=(optiscaler.INI,))
                rep.notes.append(
                    f"no DLSS in this game: OptiScaler hooks its "
                    f"{'FSR 2/3' if opt.upscaler == 'fsr' else 'XeSS'} calls "
                    f"and runs DLSS in their place, then neural rendering. "
                    f"Pick the upscaler you would normally pick in the game's "
                    f"own menu; if nothing changes in game, the game probably "
                    f"links its upscaler statically - use the feeder route.")
            if g.api == "DX11":
                # The model refuses to run on a D3D11 device. OptiScaler gets
                # around it by running the upscaler on D3D12 underneath -
                # which means DLSS cannot be the upscaler here, FSR is.
                _configure(root, rep, optiscaler.set_dx11_bridged_upscaler, log, names=(optiscaler.INI,))
                rep.notes.append("D3D11 game: OptiScaler's upscaler set to FSR "
                                 "2.2 on D3D12 (the model does not run on "
                                 "D3D11 directly; DLSS cannot be the upscaler "
                                 "on this route)")
            _place_own_fg(root, opt, rep, log, begin)
            rep.notes.append(
                f"OptiScaler is installed INSTEAD of ReShade. Press "
                f"{reshade_ini.overlay_key_name(optiscaler.OVERLAY_KEY)} "
                f"in game to open its overlay, then "
                f"turn on Neural Rendering - it is off by default. If it "
                f"refuses, the overlay says why under the checkbox.")
            rep.notes.append(f"OptiScaler proxy: {oproxy}")
            # Record the name OptiScaler actually went in under, not the
            # ReShade proxy this route never installs.
            _verify_written(root, rep, log)
            _set_gpu_pref(root, g, opt, rep, log)
            _finish_record(_write_manifest(root, g, opt, rep, oproxy, level, complete=True), rep, log)
            if not record_lost(rep):
                prefs.add_install(root)
            prog(100, "Done")
            return rep

        # --- 1) ReShade -------------------------------------------------------
        begin("ReShade")
        ver, url = sources.resolve_reshade()

        setup = dl(url, f"ReShade_Setup_{ver}_Addon.exe")
        log(f"      ReShade {ver}")
        rep.components["reshade"] = ver
        if opt.vr and not x64:
            log("      VR: the OpenXR layer is 64-bit only - skipped for this "
                "32-bit game")
        elif opt.vr:
            from . import openxr
            rep.layer_pending = True
            _checkpoint(rep)
            with prefs.mutation_lock():
                prefs.add_openxr_game(root)
                xr_manifest, xr_fresh = openxr.install_layer(setup, log)
            if xr_fresh:
                rep.notes.append("registered ReShade as an OpenXR layer for this "
                                 "user, so the pass reaches the headset's image; "
                                 "it loads into EVERY OpenXR application until "
                                 "'uninstall' removes it")
            else:
                rep.notes.append(f"reused the existing ReShade OpenXR layer "
                                 f"({xr_manifest})")
            rep.warnings.append("VR through OpenXR has not been tried with a "
                                "headset by the author, and only games that "
                                "run on OpenXR are reached (OpenVR/SteamVR "
                                "titles are not): if the headset shows nothing "
                                "new, or the game refuses to start, untick "
                                "'VR headset' and install again - and say what "
                                "happened in a report")
        # The installer exe has a zip appended: both ReShade32.dll and ReShade64.dll.
        if g.api == "Vulkan":
            # A Vulkan game never loads dxgi.dll. ReShade reaches it as an
            # implicit Vulkan layer instead - a registry value the loader reads.
            # Its own name: "fresh" is the rollback's (is this folder new to
            # us?), and install_layer's True on every reinstall made a
            # failed "update all" take a working install away (gate 2.0.6).
            rep.layer_pending = True
            _checkpoint(rep)
            with prefs.mutation_lock():
                prefs.add_vulkan_game(root)
                manifest, layer_new = vulkan.install_layer(setup, log, also32=not x64)
            if layer_new:
                rep.notes.append("registered ReShade as a Vulkan layer for this "
                                 "user - it now loads into EVERY Vulkan "
                                 "application, not just this game")
                rep.warnings.append("the Vulkan layer is global; 'uninstall' "
                                    "removes it again")
            else:
                rep.notes.append(f"reused the existing ReShade Vulkan layer "
                                 f"({manifest})")
        else:
            _extract(setup, "ReShade64.dll" if x64 else "ReShade32.dll",
                     root / proxy, rep, root)
            rep.written.append(proxy)
            log(f"      {proxy} <- ReShade{'64' if x64 else '32'}.dll")
        if not x64 and opt.path == FEEDER:
            _extract(setup, "ReShade64.dll", host / "dxgi.dll", rep, root)
            rep.written.append(f"{HOST_DIR}/dxgi.dll")
            log(f"      {HOST_DIR}/dxgi.dll <- ReShade64.dll (for the helper process)")

        # --- 2) the path-specific middle -------------------------------------
        if opt.path == BRIDGE:
            begin("dlss5-bridge")
            btag, burl = sources.resolve_bridge()
            bf = dl(burl, f"dlss5-bridge-{btag}.addon64")
            _copy(bf, root / BRIDGE_ADDON, rep, root)
            log(f"      dlss5-bridge {btag}")
            rep.notes.append(f"bridge version: {btag}")
            rep.components["bridge"] = btag
            # An older 1.0.x build under its previous name would be loaded too
            # and fight with this one; ReShade loads every add-on it finds.
            legacy = root / LEGACY_BRIDGE_ADDON
            if legacy.is_file():
                try:
                    _remove_for_install(legacy, rep, root)
                    log("      removed the older dlss5-dx11-bridge.addon64 "
                        "(both loading at once conflict)")
                    rep.notes.append("removed a legacy dlss5-dx11-bridge.addon64")
                except OSError:
                    rep.warnings.append("could not remove the older "
                                        "dlss5-dx11-bridge.addon64 - delete it "
                                        "by hand, it conflicts")

        elif (root / LEGACY_BRIDGE_ADDON).is_file():
            # ReShade loads every add-on in the folder, so an older bridge
            # left from another route hooks the same device as this one's
            # (#439: DX11 Bridge 1.0.27 beside the feed, nothing ran). Kept
            # aside, not deleted: uninstall puts it back.
            try:
                _remove_for_install(root / LEGACY_BRIDGE_ADDON, rep, root)
                log(f"      moved the older {LEGACY_BRIDGE_ADDON} aside "
                    f"(it would load beside this route's add-on)")
                rep.notes.append(f"moved an older {LEGACY_BRIDGE_ADDON} aside")
            except OSError:
                rep.warnings.append(f"could not move the older {LEGACY_BRIDGE_ADDON} "
                                    f"aside - delete it by hand, it conflicts")

        if opt.path == FEEDER:
            _install_feeder_parts(g, opt, root, host, x64, rep, begin, dl, log)

        # --- 5/6/7) DLSS parts ------------------------------------------------
        # On the 32-bit path these live in host64/, otherwise next to the game.
        dlss_dir = root if (x64 or opt.path != FEEDER) else host
        catalog = sources.rhi_catalog()
        if sources.last_fallback:
            log(f"      {sources.last_fallback}")
            if sources.last_fallback not in rep.warnings:
                rep.warnings.append(sources.last_fallback)

        if opt.path == UPSTREAM:
            begin("neural-upstream")
            utag, uurl = sources.resolve_upstream()
            uf = dl(uurl, f"neural-upstream-{utag}.addon64")
            _copy(uf, dlss_dir / UPSTREAM_ADDON, rep, root)
            log(f"      neural-upstream {utag} -> {UPSTREAM_ADDON}")
            if utag == "latest":
                log("      (GitHub's API was out of reach; took the newest "
                    "release by its download redirect)")
            rep.notes.append(f"upstream version: {utag}")
            rep.components["upstream"] = utag
            rep.notes.append("neural-upstream runs the network itself, before "
                             "the game's DLSS: no renodx-dlss5 add-on on this "
                             "route, and the game's nvngx_dlss.dll is left alone")
        elif opt.path == STANDALONE:
            # VORT and the companion shader include ReShade.fxh, so the
            # headers go in exactly as on the feeder route.
            begin("ReShade shader headers")
            for h in sources.RESHADE_HEADERS:
                dest = root / SHADERS / h
                dest.parent.mkdir(parents=True, exist_ok=True)
                _backup(dest, rep, root)
                _write_bytes(net.fetch_text(sources.RESHADE_HEADERS_BASE + h), dest, rep, root)
                rep.written.append(str(Path(SHADERS) / h))
            log(f"      {', '.join(sources.RESHADE_HEADERS)}")

            begin("standalone-dlssnr")
            stag, surls = sources.resolve_standalone()
            if sources.STANDALONE_ZIP in surls:
                # 2.1.0 and later: one 64-bit archive laid out like a game folder.
                zf = dl(surls[sources.STANDALONE_ZIP], f"standalone-{stag}-64-bit.zip")
                for name in sources.STANDALONE_ASSETS + sources.STANDALONE_ZIP_EXTRA:
                    dest = (root / SHADERS / name) if name.endswith(".fx") else root / name
                    try:
                        _extract(zf, name, dest, rep, root)
                    except RuntimeError:        # net.extract_one: not in the archive
                        if name in sources.STANDALONE_ASSETS:
                            raise RuntimeError(f"The DLSS5-Reshade-AIO archive has no {name}.")
                        continue
                    rep.written.append(str(dest.relative_to(root)))
                    log(f"      {dest.relative_to(root)}")
            else:
                for name in sources.STANDALONE_ASSETS:
                    f = dl(surls[name], f"standalone-{stag}-{name}")
                    dest = (root / SHADERS / name) if name.endswith(".fx") else root / name
                    _copy(f, dest, rep, root)
                    log(f"      {dest.relative_to(root)}")
            log(f"      standalone-dlssnr {stag}")
            if stag == "latest":
                log("      (GitHub's API was out of reach; took the newest "
                    "release by its download redirect)")
            rep.notes.append(f"standalone version: {stag}")
            rep.components["standalone"] = stag
            rep.notes.append("standalone-dlssnr runs its own feed and the network "
                             "itself: no renodx add-on on this route. The "
                             "nvngx.dll beside it is the add-on's caller bridge, "
                             "not a driver file - uninstall removes it")

            _install_vort(root, rep, dl, log, begin)
        else:
            sf = opt.path == ROUTE_RENODX
            addon_name = RENODX_SF if sf else RENODX
            begin("DLSS 5 add-on (renodx-dlss SF)" if sf else "DLSS 5 add-on (renodx)")
            # Even without an explicit choice, prefer a local build if one exists:
            # Discord releases are not on the mirror. Only a build of the right
            # family, though - the two add-ons are not interchangeable.
            if not opt.renodx_local and not opt.renodx:
                found, _ = prefs.find_renodx(sf=sf)
                if found:
                    opt.renodx_local = found
                    log(f"      found a local renodx build: {found.name}")
            if opt.renodx_local:
                src = Path(opt.renodx_local)
                if not src.is_file():
                    raise InstallError(f"Selected renodx file not found: {src}")
                try:
                    if pe.exe_bitness(src) != 64:
                        raise InstallError("The selected renodx file is not 64-bit.")
                except pe.PEError as e:
                    raise InstallError(f"The selected renodx file is not valid: {e}") from e
                _copy(src, dlss_dir / addon_name, rep, root)
                log(f"      {src.name} (your local file) -> {addon_name}")
                rep.notes.append(f"renodx: local file used ({src.name})")
            elif sf:
                fam = catalog.get("renodx_sf") or []
                if not fam:
                    raise InstallError("The mirror lists no renodx-dlss (SF) build. "
                                       "Pick 'use my file' with the add-on from the "
                                       "RenoDX Discord, or choose another route.")
                e = sources.pick(fam, opt.renodx)
                f = dl(e["url"], f"renodx-sf-{e['label']}.zip")
                _extract(f, ".addon64", dlss_dir / RENODX_SF, rep, root)
                rep.written.append(str((dlss_dir / RENODX_SF).relative_to(root)))
                log(f"      renodx-dlss SF {e['label']}")
                rep.notes.append(f"renodx-dlss SF version: {e['label']}")
                rep.components["renodx_sf"] = e["label"]
            else:
                want = opt.renodx
                if not want and gpu.driver_at_least(sources.DRIVER_FAULT_MIN):
                    # 616.64+: 4.6/4.7 fault on every evaluate (sources.py has
                    # the measurement). 4.55 is the classic engine that still
                    # runs there - and it also satisfies the OpenGL and stable-
                    # feeder pins below, so it wins outright.
                    want = sources.DRIVER_FAULT_RENODX_PIN
                    log(f"      driver {gpu.driver_version()}: renodx-dlss5 pinned to "
                        f"{want} - 4.6/4.7 fault inside the NGX runtime on 616.64 "
                        f"and newer (every evaluate, no neural frame)")
                    rep.notes.append(f"renodx-dlss5 pinned to {want}: on driver "
                                     f"616.64+ the 4.6/4.7 builds fault in the "
                                     f"driver's NGX runtime on every evaluate")
                if not want and g.api == "OpenGL":
                    # 4.70's fenced workset pool never recycles under GL and
                    # the pass stalls after four frames; 4.60 is the last
                    # build that runs there (verified on six GL games by
                    # perseval-BLR/dlss5-classic-games).
                    want = sources.OPENGL_RENODX_PIN
                    log(f"      OpenGL game: renodx-dlss5 pinned to {want} "
                        f"(4.70 stalls on GL after a few frames)")
                    rep.notes.append(f"renodx-dlss5 pinned to {want}: newer "
                                     f"builds stall on OpenGL")
                if not want and opt.path == FEEDER:
                    # Feeder builds below 0.8.0-beta.3 accept only 4.55;
                    # anything newer overlaps them and the DLSS feature dies
                    # in CreateFeature. Above that, nothing is pinned here.
                    want = sources.renodx_for_feeder(rep.components.get("feeder", ""))
                    if want:
                        log(f"      DLSS5-Feeder {rep.components.get('feeder')} accepts "
                            f"renodx-dlss5 up to {want} - pinning to it (newer builds "
                            f"conflict; pick 'newest pre-release' under 'feeder build' "
                            f"to use them)")
                        rep.notes.append(f"renodx-dlss5 pinned to {want} for this "
                                         f"feeder release - newer builds conflict "
                                         f"with it")
                e = sources.pick(catalog["renodx"], want)
                # pick() falls back to the newest build when the wanted one
                # is not on the list, and every pin above exists because the
                # newest is the build that breaks. Silence there would read
                # as "pinned to 4.55" in the log and install 5.2.1, so the
                # miss is said out loud and carried into the report.
                if want and e["label"] != want:
                    miss = (f"renodx-dlss5 {want} is not on the build "
                            f"list - installing {e['label']} instead, which "
                            f"is the kind of build that pin exists to avoid. "
                            f"If the neural pass faults, pick {want} under "
                            f"'dlss5 add-on' in the game's settings.")
                    log(f"      {miss}")
                    rep.warnings.append(miss)
                f = dl(e["url"], f"renodx-{e['label']}.zip")
                _extract(f, ".addon64", dlss_dir / RENODX, rep, root)
                rep.written.append(str((dlss_dir / RENODX).relative_to(root)))
                log(f"      renodx-dlss5 {e['label']}")
                rep.notes.append(f"renodx version: {e['label']}")
                rep.components["renodx"] = e["label"]

        begin("nvngx_dlssnr.dll")
        card, sm = gpu.detect()
        if card:
            log(f"      graphics card: {card} ({gpu.label(sm)})")
        else:
            log("      no NVIDIA card detected")

        # Some builds of the leaked library are compiled for one architecture only
        # (310.8.0 is RTX 50 only, for instance). When the user has not pinned a
        # version we find the newest build that actually supports this card:
        # download, inspect, and move down the list if it does not match.
        tried: list[str] = []
        chosen = None
        candidates = ([sources.pick(catalog["dlssnr"], opt.dlssnr)] if opt.dlssnr
                      else gpu.order_dlssnr(catalog["dlssnr"], sm))
        for e in candidates:
            f = dl(e["url"], f"dlssnr-{e['label']}.zip")
            _extract(f, DLSSNR, dlss_dir / DLSSNR, rep, root)
            compat, why_gpu = gpu.check(dlss_dir / DLSSNR, sm)
            if compat is False and not opt.ignore_gpu_mismatch:
                if opt.dlssnr:
                    raise InstallError(
                        f"Build {e['label']} will not run on {card or 'your card'}.\n\n"
                        f"{why_gpu}\n\nLeave the version on Auto and the tool picks "
                        f"the newest build that supports your card.")
                tried.append(e["label"])
                log(f"      skipped {e['label']} - {why_gpu}")
                continue
            chosen = (e, compat, why_gpu)
            break

        if chosen is None:
            raise InstallError(
                f"No suitable nvngx_dlssnr build found for {card or 'your card'}.\n\n"
                f"Tried: {', '.join(tried)}\n\n"
                f"DLSS 5 currently runs on NVIDIA RTX 20 series and newer.")

        e, compat, why_gpu = chosen
        rep.written.append(str((dlss_dir / DLSSNR).relative_to(root)))
        log(f"      nvngx_dlssnr {e['label']}")
        rep.notes.append(f"dlssnr version: {e['label']}")
        rep.components["dlssnr"] = e["label"]
        if tried:
            rep.notes.append(f"skipped as incompatible: {', '.join(tried)}")
        tier = gpu.tier_note(sm, e["label"])
        if tier:
            log(f"      {tier}")
            rep.notes.append(tier)
        if compat is True:
            log(f"      GPU check: {why_gpu}")
        elif compat is False:
            log(f"      GPU check: {why_gpu}")
            rep.warnings.append(f"dlssnr {e['label']} does not match your card - installed anyway")
        else:
            rep.warnings.append(f"could not verify GPU compatibility ({why_gpu})")

        if opt.path == UPSTREAM:
            rep.skipped.append(DLSS)
        else:
            begin("nvngx_dlss.dll")
            game_has = (root / DLSS).is_file() and str(Path(DLSS)) not in rep.written
            if x64 and game_has and opt.keep_game_dlss:
                log("      the game ships its own nvngx_dlss.dll, left untouched")
                rep.skipped.append(DLSS)
            else:
                # Looked for before the copy beside the exe is written, which
                # would otherwise read as the game's own being right there.
                nested = _nested_game_dlss(root, g, opt, x64,
                                           ours=rep.preinstalled)
                was = pe.file_version(dlss_dir / DLSS)
                e = _place_family(catalog["dlss"], opt.dlss,
                                  dlss_dir / DLSS, rep, root, dl, DLSS,
                                  "dlss", log)
                log(f"      nvngx_dlss {_swapped(was, e['label'])}")
                rep.notes.append(f"dlss version: {e['label']}")
                rep.components["dlss"] = e["label"]
                # The copy beside the exe is not the one an Unreal game
                # loads: its own under Plugins is swapped as well (#225).
                if nested is not None and not _same_path(nested, dlss_dir / DLSS):
                    _swap_nested_dlss(nested, catalog["dlss"], opt, rep, root,
                                      dl, log)

        # Ray reconstruction. A swap, never an addition: the game asks for
        # this feature or it does not, and a runtime nothing calls is dead
        # weight in the folder. NVIDIA publishes it, so the person can move
        # a game off an old build the way they already can with DLSS itself.
        if opt.dlssd:
            begin(DLSSD)
            # Its own name: `e` above still holds the nvngx_dlss entry, and
            # reusing it here would make a skipped swap look like a done one.
            rr_entry = None
            have = _find_runtime(root, DLSSD, g.folder)
            fam = catalog.get("dlssd") or []
            if have is None:
                log("      this game does not ship nvngx_dlssd.dll - ray "
                    "reconstruction is not something it asks for, so nothing "
                    "was written")
                rep.skipped.append(DLSSD)
            elif not fam:
                log("      no nvngx_dlssd build could be listed")
                rep.skipped.append(DLSSD)
            else:
                # The publisher is the only source for this one - the mirror
                # publishes no dlssd builds - so a download that does not
                # arrive has nothing behind it. The game runs perfectly well
                # on the runtime it shipped, and everything else in this
                # install is already done: skip the swap, say so, and carry
                # on rather than ending the install over an extra.
                try:
                    rr_was = pe.file_version(have)
                    rr_entry = _place_family(fam, opt.dlssd, have, rep, root,
                                             dl, DLSSD, "dlssd", log)
                except PermissionError:
                    raise      # the game is running: that answer is better
                except (sources.RateLimited, sources.Unavailable):
                    raise      # a server outage has words of its own
                except Exception as ex:
                    log(f"      nvngx_dlssd could not be fetched ({ex}) - "
                        f"the game keeps the one it shipped")
                    rep.warnings.append(
                        "ray reconstruction was not swapped: the download did "
                        "not arrive. The game keeps the runtime it shipped, "
                        "and everything else installed normally.")
                    rep.skipped.append(DLSSD)
                    rr_entry = None
            if rr_entry is not None:
                try:
                    where = have.relative_to(root)
                except ValueError:
                    where = have
                log(f"      nvngx_dlssd {_swapped(rr_was, rr_entry['label'])}"
                    f"  ({where})")
                rep.notes.append(f"ray reconstruction: {rr_entry['label']} "
                                 f"(the game's own is backed up and comes "
                                 f"back on uninstall)")
                rep.notes.append("a launcher that verifies its files will put "
                                 "its own nvngx_dlssd.dll back, and an online "
                                 "game's anti-cheat can treat a changed file "
                                 "as tampering - this is a single-player "
                                 "swap")
                rep.components["dlssd"] = rr_entry["label"]

        if opt.path == STANDALONE:
            # Frame generation is optional to the add-on: with no
            # nvngx_dlssg.dll it says so in its log and runs NR + DLAA/SR.
            begin("nvngx_dlssg.dll")
            fam = catalog.get("dlssg") or []
            game_has_g = (root / DLSSG).is_file() and DLSSG not in rep.written
            if game_has_g and opt.keep_game_dlss:
                log("      a nvngx_dlssg.dll is already here, left untouched")
                rep.skipped.append(DLSSG)
            elif not fam:
                log("      no nvngx_dlssg build could be listed - frame "
                    "generation stays off")
                rep.notes.append("frame generation needs nvngx_dlssg.dll, not "
                                 "fetched (no source listed one); neural "
                                 "rendering and DLAA/DLSS SR still run")
                rep.skipped.append(DLSSG)
            else:
                g_was = pe.file_version(root / DLSSG)
                e = _place_family(fam, None, root / DLSSG, rep, root, dl,
                                  DLSSG, "dlssg", log)
                log(f"      nvngx_dlssg {_swapped(g_was, e['label'])} "
                    f"(frame generation)")
                rep.notes.append(f"dlssg version: {e['label']}")
                rep.components["dlssg"] = e["label"]
                if sm is not None and sm < 89:
                    fg = ("frame generation needs an RTX 40 or 50 card; on "
                          "this one the add-on falls back to real frames")
                    log(f"      {fg}")
                    rep.notes.append(fg)

        # --- 8) host64 --------------------------------------------------------
        if not x64 and opt.path == FEEDER:
            begin("host64 helper process")
            _configure(host, rep, reshade_ini.write_addon_only_ini, record_root=root)
            rep.written.append(f"{HOST_DIR}/ReShade.ini")
            log(f"      {HOST_DIR}/ ready (ReShade + DLSS parts inside)")

        # --- 8b) RTX 40 multi-frame generation (opt-in - see mfg.py) --------
        if opt.mfg:
            ok_mfg, why_mfg = mfg.applies(gpu.detect()[1], g.api, root, g.folder)
            if ok_mfg:
                begin("RTX 40 multi-frame generation")
                taken = {refw.DINPUT8} if reengine.detected(root) else set()
                try:
                    mtag, mfiles = mfg.install(root, g.exe, log, taken=taken,
                                               preinstalled=rep.preinstalled,
                                               writer=lambda src, dst: _copy(src, dst, rep, root))
                # An opt-in extra: whatever stops it - a project that changed
                # shape (#141), GitHub's rate limit, a proxy page - is a
                # warning, not the end of an install that is otherwise done.
                # mfg.install checks both archives before it writes a file.
                except (mfg.NoLoaderName, mfg.ShapeChanged, sources.RateLimited,
                        sources.Unavailable, net.WrongContent) as e:
                    log(f"      multi-frame generation skipped: {e}")
                    rep.warnings.append(f"multi-frame generation not enabled: {e}")
                    mtag, mfiles = "", []
            else:
                mtag, mfiles = "", []
            if mfiles:
                rep.written += mfiles
                rep.components["mfg"] = mtag
                rep.notes.append(
                    f"RTX40MFG-Unlock {mtag}: multi-frame generation on this "
                    f"RTX 40 - pick the multiplier in ReShade's DLSS MFG tab "
                    f"(Follow game / fixed / Dynamic). The game's own DLSS "
                    f"Frame Generation must be ON; the unlock raises its "
                    f"multiplier, it does not add frame generation")
                rep.warnings.append(
                    "multi-frame generation on RTX 40 is research software: "
                    "artifacts, a frozen picture or a crash are possible at "
                    "the higher multipliers, and on Vulkan")
            elif not ok_mfg:
                log(f"      multi-frame generation skipped: {why_mfg}")
                rep.warnings.append(f"multi-frame generation not enabled: {why_mfg}")
        else:
            # The box is off: an unlock an earlier install of ours placed
            # here comes out, or it would keep hooking Streamline while the
            # new manifest says the option is off.
            restored = mfg.remove_leftovers(root, rep.preinstalled, log,
                                            hashes=(_previous_manifest(root) or {}).get("hashes", {}))
            for gone in restored:
                _forget_restored(gone, rep)
            if restored:
                _checkpoint(rep)

        # --- 9) ReShade configuration ----------------------------------------
        begin("ReShade configuration")
        if opt.path == FEEDER:
            _backup(root / "ReShade.ini", rep, root)
            _backup(root / "ReShadePreset.ini", rep, root)
            _configure(root, rep, reshade_ini.write_reshade_ini, opt.provider)
            _configure(root, rep, _ask_for_the_pass, opt, log)
            _configure(root, rep, reshade_ini.write_preset, opt.provider)
            src = _configure(root, rep, reshade_ini.carry_over, [Path(x) for x in prefs.installs()])
            if src is not None:
                log(f"      your ReShade keys and overlay settings carried over "
                    f"from {src.parent.name}")
                rep.notes.append(f"ReShade key bindings and overlay settings "
                                 f"carried over from {src.parent.name}")
            rep.written += ["ReShade.ini", "ReShadePreset.ini"]
            label, tech, _ = reshade_ini.PROVIDERS[opt.provider]
            log(f"      DLSS5_MV_PROVIDER={opt.provider} ({label})")
            if tech:
                log(f"      technique order: {tech} -> {reshade_ini.FEED_TECHNIQUE}")
            else:
                rep.notes.append("You must install your chosen provider's shader "
                                 "yourself, and place its technique ABOVE DLSS 5 "
                                 "Feed in ReShade.")
        else:
            # Native and bridge hook the game's real NGX calls, so there is no
            # effect to compile and no technique order to get right. ReShade
            # only has to load the add-ons sitting next to the executable.
            _backup(root / "ReShade.ini", rep, root)
            _configure(root, rep, reshade_ini.write_addon_only_ini)
            _configure(root, rep, _ask_for_the_pass, opt, log)
            if opt.path == ROUTE_RENODX:
                _configure(root, rep, reshade_ini.enable_renodx_dlss_nr)
                log("      [RENODX-DLSS] NeuralRenderingEnabled=1")
            if opt.path == UPSTREAM:
                rep.notes.append("neural-upstream is configured from its 'NR "
                                 "Pre-Upscale' tab in the ReShade overlay. With "
                                 "DLSS Frame Generation on, set its cadence to "
                                 "Quality (every frame) or expect stutter.")
                rep.notes.append("If the picture only gets darker, the add-on "
                                 "is not reading the game's exposure buffer "
                                 "(it normalises the frame against it, and "
                                 "some games do not expose one). There is no "
                                 "setting for that: switch the route to "
                                 "native, which runs after the game's own "
                                 "tone mapping.")
            rep.written.append("ReShade.ini")
            if opt.path == STANDALONE:
                # Search paths so ReShade can compile the two shaders; no
                # technique in any preset - the add-on schedules them itself
                # inside its Present callback, in the order it needs.
                _configure(root, rep, reshade_ini.write_shader_paths)
                log("      shader search paths set, no technique enabled - the "
                    "add-on runs DLSS5_AIO_Feed and VORT itself")
                # "F10 compares, F10 opens ReShade" is what this line read
                # when the person picked F10 anyway, after being warned.
                # One key with two jobs is worth a sentence, not a
                # contradiction (gate 1.9.1).
                _ovl = reshade_ini.overlay_key_name()
                _keys = ("F10 compares and also opens ReShade - you picked it "
                         "for the overlay, so one of the two will win"
                         if _ovl == "F10" else
                         f"F10 compares, {_ovl} opens ReShade")
                rep.notes.append("standalone-dlssnr: turn the game's own DLSS, "
                                 "frame generation and anti-aliasing OFF. Game "
                                 "resolution = the monitor's gives DLAA, a lower "
                                 f"one gives DLSS Super Resolution. {_keys}"
                                 "; leave DLSS5_AIO_Feed and "
                                 "vort_MotionEffects unticked, the add-on runs "
                                 "them. Its log is outside the game folder: "
                                 "%LOCALAPPDATA%\\RHI\\Logs\\standalone-dlssnr.log")
            else:
                log("      add-on loading enabled (no shaders needed on this path)")
                rep.notes.append("ReShade's overlay will report 'no .fx files found' "
                                 "on this route - normal, no shaders are used; the "
                                 "add-on tab is what matters")

        # The overlay key, last: carry_over above copies the [INPUT] section
        # from another game and would otherwise put the old binding back.
        # ReShade opens on Home, and a keyboard without one - or without the
        # Insert key OptiScaler uses - has no way in at all (#88).
        _key = _overlay_key_pref()
        if _key and (root / "ReShade.ini").is_file():
            written = True
            try:
                _configure(root, rep, reshade_ini.set_overlay_key, _key)
            except OSError as e:
                # This runs after everything is written and before the
                # manifest: an unwritable ReShade.ini here would have left a
                # fully set-up folder with no record of it. And having said
                # it could not be written, it must not then announce a key.
                log(f"      could not write the overlay key ({e}) - "
                    f"ReShade keeps its own")
                written = False
            name = next((k for k, v in reshade_ini.OVERLAY_KEYS.items()
                         if v == _key), f"0x{_key:02X}")
            if written:
                log(f"      ReShade overlay opens on {name}")
                rep.notes.append(
                    f"ReShade's overlay opens on {name}"
                    + ("" if name == "Home" else ", not Home"))

        # --- 10) dlss5-feed.cfg ----------------------------------------------
        if opt.path == FEEDER:
            begin("dlss5-feed.cfg")
            _backup(root / feedcfg.NAME, rep, root)
            _configure(root, rep, feedcfg.write, opt.feed, host_window=None if x64 else True, names=(feedcfg.NAME,))
            rep.written.append(feedcfg.NAME)
            summary = feedcfg.describe(opt.feed) if opt.feed else []
            if summary:
                for s in summary:
                    log(f"      {s}")
                rep.notes += summary
            else:
                log("      defaults (work_resolution=100, preset=0)")
        elif opt.path == BRIDGE:
            begin("dlss5-bridge.cfg")
            cfg = feedcfg.bridge_defaults(opt.native_dlss)
            cfg.update(opt.feed)          # user overrides (ofa_grid, ofa_perf)
            if (root / feedcfg.BRIDGE_NAME).is_file():
                log("      merging into the existing dlss5-bridge.cfg")
            _backup(root / feedcfg.BRIDGE_NAME, rep, root)
            _configure(root, rep, feedcfg.write_bridge, cfg, names=(feedcfg.BRIDGE_NAME,))
            rep.written.append(feedcfg.BRIDGE_NAME)
            for line in feedcfg.describe_bridge(cfg):
                log(f"      {line}")
                rep.notes.append(line)
            if not opt.native_dlss:
                log("      the bridge will build a synthetic contract from the "
                    "driver's optical flow engine")

    except PermissionError as e:
        note_failure(root, e)
        recorded = _write_manifest(root, g, opt, rep, oproxy or proxy, level, complete=False)
        # A fresh install is taken back out here too (gate 2.0.6): a locked
        # file stopped it just as surely as a failed download. _roll_back
        # says so itself when the lock also keeps the clean-up from finishing.
        left = _roll_back(g, root, rep, fresh, log, replaced=switched, recorded=recorded)
        log("")
        log(f"Windows refused to write a file: {e}")
        # The cause after what was taken out: the result card shows all
        # of it, and cause_of() finds the cause for the one-line callers.
        # Without a record, installing again would back our own files up as
        # the game's, so they go first - once the game no longer holds them.
        raise InstallError(
            f"{left}\n\nWindows refused to write a file:\n{e}\n\n"
            f"Almost always this means the game (or its launcher) is running "
            f"and holding the file open. "
            + ("Close the game first, then delete and rename the files listed "
               "above, and install again."
               if left.startswith(NO_RECORD_HEAD) else
               "Close it and run the install again.")) from e
    except (sources.RateLimited, sources.Unavailable) as e:
        note_failure(root, e)
        recorded = _write_manifest(root, g, opt, rep, oproxy or proxy, level, complete=False)
        left = _roll_back(g, root, rep, fresh, log, replaced=switched, recorded=recorded)
        log("")
        log(str(e))
        # The cause last: the window's result card shows the last line.
        raise InstallError(f"{left}\n\n{e}") from e
    except Exception as e:
        note_failure(root, e)
        note = ""
        if net.is_disk_full(e):
            # Said in words, and recorded: the diagnosis reads this note
            # instead of telling someone with a full drive to install again.
            note = net.DISK_FULL_NOTE
        elif isinstance(e, InstallError):
            # The install's own refusal, raised part way through (the Remix
            # runtime without the neural pass, #148). Recorded as the reason,
            # or the diagnosis reads an unfinished install and says to
            # install again - which is refused again for the same reason.
            # All of it, not the first line: the Remix refusal says what is
            # wrong in its first paragraph and what to tick in its second.
            said = " ".join(ln.strip() for ln in str(e).splitlines() if ln.strip())
            if said:
                note = net.STOP_NOTE + said[:400]
        if note:
            rep.notes.append(note)
        recorded = _write_manifest(root, g, opt, rep, oproxy or proxy, level, complete=False)
        left = _roll_back(g, root, rep, fresh, log, keep_note=note, replaced=switched,
                          recorded=recorded,
                          rewrite=lambda: _write_manifest(
                              root, g, opt, rep, oproxy or proxy, level,
                              complete=False))
        if net.is_disk_full(e):
            raise InstallError(f"{left}\n\n"
                               + net.disk_full_message(e, root, net.CACHE)) from e
        # A connection that failed for a reason with a name (#434's blocked
        # socket, #438's cut handshake): said in words with the host, not
        # as a traceback in the window.
        # Never on the install's own refusal: its words are its own, and one
        # that happened to say "timed out" is not a failed connection.
        kind = (e.kind if isinstance(e, net.Unreachable)
                else "" if isinstance(e, InstallError) else net.net_kind(e))
        if kind:
            if isinstance(e, net.Unreachable):
                said = str(e)
            else:
                what, todo = net.net_explain(kind)
                said = f"The download failed: {what} ({e}). {todo}"
            log("")
            log(left)
            log(said)
            raise InstallError(f"{left}\n\n{said}") from e
        log("")
        log(f"Install did not finish. {left}")
        raise

    _verify_written(root, rep, log)

    # --- record -----------------------------------------------------------
    clear_failure(root)     # this folder's last failure is history now
    _set_gpu_pref(root, g, opt, rep, log)
    _finish_record(_write_manifest(root, g, opt, rep, proxy, level, complete=True), rep, log)
    if not record_lost(rep):
        prefs.add_install(root)
    prog(100, "Done")
    return rep


# ---------------------------------------------------------------- uninstall

@gamelock.exclusive
def apply_tune(g: games.Game, route: str, resolution: int, on_log=None) -> None:
    """Apply a measured scale through the same recovery boundary as installation."""
    if isinstance(resolution, bool) or not isinstance(resolution, int) or not 25 <= resolution <= 100:
        raise InstallError("The working resolution must be an integer from 25 to 100.")
    if route not in (FEEDER, OPTI):
        raise InstallError("Only feeder and OptiScaler installs support this tuning action.")
    _safe_target(g.folder, g.install_dir)
    preflight(g)
    root = g.install_dir
    data = _previous_manifest(root)
    if not data or data.get("path") != route or data.get("complete") is not True:
        raise InstallError("The recorded install changed or is incomplete; check the game before applying this tune.")
    if not isinstance(data.get("files"), list) or not isinstance(data.get("hashes"), dict):
        raise InstallError("This legacy install has no verified ownership record for tuning.")
    name = optiscaler.INI if route == OPTI else feedcfg.NAME
    if not _record_hash(data, name) or not (root / name).is_file():
        raise InstallError(f"The ownership of {name} cannot be verified; it was preserved.")
    rep = Report(game_root=g.folder, written=list(data["files"]),
                 preinstalled=_previously_ours(root), hashes=dict(data["hashes"]))
    for rel in rep.written:
        if not isinstance(rel, str):
            raise InstallError("The install record contains an invalid path.")
        _safe_target(root, root / rel, g.folder)

    def checkpoint():
        data.update(files=list(rep.written), hashes=dict(rep.hashes), complete=False)
        _write_atomic(root / MANIFEST, json.dumps(data, ensure_ascii=False, indent=2))
        return True

    rep.checkpoint = checkpoint
    log = on_log or (lambda *_: None)
    if route == OPTI:
        values = {"WorkingScale": round(resolution / 100.0, 3)}
        _configure(root, rep, optiscaler.enable_nr, log, settings=values, names=(name,))
        data["nr"] = dict(data.get("nr") or {}, **values)
    else:
        values = {"work_resolution": resolution}
        _configure(root, rep, feedcfg.write, values, names=(name,))
        data["feed_cfg"] = dict(data.get("feed_cfg") or {}, **values)
    data.update(files=list(rep.written), hashes=dict(rep.hashes), complete=True)
    _write_atomic(root / MANIFEST, json.dumps(data, ensure_ascii=False, indent=2))


@gamelock.exclusive
def uninstall(g: games.Game, on_log=None) -> list[str]:
    """Remove only what this tool wrote; never touch the game's own files."""
    _safe_target(g.folder, g.install_dir)
    dlss.forget_walk(g.folder)
    dlss.forget_walk(g.install_dir)
    log = on_log or (lambda *_: None)
    root = g.install_dir
    man = root / MANIFEST
    removed: list[str] = []

    # Read ours, or an older release's, whichever is there.
    sources_ = [man] + [root / n for n in LEGACY_MANIFESTS]
    found_man = next((m for m in sources_ if m.is_file()), None)
    data: dict = {}
    if found_man is not None:
        try:
            data = json.loads(found_man.read_text(encoding="utf8"))
            if not isinstance(data, dict):
                raise InstallError("The install record is not an object. No game files were removed.")
            # v1.0/v1.1 used Turkish keys
            files = data.get("files") or data.get("dosyalar") or []
            if found_man != man:
                log(f"found an install recorded by an older version "
                    f"({found_man.name})")
        except (OSError, json.JSONDecodeError) as error:
            raise InstallError("The install record could not be read. No game files were removed.") from error
    else:
        raise InstallError("No install record was found. Unproven game files were preserved; no filename-based cleanup was attempted.")
    if not isinstance(data, dict) or not isinstance(files, list):
        raise InstallError("The install record is malformed. No game files were removed.")
    if not isinstance(data.get("hashes"), dict):
        log("Legacy install: files without byte ownership are preserved. Recorded originals can be restored while their backups are retained.")
        data["hashes"] = {}
    stuck: list[str] = []

    # The manifest is a file in the game folder, and anything can write it -
    # a broken install, a tool that "cleans" mods, a hand edit. Every name in
    # it is turned into a path below and then deleted or overwritten, so a
    # `../` entry would take a file outside the folder with it (#79). Drop
    # those here, once, rather than at each of the three places that build a
    # path from `files`.
    # The manifest can legitimately name a path outside the INSTALL folder -
    # _backup() and _copy() write an absolute one when a file is not under it,
    # and a Remix .trex sits at the game root while the install folder is the
    # executable's subfolder. It can never legitimately name a path outside
    # the GAME, so that is the boundary.
    roots = [root]
    game_root = getattr(g, "folder", None)
    if game_root is not None and Path(game_root) != root:
        roots.append(Path(game_root))

    def _permitted(entry: str) -> bool:
        for r in roots:
            try:
                net.inside(r, entry, absolute_ok=True)
                return True
            except net.OutsideError:
                continue
        return False

    safe: list[str] = []
    for rel in files:
        try:
            if not isinstance(rel, str) or not _permitted(rel):
                raise net.OutsideError(rel)
        except net.OutsideError:
            log(f"ignored an install record entry that points outside the "
                f"game folder: {rel}")
            continue
        safe.append(rel)
    files = safe

    # Only recorded, byte-verified backups may restore a destination.
    all_suffixes = (BACKUP_SUFFIX,) + LEGACY_BACKUP_SUFFIXES
    restored: set[str] = set()
    for rel in list(files):
        suffix = next((value for value in all_suffixes if rel.endswith(value)), None)
        if suffix is None:
            continue
        bak = root / rel
        orig = bak.with_name(bak.name[:-len(suffix)])
        original_key = _entry_key(rel[:-len(suffix)])
        if not bak.is_file():
            expected = _record_hash(data, rel)
            restored.add(original_key)
            if expected and orig.is_file() and net.sha256(orig) == expected:
                continue
            stuck.append(rel)
            log(f"could not restore {orig.name}: its recorded original backup is missing")
            continue
        try:
            if not _permitted(str(orig.absolute())):
                raise OSError("its destination leaves the game folder")
            expected = _record_hash(data, rel)
            if expected and net.sha256(bak) != expected:
                raise OSError("the backup no longer matches the recorded original bytes")
            backup_digest = net.sha256(bak)
            if orig.is_file() and net.sha256(orig) != backup_digest:
                written = _record_hash(data, rel[:-len(suffix)])
                if not written or net.sha256(orig) != written:
                    kept = _displace(orig)
                    log(f"kept changed {orig.name} as {kept.name}")
            _atomic_copy(bak, orig)
            if expected:
                bak.unlink()
            else:
                stuck.append(rel)
                log(f"kept legacy {bak.name}: its earlier ownership cannot be proven")
            removed.append(rel)
            restored.add(original_key)
            log(f"restored: {orig.name} (the game's own file)")
        except (OSError, net.OutsideError) as error:
            stuck.append(rel)
            restored.add(original_key)
            log(f"could not restore: {orig.name} ({error})")

    # The Remix route's one edit outside its own files: a single line in the
    # user's rtx.conf. It is never in `files` - that list gets deleted, and
    # deleting somebody's rtx.conf would take their whole mod configuration
    # with it - so the key is removed by name instead.
    rx = data.get("remix") if isinstance(data.get("remix"), dict) else {}
    if rx.get("conf") and rx.get("key"):
        # Recorded relative to the game folder by the install (`_rel(conf)`),
        # so anything that resolves outside it came from a tampered record.
        try:
            # ...and the Remix route records an absolute rtx.conf whenever
            # the .trex is outside the install folder, which is every game
            # whose executable sits in a subfolder.
            conf_p = None
            for _r in roots:
                try:
                    conf_p = net.inside(_r, str(rx["conf"]), absolute_ok=True)
                    break
                except net.OutsideError:
                    continue
            if conf_p is None:
                raise net.OutsideError(str(rx["conf"]))
        except net.OutsideError:
            log(f"ignored a Remix configuration path outside the game "
                f"folder: {rx['conf']}")
            conf_p = None
        try:
            if conf_p is not None and _restore_remix(conf_p, rx):
                removed.append(f"{rx['conf']} ({rx['key']})")
                log(f"removed: {rx['key']} from {rx['conf']} "
                    f"(nothing else in the file was touched)")
        except OSError as e:
            log(f"could not edit {rx['conf']}: {e}")
            stuck.append("Remix configuration")

    if getattr(g, "emu", None) is not None and g.exe:
        try:
            for line in emulators.restore_backend(g.emu, g.exe):
                log(line)
        except Exception as e:
            log(f"could not restore the emulator's render backend: {e}")
            stuck.append("emulator render backend")
    for name in _restore_sidelined(root, data.get("sidelined"), log, data.get("sidelined_hashes"), stuck):
        removed.append(name + SIDELINE_SUFFIX)

    # Compared with one slash and one case: the no-record fallback lists
    # "bin/d3d9.dll" and "D3D9.dll" while the backup sweep finds
    # "bin\d3d9.dll...backup", and a mismatch deleted the file the restore
    # had just put back (gate 1.9.1).
    def _key(r: str) -> str:
        return r.replace("\\", "/").lower()

    for rel in files:
        if any(rel.endswith(s) for s in all_suffixes) or _key(rel) in restored:
            continue
        p = root / rel
        if not p.is_file():
            continue
        expected = _record_hash(data, rel)
        if not expected:
            stuck.append(rel)
            log(f"kept {rel}: its ownership is unproven")
            continue
        try:
            if net.sha256(p) != expected:
                kept = _displace(p)
                log(f"kept changed {rel} as {kept.name}")
        except OSError as error:
            stuck.append(rel)
            log(f"could not preserve changed {rel}: {error}")
            continue
        if _delete(p):
            removed.append(rel)
            log(f"removed: {rel}")
        else:
            stuck.append(rel)
            log(f"could not remove: {rel} (locked - is the game or its "
                f"launcher still running?)")

    # Never remove an entire helper subtree: it may contain later personal files.
    hostdir = root / HOST_DIR
    try:
        if _permitted(str(hostdir.absolute())) and hostdir.is_dir() and not any(hostdir.iterdir()):
            hostdir.rmdir()
            removed.append(HOST_DIR + "/")
    except OSError as error:
        log(f"kept the helper folder: {error}")

    if stuck:
        data["complete"] = False
        data["notes"] = ["Uninstall is incomplete. Files or original backups could not be verified or restored; all remaining recovery entries were kept."]
        # Keep all entries: a missing original beside a failed backup must be recoverable on retry.
        _write_atomic(man, json.dumps(data, ensure_ascii=False, indent=2))
        _forget_walk(g, root)
        raise InstallError("Uninstall is incomplete. Close the game and check the log; the recovery record and unverified files were preserved.")

    try:
        prefs.drop_install(root)
    except Exception:
        pass
    # The frame-rate measurements were about this install; with it gone they
    # are about nothing, and they would otherwise sit in the settings file
    # for every folder the tool has ever touched.
    try:
        from . import autotune
        autotune.forget(root)
    except Exception:
        pass

    # Windows' graphics preference for the game and the helper: per program,
    # so it goes with this install - as long as it still says what we wrote.
    try:
        for exe in gpupref.restore(_gpu_records(root, g, data.get("gpu_pref"))):
            removed.append(f"Windows graphics setting for {Path(exe).name}")
            log(f"removed: Windows graphics setting for {Path(exe).name}")
    except Exception as error:
        data["complete"] = False
        data["notes"] = [f"Uninstall could not restore the Windows graphics setting: {error}"]
        _write_atomic(man, json.dumps(data, ensure_ascii=False, indent=2))
        raise InstallError(f"Uninstall is incomplete: {error}. Its graphics recovery record was kept.") from error

    # The Vulkan layer is registered once for the whole user, so it may only be
    # removed when the LAST game that needs it goes. Removing it while another
    # Vulkan install still relies on it would silently break that game.
    from . import openxr
    with prefs.mutation_lock():
        for title, read, drop, add, layer in (
                ("OpenXR", prefs.openxr_games, prefs.drop_openxr_game, prefs.add_openxr_game, openxr),
                ("Vulkan", prefs.vulkan_games, prefs.drop_vulkan_game, prefs.add_vulkan_game, vulkan)):
            if str(root) not in read():
                continue
            try:
                still = drop(root)
                if still:
                    log(f"kept the {title} layer: {len(still)} other install(s) still use it")
                    continue
                if layer.unregister():
                    removed.append(f"{title} layer registration")
                    log(f"removed: our ReShade {title} layer registration (no games left)")
                if any(layer.is_ours(path) for path, _ in layer.registrations()):
                    raise OSError(f"the {title} layer is still registered")
            except Exception as error:
                add(root)
                data["complete"] = False
                data["notes"] = [f"Uninstall could not restore the {title} layer: {error}"]
                _write_atomic(man, json.dumps(data, ensure_ascii=False, indent=2))
                raise InstallError(f"Uninstall is incomplete: {error}. Its recovery record was kept.") from error

    # Every folder a removed file lived in, deepest first, if it is empty now.
    # OptiScaler's zip alone brings D3D12_Optiscaler, DlssOverrides and
    # Licenses; deleting the files and leaving the folders looked like an
    # uninstall that "does not remove everything".
    dirs: set[Path] = {root / INCLUDE, root / VORT_INCLUDE, root / SHADERS,
                       root / TEXTURES, root / "reshade-shaders"}
    for rel in files + removed:
        p = root / rel
        for parent in p.parents:
            if parent == root or root not in parent.parents:
                break
            dirs.add(parent)
    for d in sorted(dirs, key=lambda x: len(x.parts), reverse=True):
        try:
            if d != root and d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        except OSError:
            pass

    man.unlink(missing_ok=True)
    for n in LEGACY_MANIFESTS:
        (root / n).unlink(missing_ok=True)
    log(f"Removed {len(removed)} items.")
    _forget_walk(g, root)
    return removed


def _forget_walk(g, root: Path) -> None:
    """Drop the remembered folder walk - at the END as well as the start.

    The safety net walks the game folder mid-uninstall, which fills the
    cache with the folder as it was before the files came out.
    """
    try:
        dlss.forget_walk(g.folder)
        dlss.forget_walk(root)
    except Exception:
        pass


def _delete(p: Path, attempts: int = 4) -> bool:
    """Delete a file, retrying briefly when something still holds it.

    Antivirus scanners and launchers hold files open for a moment after the
    game exits; a single failed unlink used to count as "cannot delete".
    """
    import time
    for i in range(attempts):
        try:
            p.unlink()
            return True
        except FileNotFoundError:
            return True
        except PermissionError:
            if i == attempts - 1:
                break
            time.sleep(0.4 * (i + 1))
        except OSError:
            break
    # Read-only attribute set by a game updater? Clear it and try once more.
    try:
        import stat
        p.chmod(p.stat().st_mode | stat.S_IWRITE)
        p.unlink()
        return True
    except OSError:
        return False
