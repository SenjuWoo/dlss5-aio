# Game installer provenance

The game installation engine and interface are adapted from the MIT-licensed
[DLSS5-Autopilot](https://github.com/Kizzuwatnaa/DLSS5-Autopilot) at commit
`f7e347c6493361e30c6609f40be66ee2e77677ce` (2026-10-14), version 2.0.8.
Its copyright and license are retained in `UPSTREAM-LICENSE.txt`.

DLSS 5 AIO separates its profile, cache, log, application mutex and updater from
Autopilot. Existing Autopilot preferences are neither imported nor overwritten.
The game-directory manifest and backup suffixes remain recognizable, but the
v2.0.1 fork adds byte-ownership hashes and durable checkpoints. Earlier records
without hashes cannot certify originals retroactively: unknown files and
backups are retained, and some legacy restoration requires manual review.
Other installer applications do not honor AIO's game/profile/cache locks;
close them before modifying the same files.

Video, screen capture and image processing are excluded from this application's
interface and CLI. The internal video helper remains because shared upstream
diagnostic and game-control modules import its data structures. Remix and VR are
game installation routes and remain available with their existing limitations.
Community issue reports target SenjuWoo/dlss5-aio; automatic community-result
downloads are disabled until this fork publishes its own verified aggregate.

Native NVIDIA SR/RR/FG installation shares AIO's SHA256-pinned runtime catalog
with DLL maintenance: version 310.9.16 from the RHI community mirror is the
automatic choice, with NVIDIA SDK 310.9.1 retained as a selectable fallback.
The installer validates these downloads before preserving or replacing a game
file. Neural-rendering runtime selection remains separate and GPU-aware;
updating SR/RR/FG does not provide a newer neural-rendering model. The listed
versions are the October 14 snapshot. Refreshed mirror DLLs without a bundled
extracted-DLL pin require a freshly verified valid NVIDIA publisher signature;
known exact SHA256 pins can be reused offline.

The October 15 v2.0.1 re-audit adds source-bound and bounded downloads,
preflighted archives, bounded/reaped extractor processes, whole-package
self-update checks, staged config/tuning writes and failure-aware restoration.
Per-game registry changes and global layer references retain recovery evidence
before mutation. Settings, profiles, own-FG recipes and tune histories use the
shared profile mutation lock. Runtime detection distinguishes an actual
upscaling integration from generic backend/frame-generation files.

Reporting now redacts common private values before preparing a GitHub issue
form. Opening that browser URL transmits its prefilled details to GitHub;
publication requires submission. Review remains necessary because arbitrary
free text cannot be guaranteed anonymous. Automatic community-result downloads
remain disabled.

The upstream tests under `tests/` are retained as reference and adapted to portable
source paths. `test_scan.py` and `test_reshade_ini.py` run offline; the large
`test_all.py`, `test_install.py` and `test_clean_machine.py` suites also include
upstream-specific source assertions, downloads, and optional native fixtures and
are not substitutes for actual in-game validation.

Run from source: `python app/dlss5_aio.py`. Build: `python -m PyInstaller app/aio.spec`.
Offline fork tests: `python -m unittest discover -s app/tests -p "test_aio_*.py"`.
Local log: `%LOCALAPPDATA%\dlss5-aio\aio.log`.
Use `--debug` or `DLSS5_AIO_DEBUG=1` to include resolved preferences in the log.
