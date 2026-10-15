> Legacy v1.4.8 manual-pack snapshot. Versions and instructions below describe that archived payload. Use the current portable AIO release for verified current runtime downloads and game installation.

# host64 — 32-bit game helper environment

The **complete** `host64\` folder (with all runtime DLLs: `dlss5-feed-host64.exe`,
64-bit ReShade `dxgi.dll`, `renodx-dlss5.addon64`, `nvngx_dlssnr.dll`, `nvngx_dlss*.dll`,
Streamline set, pre-tuned `ReShade.ini`) ships **inside the release download** — it's ~250 MB
of binaries, too heavy for the repo itself.

**How to use (32-bit game with no DLSS):**
1. Install 32-bit ReShade with add-on support against the game exe.
2. Copy `dlss5-feed.addon32` next to the game exe, `DLSS5_Feed.fx` → `reshade-shaders\Shaders\`.
3. Copy the **entire `host64\` folder** from the release pack next to the game exe.
4. Install a motion-vector provider (LumeniteFX Kernel recommended), set
   `DLSS5_MV_PROVIDER = 3` on `DLSS5_Feed.fx` in the ReShade overlay, enable **DLSS 5 Feed**.

Full instructions: `04-DLSS5-Feeder/README.md` (scenario 3).
