> Legacy v1.4.8 manual-pack snapshot. Versions and instructions below describe that archived payload. Use the current portable AIO release for verified current runtime downloads and game installation.

# 05 — Legacy: OptiScaler & DLSS Enabler (the old way)

> **⚠️ Pick ONE approach per game.** These are the *previous generation* of "DLSS on any
> hardware/game" tools. They do not mix with the DLSS 5 tools (`02`/`03`/`04`) — running both in
> the same game conflicts. (The pack owner's note: *"Pick one or try both but one at the time."*)

## OptiScaler

**Bridges upscaling/frame generation across GPUs.** Replaces a game's native upscaler with
DLSS2+ / XeSS / FSR2+ regardless of GPU brand, and enables FSR-FG / XeFG on titles without
frame gen. Includes Nukem's `dlssg_to_fsr3` for DLSSG→FSR3 conversion.

- Files in `Optiscaler\` must be **extracted into the game folder** (see the `!! README_EXTRACT
  ALL FILES TO GAME FOLDER !!.txt` inside).
- Needs a recent NVIDIA driver with the `fakenvapi` shim (`fakenvapi.dll` + `fakenvapi.ini`
  included; DLSS-based features require an RTX GPU, FSR/XeSS routes work on AMD/Intel too).
- `D3D12_Optiscaler\D3D12Core.dll` is an optional D3D12 agnostic-mode runtime.
- Component licenses (AMD FidelityFX, XeSS, DirectX) in `Optiscaler\Licenses\`.
- Source: github.com/optiscaler/OptiScaler (open source). Check their releases — newer builds exist.

## DLSS Enabler

**Simulates DLSS upscaler and DLSS-G frame generation on any DirectX 12 GPU** in DX12 games that
support DLSS 2/3 natively (older alternative to OptiScaler; lets AMD/Intel cards use the DLSS
options in-game, routed to FSR/XeSS underneath).

- `dlss-enabler-setup_0.9.4-final.20260718._MM.exe` — the setup installer; `_MM` = mod-manager
  variant. This is an older snapshot — see the project for current versions.
- Source: github.com/artur-graniszewski/DLSS-Enabler · Nexus: nexusmods.com/site/mods/757.

## Why are these here?

The user's original `!!!DLSS mod` collection kept them as the fallback route. They're archived
here unchanged for reference — the DLSS 5 path (folders `02`–`04`) is the current recommended one
on RTX 40/50 hardware.
