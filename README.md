<p align="center">
  <img src="docs/images/logo.svg" width="72" height="72" alt="DLSS 5 AIO mark">
</p>

<h1 align="center">DLSS 5 AIO</h1>

<p align="center"><strong>Official NVIDIA DLSS DLLs plus a DLSS 5 neural-rendering toolkit.</strong></p>

<p align="center">
  Community pack: latest official Super Resolution / Frame Generation / Ray Reconstruction<br>
  DLLs, plus Swapper and Feeder tools that can run DLSS 5 neural rendering in games<br>
  with or without built-in DLSS — including 32-bit titles via a 64-bit helper host.
</p>

<p align="center">
  <a href="https://github.com/ShugokiFable/dlss5-aio/actions/workflows/ci.yml"><img src="https://github.com/ShugokiFable/dlss5-aio/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-8fa3b8?labelColor=0b1016" alt="MIT License"></a>
  <a href="https://github.com/ShugokiFable/dlss5-aio/releases/tag/v1.2.5"><img src="https://img.shields.io/badge/release-v1.2.5-6b8cae?labelColor=0b1016" alt="v1.2.5"></a>
</p>

<p align="center">
  <a href="#pick-your-scenario-30-second-guide">Scenarios</a>
  ·
  <a href="#install-guides">Install</a>
  ·
  <a href="#faq">FAQ</a>
  ·
  <a href="#integrity">Integrity</a>
  ·
  <a href="START-HERE.txt">START-HERE.txt</a>
</p>

**Not affiliated with NVIDIA.** This is an unofficial convenience pack. Official DLSS/Streamline binaries keep NVIDIA's licenses; tools keep their authors' licenses. See [`LICENSE.md`](LICENSE.md) and [`CREDITS.md`](CREDITS.md).

| | |
| --- | --- |
| **Latest release** | [v1.3.0](https://github.com/SenjuWoo/dlss5-aio/releases/tag/v1.3.0) (Swapper 1.1.1 → 2.2.7) |
| **Official NVIDIA DLSS DLLs** | **310.7.129** — Super Resolution, Frame Generation, Ray Reconstruction (documented in [`01-Official-NVIDIA-DLLs/README.md`](01-Official-NVIDIA-DLLs/README.md); signed production builds in the release 7-Zip, hashed in [`SHA256SUMS.txt`](SHA256SUMS.txt)) |
| **DLSS 5 neural-rendering runtime** | `nvngx_dlssnr.dll` **310.8.0** (RenoDX community build; documented in [`02-DLSS5-Neural-Rendering/README.md`](02-DLSS5-Neural-Rendering/README.md)) |
| **Tools** | DLSS5-Swapper **2.2.7** · DLSS5-Feeder **v0.6.0-beta.1** |
| **Needs** | NVIDIA GPU · Windows 10/11 64-bit · **RTX 40/50** for DLSS 5 neural rendering |

Download: [github.com/SenjuWoo/dlss5-aio/releases/latest](https://github.com/SenjuWoo/dlss5-aio/releases/latest). It is a 3-part 7-Zip (~635 MB total): download **all 3 parts** into one folder, right-click part `.001`, **Extract Here** (7-Zip), then open **`START-HERE.txt`**. This git clone is the docs + scripts tree — the large official DLLs live in the release archive, not in git.

**What is DLSS 5?** NVIDIA's next-generation neural-rendering upscaler — announced at GTC in March 2026 and planned for a full release in fall 2026. Its runtimes are already circulating, and the community has built tools that make it work in **any** game: with or without built-in DLSS, 64-bit or 32-bit, DirectX 11/12, Vulkan, even DirectX 9.

This git tree has no app screenshot. Swapper is a third-party installer; Feeder is a ReShade add-on. Do not treat this mark as an NVIDIA logo.

---
## 📋 Pick your scenario (30-second guide)

| # | Your situation | What to use | Folder |
|---|----------------|-------------|--------|
| **1** | Game **already has DLSS** (has a `nvngx_dlss.dll`) and is **DirectX 12** | **DLSS5-Swapper** — one click, auto-backup, auto-restore | `03-DLSS5-Swapper` |
| **2** | Game has **no DLSS**, is **64-bit** (D3D11 / D3D12 / Vulkan) | **DLSS5-Feeder** 64-bit install | `04-DLSS5-Feeder` |
| **3** | Game has **no DLSS**, is **32-bit** (or DirectX 9) | **DLSS5-Feeder** 32-bit install — `dlss5-feed.addon32` + the `host64\` folder | `04-DLSS5-Feeder` |
| **4** | Just want the **latest official DLSS DLLs** in games that already support DLSS | Copy the DLLs from `01` over the game folder | `01-Official-NVIDIA-DLLs` |
| **5** | Prefer the **old-school conversion route** (FSR/XeSS frame gen on any GPU, non-RTX) | OptiScaler / DLSS Enabler — **pick ONE approach per game, never mix** | `05-Legacy-Optiscaler-DLSS-Enabler` |

**Scenario 3 is the magic one this pack is built around:** NGX and the DLSS 5 add-on are 64-bit-only, so for a 32-bit game you drop the tiny 32-bit `dlss5-feed.addon32` next to the game exe *and* the complete `host64\` folder beside it. The add-on ships frames to the bundled 64-bit helper process, which does all the real DLSS 5 work GPU-to-GPU. Proven in practice: **Saints Row: The Third (32-bit) — 1440p DLAA, 99,000+ frames evaluated** (log from the pack owner's session, see `04-DLSS5-Feeder/README.md`).

---

## 📦 What's inside (all versions verified)

```
DLSS5-AIO/
├── 01-Official-NVIDIA-DLLs/          ← the official latest DLSS DLLs
│   ├── nvngx_dlss.dll   310.7.129    Super Resolution
│   ├── nvngx_dlssg.dll  310.7.129    Frame Generation
│   ├── nvngx_dlssd.dll  310.7.129    Ray Reconstruction
│   └── Streamline-2.13.0/            sl.*.dll set (NVIDIA Streamline 2.13.0)
├── 02-DLSS5-Neural-Rendering/        ← the DLSS 5 heart (community-circulated)
│   ├── nvngx_dlssnr.dll  310.8.0     Neural-rendering runtime (RenoDX build, RTX 40/50)
│   └── renodx-dlss5.addon64 0.2026.827.2036   DLSS 5 ReShade add-on (RenoDX)
├── 03-DLSS5-Swapper/                 ← one-click DLSS 5 for DX12 games that have DLSS
│   └── DLSS5-Swapper-Setup-2.2.7.exe
├── 04-DLSS5-Feeder/                  ← DLSS 5 for games with NO DLSS
│   ├── dlss5-feed.addon64            64-bit games
│   ├── dlss5-feed.addon32            32-bit games
│   ├── DLSS5_Feed.fx                 the feeder shader (→ reshade-shaders\Shaders)
│   ├── reshade-shaders/              self-sufficient: feeder shader + ReShade core headers + must-have effects
│   │   └── Shaders/                  Deband, Levels, LUT, DisplayDepth, Daltonize, UIMask, qUINT_common
│   ├── feed-vk-layer.zip             only if a Vulkan game's log asks for it
│   └── host64/                       complete 64-bit helper env for 32-bit games
│       ├── dlss5-feed-host64.exe     the helper process
│       ├── dxgi.dll                  ReShade 6.8.0 (64-bit, add-on build)
│       ├── renodx-dlss5.addon64 + nvngx_dlssnr.dll + nvngx_dlss*.dll + sl.*.dll
│       └── ReShade.ini               pre-tuned DLSS 5 defaults (sanitized)
└── 05-Legacy-Optiscaler-DLSS-Enabler/ ← the old way (kept for reference)
    ├── Optiscaler/                   OptiScaler (upscaler/frame-gen bridge)
    └── dlss-enabler-setup_0.9.4-…exe DLSS Enabler
```

*Provenance: this pack restructures the original `!!!DLSS mod` collection — `GOATED NEW` → folders `02` + `04`, `Older` → folder `05` — and adds the official `zofficialdlls` set as folder `01`, plus the missing 64-bit feeder pieces (`dlss5-feed.addon64`, `DLSS5_Feed.fx`, `feed-vk-layer.zip`). The `reshade-shaders` folder is the free-to-share set: feeder shader + ReShade core headers + standard effects (Deband, Levels, LUT, DisplayDepth, Daltonize, UIMask, qUINT_common) — motion-vector providers are *not* bundled (iMMERSE and LumeniteFX licenses forbid redistribution).*

---

## ⚙️ Requirements

- **NVIDIA GPU + Windows 10/11 64-bit.**
- **DLSS 5 neural rendering (scenarios 1–3): RTX 40 or RTX 50 series.** The bundled `nvngx_dlssnr.dll` is the custom build published by the RenoDX author that adds RTX 40/50 support.
- **Scenario 4 (plain official DLL swap):** works on older RTX cards too — the new DLSS quality/preset improvements apply, but Frame Generation itself needs RTX 40+.
- **Feeder installs need ReShade with add-on support** (the full/unsigned build from reshade.me, ≥ 6.8). The `host64\dxgi.dll` here is the 64-bit add-on build; you still need the matching **32-bit** ReShade in the game folder for scenario 3 (ReShade's installer does this automatically when it detects a 32-bit game).
- **Not compatible with NVIDIA Smooth Motion or OptiScaler running in the same game** — disable them first.
- DLSS 5 add-on is **DirectX 12 only** at its core; the feeder bridges D3D11 / Vulkan / 32-bit / D3D9 to it.

---

## 🚀 Install guides

### Scenario 1 — Game has DLSS, DirectX 12 → DLSS5-Swapper (easiest)

1. Run `03-DLSS5-Swapper\DLSS5-Swapper-Setup-2.2.7.exe` and install it.
2. SmartScreen will warn ("Windows protected your PC") — the build isn't code-signed. Click **More info → Run anyway**.
3. Launch **DLSS 5 Swapper**, drop the **game folder** onto it.
4. It finds the game exe, works out the API, upgrades every DLSS/Streamline DLL it finds (including the ones Unreal hides under `Engine\Binaries\ThirdParty\NVIDIA\NGX\Win64`), places `renodx-dlss5.addon64` + `nvngx_dlssnr.dll` next to the exe, and installs ReShade (add-on build) silently.
5. It **backs everything up first** to `_DLSS5_Backup\` — **Restore originals** puts it all back.
6. Run the game, open the ReShade overlay (Home), and enable **DLSS 5 Neural Rendering**.

Notes: DX12-only (other APIs get a warning). A game under `Program Files` needs the app run as administrator. English and Arabic UI.

### Scenario 2 — Game has NO DLSS, 64-bit → DLSS5-Feeder

1. Install **ReShade with add-on support** against the game exe (Direct3D 10/11/12, tick "Enable loading of add-ons"). This puts `dxgi.dll` next to the game.
2. Copy `04-DLSS5-Feeder\dlss5-feed.addon64` next to the game exe, and the **whole `reshade-shaders\` folder** (feeder shader + ReShade core headers + must-have effects — self-sufficient).
3. Copy `renodx-dlss5.addon64` + `nvngx_dlssnr.dll` + `nvngx_dlss.dll` next to the exe too (`02-DLSS5-Neural-Rendering\` has the first two; `01-Official-NVIDIA-DLLs\` has `nvngx_dlss.dll`). The add-on refuses to start without the neural-rendering runtime beside it.
4. **Motion vectors are required.** The recommended **LumeniteFX Kernel** (`DLSS5_MV_PROVIDER=3`) is a 2-minute download: [github.com/umar-afzaal/LumeniteFX](https://github.com/umar-afzaal/LumeniteFX) (its `Shaders\` + `include\` → `reshade-shaders\Shaders\`, `Textures\lumenite_bluenoise256.png` → `reshade-shaders\Textures\`). Providers can't ship in this pack — iMMERSE and LumeniteFX both forbid redistribution — so the bundled folder instead has everything else (headers + must-have effects). One provider only, enabled ABOVE `DLSS 5 Feed`.
5. In the ReShade overlay (Home): select `DLSS5_Feed.fx` → Preprocessor definitions → set `DLSS5_MV_PROVIDER` to your choice → reload effects. Enable the provider's technique, then **DLSS 5 Feed** *below it*, then enable neural rendering in the **DLSS 5 Neural Rendering** panel.
6. Check `dlss5-feed.log` next to the exe for `feature ready … DLAA` and `frame N delivered`.

### Scenario 3 — Game has NO DLSS, 32-bit (or D3D9) → DLSS5-Feeder 32-bit ⭐

1. Install **32-bit ReShade** with add-on support against the game exe (`dxgi.dll` should be ~4.4 MB — that's the x86 build).
2. Copy **`dlss5-feed.addon32`** next to the game exe and the **whole `reshade-shaders\` folder**.
3. Copy the **entire `host64\` folder** next to the game exe — keep the folder name `host64` (`Game\host64\dlss5-feed-host64.exe`). Everything inside is already configured (helper exe, 64-bit ReShade, DLSS 5 add-on, DLSS runtimes, tuned `ReShade.ini`).
4. Motion vectors + `DLSS5_MV_PROVIDER` exactly as in scenario 2 (steps 4–5). **There is no `renodx-dlss5.addon32`** — on 32-bit the RenoDX add-on stays x64 on the host side.
5. Enable **DLSS 5 Feed** in the overlay. The first fed frame spawns `host64\dlss5-feed-host64.exe` (a window titled "32-bit DLSS 5 Feeder") — that's where the DLSS 5 add-on's own full panel lives. Set `host_window=0` on the add-on page once you're happy with it.
6. **DirectX 9 games:** translate to D3D11 first with **dgVoodoo2** (dege.freeweb.hu) — copy `MS\x86\D3D9.dll` + `dgVoodoo.conf` + `dgVoodooCpl.exe` next to the exe, set `DisableAndPassThru=false`, `VRAM=1GB`, `OutputAPI=d3d11_fl11_0`, verify the watermark, then install the feeder normally (ReShade as `dxgi.dll`, never `d3d9.dll`).

### Scenario 4 — Just update official DLSS DLLs

1. Back up the game's existing `nvngx_dlss*.dll` files.
2. Copy the matching files from `01-Official-NVIDIA-DLLs\` over them (same filenames).
3. Games that use Streamline (files like `sl.common.dll`): update those from `01-Official-NVIDIA-DLLs\Streamline-2.13.0\`.
4. Verify with `SHA256SUMS.txt` in this folder if you want to be thorough.

### Scenario 5 — Legacy (OptiScaler / DLSS Enabler)

See `05-Legacy-Optiscaler-DLSS-Enabler\README.md`. **One approach per game — never run these alongside the DLSS 5 tools.**

---

## 🧠 How DLSS 5-in-any-game works in 30 seconds

- **DLSS 5** (`nvngx_dlssnr.dll`) is a neural-rendering model. Its add-on (`renodx-dlss5.addon64`) is a ReShade add-on that hooks a game's own DLSS calls.
- A game **with** DLSS makes those calls → **DLSS5-Swapper** just drops the new runtime + add-on next to the exe and updates the old DLLs.
- A game **without** DLSS never makes those calls → **DLSS5-Feeder makes the calls itself**: it builds a DLAA "contract" from the ReShade frame + depth + estimated motion vectors, runs a real DLSS evaluate, lets the DLSS 5 add-on hook it, and writes the neural result back into the frame.
- **32-bit** games can't load the 64-bit NGX/add-on → the feeder splits in two: the tiny `addon32` in the game ships frames over shared GPU textures to `host64\dlss5-feed-host64.exe`, a 64-bit process that does the real work and hands the result back. Nothing crosses into system memory.

---

## ❓ FAQ

**Is this official?** The `01` DLLs are genuine NVIDIA production builds (signed, "DVS PRODUCTION"). DLSS 5 itself is official NVIDIA tech, but its runtime here is an early community-circulated build, and the RenoDX add-on is community software. It's beta-grade: expect some temporal softness in fast motion (estimated motion vectors, not the game's real ones).

**Do I need both tools?** No — per game, one or the other: Swapper if the game has DLSS, Feeder if it doesn't. Both need the `02` pieces (the Swapper embeds its own copies; the Feeder reads them from `host64\`).

**Why does a 32-bit game need the `host64\` folder?** NGX and the DLSS 5 add-on only exist as 64-bit code. The helper process in `host64\` is a real 64-bit "fake game" that does the DLSS work and shares the results GPU-to-GPU.

**What if there's ghosting/smearing when moving?** Keep the feeder's motion-vector validation on, use LumeniteFX Kernel (`DLSS5_MV_PROVIDER=3`), and try `preset=5` or `6` in `dlss5-feed.cfg` (legacy CNN presets clamp history harder). DRME (ReshadeMotionEstimation) does **not** compile on ReShade 6.8 — don't use it.

**The DLSS 5 panel is stuck in STANDBY.** The feeder's built-in warm-up re-creates the feature a few seconds in — it normally clears itself.

**Nothing happens, no `dlss5-feed.log`?** Architecture mismatch — a 64-bit `dxgi.dll` can't load into a 32-bit game and vice versa. Check which ReShade build you installed.

**Does it touch my system or go online?** The Swapper 2.x auto-updates itself (one silent check at launch). Nothing here installs drivers. Everything runs from the game folder.

**Is it safe for multiplayer / anti-cheat games?** Not guaranteed — ReShade add-ons, NGX hooking and DLL injection can trigger anti-cheat (BDO, Warframe, APB Reloaded, …). The owner saw BDO warn over similar DLSS injection software. "Technically compatible" ≠ "safe on an online account" — keep this to offline/single-player titles.

**DLSS 5 = Frame Generation?** No. DLAA/Super Resolution, Neural Rendering, Frame Generation and Multi Frame Generation are separate. This setup targets **DLAA + DLSS 5 Neural Rendering**; it doesn't promise frame gen.

---

## 🔧 Troubleshooting

**Log says `SuperSampling.Available=0 NeedsUpdatedDriver=0 MinDriver=0.0`.**

That combination means the driver is fine and NGX simply can't find a DLSS implementation to load — `nvngx_dlss.dll` (and `nvngx_dlssnr.dll` for the Neural Rendering features) must sit **next to the game exe**. No-DLSS games don't ship them; copy from `01-Official-NVIDIA-DLLs` + `02-DLSS5-Neural-Rendering` into the game folder. This is exactly why games with native DLSS (GTA V Enhanced, Palworld) "just work" — they already have the DLLs.

**Log says `SuperSampling.Available=0` / "DLSS is not available on this GPU/driver" (but your GPU is an RTX card and it works in other games).**

First, **make sure the DLLs are present** — see the section above (`Available=0 NeedsUpdatedDriver=0 MinDriver=0.0` = `nvngx_dlss.dll`/`nvngx_dlssnr.dll` missing next to the exe). That was the cause in every reported case so far.

**Log says `opening same-device D3D12 session` (Unity D3D11-on-12 games)?** That is **normal and works**. Unity games like this one render through the 11-on-12 wrapper, the feeder attaches to the game's device, and with the DLLs in place NGX initialises fine. Keep `mode=2` in `dlss5-feed.cfg` and **do not** add `-force-d3d11` — it's not needed (proven: Sledding Game runs DLAA with same-device, no launch flags).

Only if you still get `Available=0` with the DLLs confirmed present AND a same-device session: try adding `-force-d3d11` to Steam launch options as a fallback (forces pure D3D11, feeder creates its own D3D12 device).

**Other quick checks:** driver updated? RTX 40/50 required for the neural-rendering runtime (`nvngx_dlssnr.dll`). No `dlss5-feed.log` at all = wrong ReShade bitness (a 64-bit `dxgi.dll` can't load into a 32-bit game and vice versa). Motion vectors missing = `DLSS5_MV_PROVIDER` shows none in the log — install LumeniteFX Kernel (see scenario 2, step 4).

---

## 🔄 Keeping it updated

- **Official DLSS DLLs:** watch TechPowerUp / TechSpot "NVIDIA DLSS DLL" pages, or the NVIDIA/DLSS GitHub SDK releases. Version shown here: 310.7.129 (SR/FG/RR), Streamline 2.13.0.
- **DLSS5-Swapper:** github.com/rakanki911/DLSS5-Swapper/releases (also on Nexus: site/mods/2228).
- **DLSS5-Feeder:** github.com/jlrouzies-fr/DLSS5-Feeder/releases (also on Nexus: site/mods/2228's sibling pages — search "DLSS 5 Feeder").
- **DLSS 5 add-on / runtime:** RenoDX Discord / github.com/RankFTW/RHI (RHI auto-downloads and keeps them updated).
- After updating any DLL, re-check it against `SHA256SUMS.txt` if integrity matters to you.

## 🔐 Integrity

`SHA256SUMS.txt` in the pack root lists every shipped file. Verify with:

```
sha256sum -c SHA256SUMS.txt
```

---

## Honest status

Verified in this tree:

- latest GitHub release **v1.2.5** (docs-only over v1.2.4; binaries identical)
- documented official DLL versions **310.7.129** (SR/FG/RR) and neural runtime **310.8.0** in folder READMEs
- [SHA256SUMS.txt](SHA256SUMS.txt) hashes for every shipped file
- CI (.github/workflows/ci.yml) runs scripts/check_release.py (doc pointers, license-forbidden shader paths, link check)

Not claimed:

- an NVIDIA partnership, endorsement, or official DLSS 5 installer
- that this git clone contains the official 
vngx_dlss*.dll binaries (they ship in the release 7-Zip)
- anti-cheat safety or online-game compatibility
- Frame Generation from the Feeder/Swapper neural-rendering path (this pack targets DLAA + DLSS 5 Neural Rendering)

## 🙏 Credits & licenses

- **[NVIDIA](https://www.nvidia.com/en-us/geforce/technologies/dlss/)** — DLSS 5, official DLSS/Streamline DLLs (see Streamline folder for NIS/Reflex licenses)
- **[jlrouzies-fr](https://github.com/jlrouzies-fr/DLSS5-Feeder)** — DLSS5-Feeder v0.6.0-beta.1
- **[Rakan Alkhaldi (rakanki911)](https://github.com/rakanki911/DLSS5-Swapper)** — DLSS5-Swapper 2.2.7, MIT
- **[RenoDX (clshortfuse)](https://github.com/clshortfuse/renodx)** — `renodx-dlss5.addon64` + custom `nvngx_dlssnr.dll` (RTX 40/50)
- **[crosire](https://github.com/crosire/reshade)** — ReShade 6.8.0 (BSD-3-Clause)
- **[umar-afzaal](https://github.com/umar-afzaal/LumeniteFX)** — LumeniteFX motion vectors (Kernel + QuantMotion): linked, not bundled (AGNYA license forbids redistribution)
- **[MartysMods / iMMERSE (Pascal Gilcher)](https://github.com/martymcmodding/iMMERSE)** — motion-vector provider: linked, not bundled (license forbids public propagation)
- **[Niklas Haas](https://github.com/crosire/reshade-shaders/blob/slim/Shaders/Deband.fx)** — Deband.fx (MIT) · **[CeeJay.dk](https://github.com/CeeJayDK/SweetFX)** — SweetFX Levels · **[crosire](https://github.com/crosire/reshade-shaders)** — ReShade core headers + qUINT_common (all bundled, free to share)
- **[optiscaler](https://github.com/optiscaler/OptiScaler)** + **[artur-graniszewski](https://github.com/artur-graniszewski/DLSS-Enabler)** — legacy tools
- **[dege](https://github.com/dege-diosg/dgVoodoo2)** — dgVoodoo2 (D3D9 → D3D11, linked)
- **[RankFTW](https://github.com/RankFTW/RHI)** — RHI, the alternative DLSS 5 deploy tool (linked)

Full credits & per-component licenses: **`CREDITS.md`** / **`LICENSE.md`**. Pack assembled, documented and packaged by **ShugokiFable** — this is a personal-use backup & convenience pack; official tools, credit and links always go to the original authors.
