# 06 - DLL Refresher

An advanced command-line tool for replacing existing managed files with the
versions in an extracted DLSS 5 AIO pack. It does not install DLSS into a game
that lacks it. The unified app covers broader deployment and vendor workflows.

Double-click **Refresh-DLSS-DLLs.bat** for the existing scan/update/restore menu.
Run it from a complete extracted pack, or select its `01-Official-NVIDIA-DLLs`
folder with menu option 8. The source repository alone lacks the NVIDIA binaries.

```powershell
.\DLSS-DLL-Refresher.ps1 -Roots 'D:\Games'             # report only
.\DLSS-DLL-Refresher.ps1 -Roots 'D:\Games' -Apply      # update eligible files
.\DLSS-DLL-Refresher.ps1 -Roots 'D:\Games' -Restore    # restore verified originals
.\DLSS-DLL-Refresher.ps1 -Apply -SkipNR               # omit nvngx_dlssnr.dll
.\DLSS-DLL-Refresher.ps1 -Exclude 'Battlefield 6,MarvelRivals'
.\DLSS-DLL-Refresher.ps1 -SelfTest
```

Without `-Roots`, scans ready fixed drives. Missing or inaccessible paths make
the result incomplete and return exit code 1. A dry run never changes game files.

## Managed files

| Source folder | Existing files it can replace |
|---|---|
| `01-Official-NVIDIA-DLLs` | `nvngx_dlss.dll`, `nvngx_dlssg.dll`, `nvngx_dlssd.dll` |
| Latest `01-Official-NVIDIA-DLLs/Streamline-*` | `sl.common.dll`, `sl.dlss.dll`, `sl.dlss_g.dll`, `sl.dlss_nr.dll`, `sl.interposer.dll`, `sl.nis.dll`, `sl.pcl.dll`, `sl.reflex.dll` |
| `02-DLSS5-Neural-Rendering` | `nvngx_dlssnr.dll`, `renodx-dlss5.addon64` |
| `04-DLSS5-Feeder` | `dlss5-feed.addon64`, `dlss5-feed.addon32`, `DLSS5_Feed.fx` |

Every selected source must match its exact entry in the pack's `SHA256SUMS.txt`.
Native files require the expected PE architecture; NVIDIA runtimes require a
readable version. This proves consistency with that manifest. It does not
independently authenticate the pack's publisher.

Newer installed versions are left alone. Equal versions with different bytes,
older versions, and changed versionless add-ons/shaders are eligible for update.
An unreadable target runtime or architecture mismatch is skipped. Matching
architecture and version do not establish a game's ABI or Streamline compatibility.

## Backups and recovery

Before replacement, the tool verifies the original in `_dlss_originals` beside
the target and records its SHA-256 in `manifest.json`. It stages and verifies the
new file, replaces it atomically, verifies the installed bytes, and rolls back
if the final commit fails. Repeated updates retain the first original.

Restore works **without the source pack**. It verifies the backup and accepts
only a target matching the original or a recorded installed/pending hash.
Later personal edits, changed/missing backups, malformed ledgers, and locked
files fail without being overwritten. Failures return exit code 1.

Old v1.4.8 backups have no recovery ledger. They remain untouched. Copy them
back manually after checking the current game files; the tool cannot establish
whether a later game update or personal edit should be kept.

Backup/reference trees, Windows directories, source packs, installed DLSS tool
folders, AI profiles, session/model stores, and directory/file links are excluded
before traversal. `-Exclude` adds more folder matches. Concurrent mutation
commands are refused to prevent conflicting writes to the same recovery ledger.

Known online-title names are skipped by default. This is a path-name heuristic,
not anti-cheat detection. `-ForceOnline` disables that heuristic. DLL replacement,
including vendor runtimes, is not guaranteed compatible with a game or anti-cheat.

Failures are logged to `%LOCALAPPDATA%\DLSS5AIO\Logs\refresher.log`.
`-DebugLog` also records startup version and resolved command settings.

Functional regression checks use disposable files and real Windows file locks:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\Test-Refresher.ps1
```
