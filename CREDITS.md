# CREDITS

This pack bundles third-party binaries, all redistributed as-is for personal backup/use.
**Always prefer the original sources for updates.** Nothing here is "owned" by the pack author —
the pack is an assembly, a backup, and a convenience layer.

## Official NVIDIA components

| Component | Version | Source |
|---|---|---|
| `nvngx_dlss.dll` (Super Resolution) | 310.7.129 | NVIDIA DLSS SDK / game-ready builds — also mirrored on TechPowerUp ("NVIDIA DLSS DLL"), TechSpot (310.7.129) |
| `nvngx_dlssg.dll` (Frame Generation) | 310.7.129 | NVIDIA DLSS SDK (github.com/NVIDIA/DLSS, v310.7.0 SDK) |
| `nvngx_dlssd.dll` (Ray Reconstruction) | 310.7.129 | NVIDIA DLSS SDK |
| Streamline `sl.*.dll` set | 2.13.0 | NVIDIA Streamline SDK — `nis.license.txt` / `reflex.license.txt` included |
| DLSS 5 (neural rendering) | — | NVIDIA, announced GTC March 2026, public release planned fall 2026 |

## Community tools & runtimes

| Component | Version | Author / source | License |
|---|---|---|---|
| **DLSS5-Swapper** (`DLSS5-Swapper-Setup-2.2.7.exe`) | 2.2.7 | Rakan Alkhaldi — github.com/rakanki911/DLSS5-Swapper · Nexus: nexusmods.com/site/mods/2228 | MIT |
| **DLSS5-Feeder** (`dlss5-feed.addon64`, `dlss5-feed.addon32`, `DLSS5_Feed.fx`, `feed-vk-layer.zip`, `dlss5-feed-host64.exe`) | v0.6.0-beta.1 | jlrouzies-fr — github.com/jlrouzies-fr/DLSS5-Feeder | not declared on repo; distributed by author via GitHub Releases |
| **`renodx-dlss5.addon64`** (DLSS 5 ReShade add-on) | 0.2026.827.2036 | RenoDX community (Discord) | closed source, community-distributed |
| **`nvngx_dlssnr.dll`** (neural-rendering runtime) | 310.8.0 | NVIDIA production build, *custom-compiled by the RenoDX author* per DLSS5-Swapper README (adds RTX 40/50 support) | NVIDIA proprietary |
| **ReShade** (`dxgi.dll` in `host64\`) | 6.8.0 (add-on build) | crosire — reshade.me | BSD-3-Clause |
| **RHI** (DLSS 5 deployment tool) | — | RankFTW — github.com/RankFTW/RHI | linked, not bundled |
| **LumeniteFX** (motion-vector provider, recommended) | — | Umar Afzaal — github.com/umar-afzaal/LumeniteFX | **linked, not bundled** (no redistribution-friendly license; download from its repo) |
| **OptiScaler** (legacy, `05`) | 0.9.4-final-era build | cdozdil & contributors — github.com/optiscaler/OptiScaler | open source (see repo) |
| **DLSS Enabler** (legacy, `05`) | 0.9.4 | artur-graniszewski/DLSS-Enabler · Nexus: nexusmods.com/site/mods/757 | open source (see repo) |
| **dgVoodoo2** (D3D9 → D3D11) | — | dege — dege.freeweb.hu/dgVoodoo2 | freeware — linked, not bundled |
| **dlss5-dx11-bridge** (transport adapted inside Feeder) | — | NIGos — github.com/NIGos/dlss5-dx11-bridge | MIT (per Feeder README) |

## Motion-vector providers supported by DLSS5-Feeder

**None are bundled in this pack** — both major sources (iMMERSE / MartysMods by Pascal
Gilcher, and LumeniteFX by umar-afzaal) use licenses that forbid public redistribution, so
they are **linked** here. The bundled `reshade-shaders` instead carries the free-to-share set:
ReShade's own core headers, Deband (MIT), SweetFX Levels, LUT, DisplayDepth, Daltonize,
UIMask and qUINT_common.

| `DLSS5_MV_PROVIDER` | Provider | Source | Bundled? |
|---|---|---|---|
| `3` (recommended) | LumeniteFX Kernel | github.com/umar-afzaal/LumeniteFX | no (AGNYA) |
| `1` | iMMERSE Launchpad | MartysMods (Nexus / MartysMods) | no (Gilcher license) |
| `2` | VORT | VORT (Nexus) | no |
| `4` | LumeniteFX QuantMotion | github.com/umar-afzaal/LumeniteFX | no (AGNYA) |
| `0` | Anything writing `texMotionVectors` (qUINT, dh_uber_motion) | Nexus / github.com/AlucardDH/dh-reshade-shaders | no (header only) |

## Pack assembly

- Assembled, documented, packaged: **ShugokiFable** (2026-08-31)
- Source material: the original `!!!DLSS mod` collection (restructured into folders `01`–`05`) plus the official `zofficialdlls` NVIDIA DLL set (byte-verified against the packed copies), with the missing Feeder v0.6.0-beta.1 assets fetched from its GitHub release (`dlss5-feed.addon64`, `DLSS5_Feed.fx`, `feed-vk-layer.zip`). The `reshade-shaders` folder is the free-to-share set (core headers, Deband, Levels, LUT, DisplayDepth, Daltonize, UIMask, qUINT_common) — provider files deliberately excluded (iMMERSE: Pascal Gilcher license forbids public propagation; LumeniteFX: AGNYA license forbids redistribution).
- Known-working evidence: `dlss5-feed-host.log` from the pack owner's session — **Saints Row: The Third (32-bit), 2560×1440 DLAA, feature ready flags=66, 99,000+ frames evaluated** across a full play session.

*If you are a listed author and want your component removed or re-credited differently, open an issue on the repo.*
