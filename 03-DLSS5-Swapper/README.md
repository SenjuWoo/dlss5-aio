# 03 — DLSS5-Swapper (one-click DLSS 5 for games that already have DLSS)

**The easiest path.** Point it at a game folder; it does everything:

1. **Finds the game** — reads the import table of every `.exe` to separate the game from its
   launcher and detect the rendering API (handles protected builds like GTA V Enhanced and
   engine-DLL renderers like Control / Unity).
2. **Upgrades every DLSS and Streamline DLL** where it already lives — including the ones Unreal
   buries under `Engine\Binaries\ThirdParty\NVIDIA\NGX\Win64`. Already-current files are skipped;
   folders named `backup`/`old`/`original` are left alone.
3. **Places the DLSS 5 add-on** (`renodx-dlss5.addon64` + `nvngx_dlssnr.dll`) next to the executable.
4. **Installs ReShade silently** (add-on build, verified by inspecting the binary). If the game
   already runs ReShade as a `.asi` (e.g. GTA V + NaturalVision), the `.asi` is upgraded in place
   instead — never two ReShades.
5. **Backs up everything first** to `_DLSS5_Backup\` with a manifest. **Restore originals** puts
   every file back and removes only what the app added.

## Install

- Run `DLSS5-Swapper-Setup-2.2.7.exe` (start-menu/desktop shortcuts, clean uninstall).
  A portable build also exists on the release page if you prefer no installation.
- **SmartScreen** will warn — the build is not code-signed. **More info → Run anyway.**
- Games under `Program Files` need the app run **as administrator** (it checks before touching anything).
- The app **auto-updates itself** at launch when a new release exists — you don't need to re-download the pack to stay current.

## Requirements & limits

- Windows 10/11 64-bit, NVIDIA RTX.
- The DLSS 5 add-on is **DirectX 12 only** — the app warns for other APIs.
- English + Arabic UI (RTL-aware).

## Sources

- github.com/rakanki911/DLSS5-Swapper · Nexus mirror: nexusmods.com/site/mods/2228 · MIT
- Backed up here at v2.2.7 for convenience — the app auto-updates itself, so this stays current.
