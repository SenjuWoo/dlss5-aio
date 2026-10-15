# DLSS 5 AIO recovery state

## Goal
One portable game-focused application: discover games, update compatible NVIDIA/AMD/Intel runtime DLLs, install a compatible DLSS neural-rendering route, preserve settings and originals, and restore changes. Exclude screen/video/image processing. Audit existing refresher and public claims. Deliver source, tests, docs and a verified release.

## Baseline and completed inspection
- Clean checkout of main at `731ff9b`, release v1.4.8. No project AGENTS.md or prior STATE.md found. No user edits observed.
- Existing repository is documentation/component pack plus folder 06 PowerShell refresher; it has no unified application.
- Existing CI runs only `python3 scripts/check_release.py` on Ubuntu; functional Windows tests are missing.
- NVIDIA primary announcement (2026-10-13): https://www.nvidia.com/en-us/geforce/news/dlss-5-faster-ai-model-hogwarts-legacy-rtx-spark-laptops/ . The 2x faster NR model debuts October 16; do not label it available on October 14. Frame Generation Preset C beta is separate.
- Installed DLSS 5 Autopilot identifies upstream `Kizzuwatnaa/DLSS5-Autopilot` (MIT); inspect its reusable game routes before creating replacements.
- .NET SDKs 8.0.418 and 10.0.301 available. PATH's first Python is a broken Windows Store alias; resolve a real interpreter from `where.exe python` instead.
- gh CLI authentication is invalid. Connected GitHub MCP authenticated as SenjuWoo and confirms admin/push permissions; use that route if CLI remains unavailable. Never print credentials.
- Local installed apps, DLL collections and game folders are read-only references. No game or personal settings changed.

## Implementation milestone
- Added `app/`: MIT Autopilot game engine/UI at immutable upstream `f7e347c6493361e30c6609f40be66ee2e77677ce`, game-only AIO identity/version 2.0.0, separate profile/cache/log, strict CLI, no exposed screen/video workflow. Provenance is `app/UPSTREAM.md`.
- Added verified 12-family NVIDIA/AMD/Intel catalog and exact-filename refresh/restore using the existing layered backup engine. AMD split runtimes require the matching loader; unknown ABI/32-bit refresh files are preserved.
- Added reentrant per-game OS write lock; byte recheck catches same-version personal edits during download; staged copies verified by SHA256.
- Reworked legacy folder 06 backup/ledger/staged replacement/rollback/source identity and source-independent restore. Global mutex prevents overlapping legacy console writes. No real game files changed.
- Root README/credits/licenses/changelog/start guide and source/provenance/audit docs updated. Public owner name is SenjuWoo. Legacy numbered-folder material remains a snapshot, not the new portable release.
- Windows CI now runs each test as its own step (no masked earlier native failures), both PowerShell engines, pinned build tool and fresh-package checks. Existing GitHub default CodeQL remains enabled for Python and Actions; no duplicate advanced workflow is added.

## Verified evidence
- `python -m unittest discover -s app/tests -p test_aio_*.py`: 19 passed after final byte-identity and source-placement changes (actual Windows PE VERSIONINFO, filesystem/backup/restore, process/thread locking, strict CLI, namespace and injection-source checks).
- `python -m unittest discover -s app/tests -p test_runtimecatalog.py`: 14 passed. Includes actual version agreement and serialized shared-cache writes. All 12 existing live DLLs passed the final changed validator again using cache only.
- `app/tests/test_scan.py`: 23 passed; `test_reshade_ini.py`: 6 scenarios passed. Logs in the parent work directory.
- `scripts/Test-Refresher.ps1`: 45 functional checks passed on both Windows PowerShell 5.1 and PowerShell 7; final logs `refresher-final-ps51.log` and `refresher-final-ps7.log`. Fixed inherited module-path hash discovery and a false-positive batch oracle.
- `injection-tests.log`: real publisher component downloads installed/removed in isolated x64/x86 fixture folders, including route switching. After latest SR integration, cached-component fixture `injection-latest-tests.log` confirms SR 310.9.16 and FEEDER -> NATIVE -> FEEDER, complete restoration. Header/metadata transports substituted in this final offline fixture; no shader/game execution.
- All 12 current maintenance families downloaded into isolated `work/runtime-live-cache`, source SHA256/size/PE/actual FileVersion verified; all 12 Authenticode signatures Valid. Evidence: parent work `runtime-live-results.json`, `runtime-authenticode.json`, `runtime-live-catalog.json`. Reuse these unchanged downloads.
- Current NVIDIA SR/FG/RR mirror builds 310.9.16; official SDK 310.9.1. Current AMD SDK 2.3.0 and Intel SDK 3.0.2 have distinct per-DLL versions; exact pins in runtimecatalog. AMD/Intel are verified snapshot pins, NVIDIA explicit refresh resolves live verified metadata.

## Build and visual milestone
- Actual native library/runtime pages captured and inspected at 1280x800, using owned fixtures. Images in `docs/images/aio-library.png` and `aio-runtimes.png`; no callback errors. These are UI evidence, not in-game proof.
- Local PyInstaller 6.22.1 build created payload-only EXE/ZIP. `scripts/verify_package.py` passed fresh extraction with spaces, required licenses, version, self-test and invalid-option rejection using only the packaged executable.
- Packaged GUI also launched with isolated settings, produced its native window, captured, closed and exited 0 with no ERROR in its log. Work evidence `frozen-ui.png` and `frozen-ui-profile`; no game changed.
- `scripts/check_release.py`: 14 live external links checked, zero dead; restricted-file and documentation checks passed.
- Root diff review clean after fixing missing Tcl notice fallback (CPython's license includes Tcl/Tk), same-size backup identity, CI exit-code masking and packaged source link.

## Push / CI milestone
- First implementation push: `bdd8cc53be4eaffd07fce5bfc1a1a334d1b909eb`. Link checks and dependency graph passed; Windows CI failed because its disposable fixture was under the protected `D:\a\dlss5-aio` tool-folder parent.
- Corrected test fixture placement to use absolute `RUNNER_TEMP` when available; preserved production tool-folder protection. Simulated runner-temp fixtures passed all 45 checks on both PowerShell engines. Source/runtime downloads unchanged.
- Follow-up `6a53584464f252e576795e657fdcf0808d43d322`: all 45 hosted refresher checks passed, but Actions inherited exit 1 from the intentionally refused concurrent child command. Successful test completion now resets LASTEXITCODE to zero; failure assertions still throw. Verify with Actions' dot-source/exit wrapper, not only `powershell -File`.
- Numbered legacy README files now explicitly label the v1.4.8 manual-pack snapshot.

## Next unfinished step
Push the CI fixture correction, wait for exact-SHA CI/default CodeQL, query all security alerts, download the CI-built artifact and verify it locally, tag/publish from the green SHA, then compare downloaded public asset bytes. No unchanged runtime downloads/tests need repeating.

## Verification and release status
Local build/package and implementation push verified; release pending successful CI. Last known-good is immutable GitHub tag v1.4.8; preserve it. Build: `scripts/Build-Release.ps1 -OutputDir <owned output folder>` (Python/PyInstaller 6.22.1). Run: `python app/dlss5_aio.py`; log `%LOCALAPPDATA%\dlss5-aio\aio.log`, debug via `--debug`/help toggle/`DLSS5_AIO_DEBUG=1`. Use the first non-WindowsApps interpreter from `where.exe python`; sandbox TEMP/TMP must point inside owned work/test-temp for tests.
- Refreshed gh authentication works outside sandbox (`gh api user` -> SenjuWoo); sandbox credential access returns 401. Use approved external credential access. No credentials printed or config overwritten.
- Baseline live security query: Dependabot/code-scanning/secret-scanning all zero open alerts; code quality endpoints return 404 unavailable (left off). Requery after push/CI.

## Scope and limits
Updating a DLL cannot create engine integration. Native runtime refresh and neural injection must remain distinct. API/bitness/runtime availability must determine the route. No claim of universal compatibility or anti-cheat safety without evidence.
