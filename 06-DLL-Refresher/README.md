# 06 - DLL Refresher (swap only, no DLSS 5)

**Every DLSS file on the PC, brought up to date - without installing DLSS 5.**

DLSS5-Swapper's newer versions install the whole DLSS 5 pipeline. This folder is the
other half: a plain file swap that only touches NVIDIA's own `nvngx_dlss*.dll`
runtimes. No injector, no proxy DLL, no ReShade add-on, no hooks - nothing an
anti-cheat looks for. If you just want the newest DLSS in every game, this is it.

## Run it

Double-click **`Refresh-DLSS-DLLs.bat`**.

| Menu | What it does |
|---|---|
| 1 - Scan only | Lists every `nvngx_dlss*.dll` found, its version, and what it would do. Writes nothing. |
| 2 - Update all | Replaces the outdated ones. The original of every file is kept in `_dlss_originals\` next to it. |
| 3 - Restore | Copies all those originals back. |
| 4 - Include DLSS 5 runtime | Adds `nvngx_dlssnr.dll` to the scan (only if you actually use DLSS 5). |
| 5 - Scan a single folder | For when you only care about one game folder. |
| 6 - Self test | Builds a throwaway fixture and proves detect / swap / backup / restore all work. |

Straight from a terminal, if you prefer:

```powershell
.\DLSS-DLL-Refresher.ps1                     # report only, all fixed drives
.\DLSS-DLL-Refresher.ps1 -Roots 'D:\Games'   # report only, one folder
.\DLSS-DLL-Refresher.ps1 -Apply              # do it
.\DLSS-DLL-Refresher.ps1 -Restore            # undo
.\DLSS-DLL-Refresher.ps1 -Apply -Exclude 'Battlefield 6,MarvelRivals'   # leave online games alone
```

On a real library this is what it looks like: **68 DLSS files found, 65 out of date, 3
already current** - the sort of spread you get from a decade of game folders.

## What it will and will not touch

- **Replaces** `nvngx_dlss.dll`, `nvngx_dlssg.dll`, `nvngx_dlssd.dll` when the one
  on disk is older than the pack's copy (or the same version but a different build).
- **Leaves alone** anything already identical, anything *newer* than the pack
  (a build you got elsewhere is not downgraded), and anything whose version it
  cannot read - those are listed for you to check by hand.
- **Never touches 32-bit files.** A 64-bit DLL written over a 32-bit game's copy
  would break that game; the tool reads the PE header and skips them, saying so.
- **Never touches another tool's backups** (`_DLSS5_Backup`, `dlss5-backup`,
  `\Backup\`, its own `_dlss_originals\`) - rewriting one would silently break that
  tool's restore.
- **Skips** `\Windows\`, `WindowsApps` and the recycle bin.
- Files that are locked (game running, service holding them) are reported as
  failed instead of being forced.

**Anti-cheat:** online games with kernel anti-cheat (Battlefield, Marvel Rivals,
GTA Online, ...) can treat a swapped DLL as tampering. The report warns about it,
and `-Exclude` skips those folders entirely. Offline and single-player games are
the point of this tool.

The versions it installs come from `01-Official-NVIDIA-DLLs\` in this pack - update
the pack, and this tool installs whatever the pack ships.

## Why this exists

DLSS5-Swapper 2.2.7, RHI and DLSS5-Autopilot all manage DLSS versions *per game*
through their own interface and their own game-library scan. None of them answers
"is there a single stale DLSS file anywhere on this machine?" - which is what you
want when you have a decade of game folders, emulators, benchmarks and old
installers lying around. This scans the file system and nothing else.

Backups are local (`_dlss_originals\` beside each file), so deleting the pack never
strands your originals.
