# 06 - DLL Refresher (swap only, no DLSS 5 install)

**Every DLSS file on the PC, brought up to date - without installing anything.**

DLSS5-Swapper's newer versions install the whole DLSS 5 pipeline. This folder is the
other half: a plain file swap. No injector, no proxy DLL, no hooks - nothing an
anti-cheat looks for. If you just want the newest DLSS everywhere, this is it.

It manages **everything DLSS-related the pack ships**, anywhere on the PC:

| Files | Where they come from |
|---|---|
| `nvngx_dlss.dll`, `nvngx_dlssg.dll`, `nvngx_dlssd.dll` | `01-Official-NVIDIA-DLLs\` |
| `sl.common.dll`, `sl.dlss.dll`, `sl.dlss_g.dll`, `sl.dlss_nr.dll`, `sl.interposer.dll`, `sl.nis.dll`, `sl.pcl.dll`, `sl.reflex.dll` (Streamline) | `01-Official-NVIDIA-DLLs\Streamline-*\` |
| `nvngx_dlssnr.dll`, `renodx-dlss5.addon64` | `02-DLSS5-Neural-Rendering\` |
| `dlss5-feed.addon64`, `dlss5-feed.addon32`, `DLSS5_Feed.fx` | `04-DLSS5-Feeder\` |

If the pack starts shipping another filename, add it to `$script:Names` in the
`.ps1` or the tool will not know to look for it.

## Run it

Double-click **`Refresh-DLSS-DLLs.bat`**.

> **Run it from the extracted pack, not from the source repo.** The repo carries the
> tool but none of the binaries; the tool now says so instead of failing obscurely.
> If you keep it elsewhere, point it at the DLLs: `-SourceDir 'D:\DLSS5-AIO\01-Official-NVIDIA-DLLs'`.

| Menu | What it does |
|---|---|
| 1 - Scan only | Lists every managed file found, its version, and what it would do. Writes nothing. |
| 2 - Update all | Replaces the outdated ones. The original of every file is kept in `_dlss_originals\` next to it. |
| 3 - Restore | Copies all those originals back. |
| 4 - Skip DLSS 5 runtime | Drops `nvngx_dlssnr.dll` from the scan. Everything else is always included. |
| 5 - Scan a single folder | For when you only care about one game folder. |
| 6 - Self test | Builds a throwaway fixture and proves detect / swap / backup / restore all work. |
| 7 - Include online games | **Off by default.** Turns the anti-cheat skip off - see below. |

Straight from a terminal, if you prefer:

```powershell
.\DLSS-DLL-Refresher.ps1                     # report only, all fixed drives
.\DLSS-DLL-Refresher.ps1 -Roots 'D:\Games'   # report only, one folder
.\DLSS-DLL-Refresher.ps1 -Apply              # do it
.\DLSS-DLL-Refresher.ps1 -Restore            # undo
.\DLSS-DLL-Refresher.ps1 -Apply -SkipNR      # leave the DLSS 5 runtime alone
.\DLSS-DLL-Refresher.ps1 -Apply -Exclude 'Battlefield 6,MarvelRivals'   # leave online games alone
```

## What it will and will not touch

- **Replaces** any managed file that is older than the pack's copy, or the same
  version but a different build, or (for version-less files like the `.fx` shader)
  simply different content.
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

**Anti-cheat:** online games with kernel anti-cheat (Fortnite, Marvel Rivals, Star
Citizen, Battlefield, Call of Duty, Overwatch, The Finals, Helldivers 2, Palworld,
Halo, GTA V Enhanced, Black Desert, Warframe, Destiny 2, Valorant, Apex, Tarkov,
PUBG, Rainbow Six, Elden Ring, The Division) are **skipped by default** - they still
show up in the report, marked with the reason. `-ForceOnline` (menu option 7) turns
that off; `-Exclude` skips further folders by name. Matching ignores spaces and
punctuation, so `-Exclude 'Marvel Rivals'` catches a `MarvelRivals` folder.

Offline and single-player games are the point of this tool.

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
