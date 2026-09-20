# 01 — Official NVIDIA DLSS DLLs (latest)

**The official, NVIDIA-signed production builds** ("DVS PRODUCTION"). Drop them over a game's existing
DLSS files to bring it up to date — the most common, safest DLSS upgrade there is.

| File | Version | What it is | What it does |
|---|---|---|---|
| `nvngx_dlss.dll` | **310.9.1.0** | DLSS Super Resolution | Upscaling + quality presets (transformer model) |
| `nvngx_dlssg.dll` | **310.9.1.0** | DLSS Frame Generation | AI frame interpolation (needs RTX 40+ to actually generate frames) |
| `nvngx_dlssd.dll` | **310.9.1.0** | DLSS Ray Reconstruction | Denoises ray-traced lighting |
| `Streamline-2.13.0\sl.*.dll` | **2.13.0** | NVIDIA Streamline | Runtime used by newer games (Cyberpunk 2077, Alan Wake 2, …) to load DLSS |

## How to update a game

1. Find the game folder (the one with the game `.exe`) — DLSS DLLs usually sit right there,
   sometimes under `Engine\Binaries\ThirdParty\NVIDIA\NGX\Win64\` (Unreal Engine games).
2. **Back up** the existing `nvngx_dlss*.dll` files (rename them or copy them to a folder called `backup`).
3. Copy the matching files from this folder over them. Filenames must stay the same.
4. Streamline-based games: update the `sl.*.dll` files from `Streamline-2.13.0\` too
   (usually in the same folder, or `Engine\Binaries\ThirdParty\NVIDIA\Streamline\Win64\`).

## Notes

- All files are **signed by NVIDIA, unmodified** — verify with `sha256sum -c SHA256SUMS.txt` (pack root).
- Updating SR/RR works on RTX 20/30 series too (better quality/presets). Frame Generation
  itself requires RTX 40+.
- If you want DLSS 5 neural rendering on top of these, see folders `02`, `03` and `04`.
- New versions appear regularly: TechPowerUp / TechSpot "NVIDIA DLSS DLL" pages, or
  github.com/NVIDIA/DLSS (SDK). NVIDIA does not publish standalone DLL downloads — the
  community mirrors do.
