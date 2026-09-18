# 04 — DLSS5-Feeder (DLSS 5 for games with NO DLSS)

**Real NVIDIA DLSS 5 Neural Rendering in games that never had DLSS — D3D11, D3D12, Vulkan,
32-bit, even DirectX 9.**

> **Beginner briefing.** There are exactly TWO ways DLSS 5 Neural Rendering gets into a game:
>
> 1. **The game already has native DLSS** → the RenoDX DLSS 5 add-on hooks the game's existing
>    NVIDIA NGX/DLSS calls. No feeder needed → use `03-DLSS5-Swapper`.
> 2. **The game has NO DLSS at all** → **DLSS5-Feeder creates the DLSS inputs itself**, using ReShade.
>
> Point 2 is the important one: **the game does NOT need FSR, XeSS, DLSS, OptiScaler, or DLSS
> Enabler first.** The feeder takes what ReShade already has — the rendered color, the depth
> buffer, and *estimated* motion vectors — and feeds them into NVIDIA NGX/DLSS through RenoDX,
> as if the game had native DLSS all along.

---

## Files in this folder

| File / folder | What it is | Used by |
|---|---|---|
| `reshade-shaders/` | **Drop-in ReShade folder — everything the shader side needs** (see below) | both |
| `dlss5-feed.addon64` | 64-bit feeder add-on (executable ReShade add-on, not a shader) | **64-bit** games |
| `dlss5-feed.addon32` | 32-bit feeder add-on — talks to the `host64` helper | **32-bit** games |
| `DLSS5_Feed.fx` | The feeder shader (also inside `reshade-shaders\Shaders\`) | both |
| `feed-vk-layer.zip` | Vulkan interop fallback — **only if a Vulkan game's log asks for it** | Vulkan |
| `host64\` | The complete 64-bit helper environment for 32-bit games | **32-bit** games |

### The bundled `reshade-shaders\` folder (v1.3.0)

Everything ReShade needs to **compile and run the feeder out of the box**, in ReShade's own
folder layout — copy the whole folder next to the game exe (or merge into an existing
`reshade-shaders`):

```
reshade-shaders\
├── Shaders\
│   ├── DLSS5_Feed.fx              the feeder effect itself
│   ├── ReShade.fxh + ReShadeUI.fxh + Macros.fxh + Blending.fxh + TriDither.fxh + DrawText.fxh
│   │                              ReShade's core headers — DLSS5_Feed.fx needs these to compile
│   ├── Deband.fx                  must-have: removes color banding (MIT, Niklas Haas)
│   ├── SweetFX\Levels.fx          must-have: the classic Levels / brightness-contrast effect
│   ├── LUT.fx · DisplayDepth.fx · Daltonize.fx · UIMask.fx   standard free effects
│   └── qUINT\qUINT_common.fxh     shared header for texMotionVectors-style providers (crosire)
└── Textures\                      (font atlas + LUTs these effects reference)
```

This folder is **self-sufficient**: it includes ReShade's own headers, so the feeder shader
compiles even against a bare ReShade install that ships no shaders.

**What is NOT bundled, and why** — the motion-vector providers:

| Provider | `DLSS5_MV_PROVIDER` | Bundled? | Why |
|---|---|---|---|
| **LumeniteFX Kernel** ⭐ recommended | `3` | ❌ no | AGNYA license — **redistribution prohibited** |
| **LumeniteFX QuantMotion** | `4` | ❌ no | AGNYA license — redistribution prohibited |
| **iMMERSE Launchpad** | `1` | ❌ no | Pascal Gilcher license — **public propagation strictly forbidden** |
| VORT | `2` | ❌ no | install from its repo |
| Anything writing `texMotionVectors` (qUINT, dh_uber_motion) | `0` | ❌ no | install from their repos |

(Your own backups of these still work — this restriction is only about **redistributing**
them in a public repo.) Download one provider from its source (Kernel: github.com/umar-afzaal/
LumeniteFX — 2 minutes), drop its files into `reshade-shaders\Shaders\` (plus its textures),
set `DLSS5_MV_PROVIDER`, and you're set.

---

## How it works

### 64-bit game with no DLSS (the easy case)

```
64-bit game
  → x64 ReShade (add-on build)        dxgi.dll next to the exe
  → motion-vector provider            one of the .fx shaders
  → DLSS5_Feed.fx                     turns frame+depth+MV into DLSS's guide textures
  → dlss5-feed.addon64                makes the actual DLSS evaluate call
  → renodx-dlss5.addon64              hooks it → DLSS 5 Neural Rendering
  → nvngx_dlss.dll + nvngx_dlssnr.dll the runtimes
```

No `host64` bridge needed. D3D12 is the cleanest case (NGX works through D3D12 directly);
D3D11 also works — the feeder creates its own D3D12 device internally for the DLSS work and
returns the result to the D3D11 game.

### 32-bit game with no DLSS (the confusing case, solved)

NVIDIA's NGX/DLSS 5 stack and the `renodx-dlss5` add-on are **64-bit only**, and a 32-bit game
cannot load a 64-bit DLL. **There is no such thing as `renodx-dlss5.addon32`** — don't look for
one. Instead the 32-bit game uses the **32-bit feeder add-on** + a **separate 64-bit helper**:

```
32-bit game
  → x86 ReShade                       x86 dxgi.dll in the game folder
  → dlss5-feed.addon32                captures color/depth/motion vectors in the game
  → shared GPU textures + fences      (GPU-to-GPU, nothing crosses into system memory)
  → host64\dlss5-feed-host64.exe      a real 64-bit process — its own D3D12 device
  → x64 ReShade + renodx-dlss5.addon64 + nvngx_dlssnr.dll
  → DLSS 5 result handed back to the 32-bit game
```

**Directory detail (a common beginner mistake):** keep the helper as a **folder named
`host64`** next to the game exe — `Game\host64\dlss5-feed-host64.exe`. Do *not* scatter its
files flat beside the exe if the feeder expects `host64\`. The host folder already contains
the x64-side components it needs (x64 ReShade, the DLSS 5 add-on, `nvngx_dlssnr.dll` etc.).

**The x86 game-side ReShade DLL and the x64 host-side ReShade DLL are NOT interchangeable.** A
32-bit game cannot load an x64 ReShade DLL or an x64 add-on directly.

### DirectX 9 games

D3D9 itself can't work (SM3 cap, no shared handles). Translate with **dgVoodoo2** first:

```
DX9 game → dgVoodoo2 (DX9 → D3D11) → ReShade → DLSS5-Feeder → DLSS 5
```

A 32-bit DX9 game combines both complications: DX9→D3D11 translation **and** the 32-bit→64-bit
host bridge. See step 6 of the 32-bit install below.

---

## Install — 64-bit game

1. Install **ReShade with add-on support** (reshade.me, full/unsigned build, Direct3D 10/11/12,
   tick "Enable loading of add-ons") against the game exe → `dxgi.dll` appears next to it.
2. Copy `reshade-shaders\` (the whole folder) next to the game exe — it contains `DLSS5_Feed.fx`
   and the bundled motion-vector providers. If the game already has a `reshade-shaders`, merge
   (or just copy `DLSS5_Feed.fx` and the provider you want into its `Shaders\`).
3. Copy `dlss5-feed.addon64` next to the game exe, plus `renodx-dlss5.addon64` +
   `nvngx_dlssnr.dll` + `nvngx_dlss.dll` (from `02-DLSS5-Neural-Rendering\` and
   `01-Official-NVIDIA-DLLs\`). The add-on refuses to start without the neural-rendering
   runtime beside it.
4. **Motion vectors** — pick ONE provider and set `DLSS5_MV_PROVIDER` (see the table below).
   The recommended **LumeniteFX Kernel** (`=3`) is a 2-minute download:
   github.com/umar-afzaal/LumeniteFX → its `Shaders\` + `include\` → `reshade-shaders\Shaders\`,
   `Textures\lumenite_bluenoise256.png` → `reshade-shaders\Textures\`.
   (Providers can't be bundled in this public pack — iMMERSE and LumeniteFX both forbid
   redistribution. The bundled folder has the core headers + must-have effects instead.)
5. ReShade overlay (Home) → select `DLSS5_Feed.fx` → **Preprocessor definitions** →
   set `DLSS5_MV_PROVIDER` to your chosen value → reload effects.
6. Enable the provider's technique, then **DLSS 5 Feed** *below it*, then enable neural
   rendering in the **DLSS 5 Neural Rendering** panel. Keep the game's MSAA/SSAA off.
7. Verify: `dlss5-feed.log` next to the exe shows `feature ready … DLAA` and `frame N delivered`.

## Install — 32-bit game (beta) ⭐

1. Install **32-bit ReShade** with add-on support against the game exe (the installer detects
   32-bit games automatically; `dxgi.dll` ≈ 4.4 MB = the x86 build).
2. Copy **`dlss5-feed.addon32`** next to the game exe, and `reshade-shaders\` as in step 2 above.
3. Copy the **entire `host64\` folder** next to the game exe — keep the folder name `host64`,
   everything inside is pre-configured (helper exe, 64-bit ReShade, DLSS 5 add-on, DLSS
   runtimes, tuned `ReShade.ini`).
4. Motion vectors + `DLSS5_MV_PROVIDER` — same as steps 4–5 of the 64-bit install.
5. Enable **DLSS 5 Feed** in-game. The first fed frame spawns `host64\dlss5-feed-host64.exe`
   (window title "32-bit DLSS 5 Feeder") — that's the DLSS 5 helper doing the real work; its
   own settings panel lives in that window or on the game's ReShade overlay with an **Apply**
   button. Set `host_window=0` on the add-on page once happy. Logs: `host64\dlss5-feed-host.log`
   and `host64\ReShade.log`. If the host dies, the feed disables itself and the game renders
   normally.
6. **DirectX 9 games:** translate with **dgVoodoo2** first (dege.freeweb.hu): `MS\x86\D3D9.dll`
   + `dgVoodoo.conf` + `dgVoodooCpl.exe` next to the exe, `DisableAndPassThru=false`,
   `VRAM=1GB`, `OutputAPI=d3d11_fl11_0`, verify the watermark, then install the feeder normally
   (ReShade as `dxgi.dll`, **never** `d3d9.dll`).

## Install — Vulkan game

Same as 64-bit, but ReShade is a Vulkan **layer** (register the game exe in its installer;
ensure `AddonPath=.\` under `[ADDON]` in `ReShade.ini`). The add-on adds the interop
extensions itself; **only** if `dlss5-feed.log` reports missing interop entry points, unzip
`feed-vk-layer.zip` and launch via its `run-with-feed-layer.bat`.

---

## Motion vectors — why they matter

Old games don't expose the high-quality engine motion vectors that native DLSS integrations
use. DLSS5-Feeder therefore uses **ReShade motion-vector reconstruction** — optical-flow
shaders that estimate where each pixel moved since the last frame.

| `DLSS5_MV_PROVIDER` | Provider | Status in this pack |
|---|---|---|
| `0` | anything writing `texMotionVectors` (qUINT, dh_uber_motion) | `qUINT_common.fxh` bundled; shaders from their repos |
| `1` | iMMERSE Launchpad (MartysMods) | download — not redistributable |
| `2` | VORT | install from its repo |
| `3` | **LumeniteFX Kernel** | ⭐ recommended — download (not redistributable) |
| `4` | LumeniteFX QuantMotion | download — not redistributable |

Rules:

- **Only use ONE active motion-vector provider** unless a specific shader's docs say otherwise.
- Enable the provider's technique **ABOVE** the `DLSS 5 Feed` technique in the effect list.
- **Not DRME / ReshadeMotionEstimation** — it does not compile on ReShade 6.8 (silently writes
  nothing; the feeder detects this and says so in the overlay + log).
- **Bad motion vectors look like:** ghosting, trails, unstable hair, unstable particles,
  smearing around moving characters, bad edges during fast camera movement. If you see those,
  suspect the provider (or the depth buffer, below) *before* blaming DLSS.

## Depth also matters

ReShade must be able to read the game's **actual scene depth buffer**. If the wrong depth
buffer is selected, the feeder may run but produce poor or broken results. Check ReShade's
depth/debug views (ReShade overlay → depth preview, or the feeder's own
`DLSS5_Feed_Debug` technique) before blaming DLSS.

---

## ⚠️ Anti-cheat warning (read this for online games)

Full ReShade add-ons, NGX hooking, wrappers and DLL injection **can trigger anti-cheat
systems**. For old/offline/single-player games this is much less concerning. For games with
active anti-cheat (BDO, Warframe, APB Reloaded, …) treat the DLSS 5 add-on stack as **a risk
even if plain ReShade itself is tolerated** — the pack owner personally saw BDO warn when
similar DLSS injection/modification software was used. **"Technically compatible" is not the
same as "safe to use on an online account."** Experiment on offline/single-player titles.

## DLSS 5 is NOT the same thing as Frame Generation

This setup does not automatically add every DLSS feature. DLSS Super Resolution, DLAA,
Neural Rendering, Frame Generation and Multi Frame Generation are separate technologies. The
current feeder setup is primarily interesting for **DLAA / DLSS 5 Neural Rendering** in
unsupported games — it does not promise Frame Generation or Multi Frame Generation.

## Shaders vs. add-ons (`.fx` vs `.addon64`)

`*.fx` files are **shaders** (post-processing code ReShade runs). `*.addon64` / `*.addon32`
files are **executable ReShade add-ons**. DLSS5-Feeder and RenoDX need the add-on-capable
ReShade build — "enable loading of add-ons" during ReShade install — not merely ordinary
shader support.

---

## Troubleshooting (quick)

| Symptom | Fix |
|---|---|
| Image smears while moving | No vectors reaching DLSS — overlay "Motion vectors" section names the cause (provider not installed / disabled / failed to compile / wrong one enabled) |
| Warping around flames/transparents | Keep validation on; use provider 3; try `preset=5`/`6` in `dlss5-feed.cfg` |
| No `dlss5-feed.log` at all | ReShade architecture mismatch: x64 `dxgi.dll` in a 32-bit game or vice versa |
| DLSS 5 panel stuck STANDBY | Built-in warm-up re-creates the feature after a few seconds |
| "ran out of video memory" (D3D9 path) | Raise `VRAM` in `dgVoodoo.conf` (1 GB; not 2 GB — 32-bit signed overflow) |
| Ghosting/trails while moving | Check depth buffer first, then the motion-vector provider; one provider only |
| Conflicts | Disable **NVIDIA Smooth Motion** and **OptiScaler** in the same game |

Logs: `dlss5-feed.log`, `ReShade.log`, `host64\dlss5-feed-host.log`, `host64\ReShade.log`.
Config: `dlss5-feed.cfg` (auto-created) — full key reference in the project's README.

---

## Proven working (pack owner's session)

**Saints Row: The Third (32-bit, D3D11)** — 2560×1440 DLAA, `feature ready … flags=66`,
99,000+ frames evaluated over a full play session, host window healthy throughout.
Upstream reports also: Metro 2033 Redux (64-bit D3D11), LOTR War in the North (64-bit D3D12),
Splinter Cell Blacklist (32-bit), BioShock Remastered (32-bit), Fable Anniversary (32-bit D3D9
via dgVoodoo2), DOOM 2016 (64-bit Vulkan).

## Source

github.com/jlrouzies-fr/DLSS5-Feeder — v0.6.0-beta.1 (2026-08-30). Beta software: temporal
quality of *estimated* motion vectors; HUD processed with the scene. Full documentation,
configuration reference and building instructions live in the project's README.
