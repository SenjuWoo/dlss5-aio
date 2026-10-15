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
- Initial gh CLI credential was invalid; later refreshed and verified as SenjuWoo outside the sandbox. No credentials printed or personal Git settings changed.
- Local installed apps, DLL collections and game folders are read-only references. No game or personal settings changed.

## Implementation milestone
- Added `app/`: MIT Autopilot game engine/UI at immutable upstream `f7e347c6493361e30c6609f40be66ee2e77677ce`, game-only AIO identity/version 2.0.0, separate profile/cache/log, strict CLI, no exposed screen/video workflow. Provenance is `app/UPSTREAM.md`.
- Added verified 12-family NVIDIA/AMD/Intel catalog and exact-filename refresh/restore using the existing layered backup engine. AMD split runtimes require the matching loader; unknown ABI/32-bit refresh files are preserved.
- Added reentrant per-game OS write lock; byte recheck catches same-version personal edits during download; staged copies verified by SHA256.
- Reworked legacy folder 06 backup/ledger/staged replacement/rollback/source identity and source-independent restore. Global mutex prevents overlapping legacy console writes. No real game files changed.
- Root README/credits/licenses/changelog/start guide and source/provenance/audit docs updated. Public owner name is SenjuWoo. Legacy numbered-folder material remains a snapshot, not the new portable release.
- Windows CI now runs each test as its own step (no masked earlier native failures), both PowerShell engines, pinned build tool and fresh-package checks. Existing GitHub default CodeQL remains enabled for Python and Actions; no duplicate advanced workflow is added.

## Verified evidence
- `python -m unittest discover -s app/tests -p test_aio_*.py`: 20 passed after final byte-identity, source-placement and hostname fixes (actual Windows PE VERSIONINFO, filesystem/backup/restore, process/thread locking, strict CLI, namespace and injection-source checks).
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
Push the frozen v2.0.1 audit fixes/docs, converge exact-SHA CI/security, download and retest that CI artifact, then publish and independently verify public bytes. Baseline is `bd4752e66f361fc0ad77f5bbf003f6423941dfde`. Local source/build/native gates passed below. v2.0.0 tags/assets remain unchanged, but its release notes warn about the reproduced recovery defects. No real games/profiles have been changed. Reuse immutable component downloads.

## Whole-project re-audit implementation
- No personal edits present at the start; no game or user settings will be changed by audit fixtures.
- Read-only review work is split across three agents with disjoint scopes; findings require a concrete trigger and evidence before fixes. Evidence/repros belong in parent work/audit-v2.
- Existing release/source/security proof below remains valid for v2.0.0. Do not claim universal perfection or new in-game FPS/visual proof from static review and fixtures.
- Reproduced installer backup-failure overwrite, later-edit loss, untracked-file/host64 deletion, manifest path escape, failed-restore record deletion and partial-copy loss. Recovery now uses verified staged writes, intended hashes/checkpoints, conservative ownership and retained records; independent tune/registry/legacy review completed.
- Reproduced source-confused cache, stale unpack cache, update ZIP payload checksum gap, daemon-write shutdown, profile RMW race and generic-Streamline/native-upscaler false detection. Fixes and regression suites passed the final combined run.
- Root checks passed: 13 runtime/recovery tests (including real NTFS hard-link and nested game locks; hard-link fixture requires external sandbox access), 17 runtime catalog tests (including real Windows unsigned-signature boundary and signed component-family checks), 8 component-writer tests, GPU-journal tests. Actual cached signed NVIDIA DLL passed the new Windows publisher reader as Valid/NVIDIA Corporation. Legacy refresher has 46 functional checks passing on both PowerShell 5.1 and 7, after reproducing missing-target restore failure.
- Native source App/Tk deferred-close lifecycle passed with a real fixture worker and isolated settings (`work/audit-v2/product-native-lifecycle.json`). Final frozen-source cached x64/x86 installs, FEEDER -> NATIVE -> FEEDER and restoration passed (`injection-frozen-source.log`).
- Independent final reports: parent work/audit-v2/recovery-final.md (42 recovery tests), network-final.md (22 network/archive/self-update/privacy tests and native 7-Zip/batch/child boundaries), product-final.md (42 product tests, emulator formats and native Tk lifecycle/PNG exports). Integration caught option-off ownership re-adoption; all removed names now leave written/hash/prior collections together before a checkpoint. Two root boundary counterexamples were independently refused after fixing signed wrong-family NVIDIA builds and a GPU-choice race between reads.

## v2.0.1 frozen-source local gates
- Combined AIO: 142 passed (`combined-aio-final.log`); catalog: 17 passed (`catalog-final.log`); scanner: 23 passed; ReShade INI: 6 scenarios passed. Compileall app/scripts and diff check passed. Legacy refresher: 46 functional checks on each PowerShell engine, unchanged production code after those checks except the version string.
- Final cached publisher-component fixture passed x64/x86 install, route switching and full restoration without new downloads. Original fixture EXEs and persistent AIO locks were the only remaining files; shader execution and registry transports are substituted.
- Actual native report/share forms captured and visually inspected after correcting an occluded initial capture: content fits, submit gating works, cancel opens no browser, zero callback errors (`product-native-report.json`). Native comparison exports preserve concurrent PNGs and correct decoded pixels.
- Local PyInstaller 6.22.1 build/package passed fresh extraction, licenses/payload boundaries, real EXE version/self-test/invalid CLI (`build-local.log`). Extracted native 2.0.1 GUI opened, was captured/inspected, closed and exited zero with no ERROR log (`local-native-gui.log`). Local candidate is parent work/audit-v2/local-build; release will use the exact green CI artifact instead.
- Release checker: 15 external links checked, zero dead; restricted-file and docs checks passed. New audit/recovery/source docs reviewed. No v2.0.1 release is published yet; CI/security/public bytes remain unfinished.

## CodeQL fix milestone
- Both production HTTP readers now classify GitHub rate limits using the exact parsed hostname. Regression covers 24 reader/status/URL combinations including suffix, path, query and credential spoofing.
- Three inherited reference-test oracles now inspect actual error behavior and exact host tokens rather than loose domain substrings. All seven changed-oracle checks passed.
- Final application suite is now 20 passing tests; syntax and git diff checks passed. No alert was dismissed. The earlier 011cfcdd artifacts are superseded candidates and must not be published after these source changes.

## CI artifact milestone
- Candidate source: `011cfcdd912ea07abe71d1e764dcb5407710a533`. CI run `38671370899` and default CodeQL run `38671370379` both terminal success; all four check runs green. Post-scan query found five open `py/incomplete-url-substring-sanitization` findings: production `app/core/net.py:608`, `app/core/sources.py:348`; upstream reference tests `app/tests/test_all.py:8156,9290,9648`. These classify GitHub rate-limit errors via a substring rather than parsed hostname. Fixing all before release; no alert dismissed. Dependabot and secret-scanning remain zero; code quality unavailable 404.
- Downloaded CI artifact `11943603467` (`DLSS5-AIO-win-x64`) from that exact source SHA. Retested fresh extraction and real packaged version/self-test/invalid CLI locally; launched/captured/closed its native GUI with exit 0 and no ERROR log. PE product/owner/version metadata correct.
- Those initial candidate bytes were superseded by the hostname fix. Do not publish the old local or 011cfcdd build.
- Release notes originated in parent work/release-notes.txt. Copy-paste platform changelog is in outputs/CHANGELOG-PUBLISH.txt. Publication and public proof completed below.

## Corrected CI artifact milestone
- Pushed `8178e0ac45f03d7fc3a279583aaf397f8587c4f2`; CI run `38673144602` and CodeQL run `38673144499` terminal success. All four exact-SHA checks passed. All five findings closed through code fixes; no alert dismissed. Post-scan Dependabot, code-scanning and secret-scanning open-alert queries all returned zero. Code quality remains unavailable (404), left off.
- Downloaded CI artifact `11944856876` from that exact SHA. Fresh ZIP extraction, packaged version/self-test/invalid CLI passed locally. Its native GUI opened, was captured/inspected, closed and exited zero with no ERROR log, using isolated settings.
- Promoted unchanged verified bytes to outputs: EXE 13,582,294 bytes SHA256 `afbc0cf4e2a717630a94da76bd06b25e83d9423d8aac334455cc6d775bdd37b5`; ZIP 13,372,627 bytes SHA256 `d2e6927e244ab2c4c3e53804bdb286b892e1cb71105017e6a17e0c3b8656d8dd`. Both match CI SHA256SUMS.

## Publication proof
- Published https://github.com/SenjuWoo/dlss5-aio/releases/tag/v2.0.0 on October 15, 2026. Non-draft, non-prerelease, latest. Tag resolves exactly to green source `8178e0ac45f03d7fc3a279583aaf397f8587c4f2`.
- Downloaded all three public assets without authentication into fresh parent work/public-v2.0.0-8178e0a. Nonempty sizes and SHA256 match the verified CI files exactly. Proof: parent work/public-v2.0.0-proof.json. Checksum asset is 177 bytes, SHA256 `e79c7a5c70560b4711eec29fca658bc609bcdc7f5098ff8a04413bd3b2e31240`.
- Outputs/HANDOFF.md contains the release/source/check links, hashes, log location and exact remaining runtime limits. Outputs/CHANGELOG-PUBLISH.txt contains the ready-to-paste v1.4.8 -> v2.0.0 changelog. Final documentation-only commit does not change the released application bytes.

## Verification and release status
v2.0.0 source, exact-SHA CI/security, native/package checks, publication and public bytes are verified. Immutable GitHub tag v1.4.8 remains the prior rollback baseline. Build: `scripts/Build-Release.ps1 -OutputDir <owned output folder>` (Python/PyInstaller 6.22.1). Run: `python app/dlss5_aio.py`; log `%LOCALAPPDATA%\dlss5-aio\aio.log`, debug via `--debug`/help toggle/`DLSS5_AIO_DEBUG=1`. Use the first non-WindowsApps interpreter from `where.exe python`; sandbox TEMP/TMP must point inside owned work/test-temp for tests.
- Refreshed gh authentication works outside sandbox (`gh api user` -> SenjuWoo); sandbox credential access returns 401. Use approved external credential access. No credentials printed or config overwritten.
- Baseline live security query: Dependabot/code-scanning/secret-scanning all zero open alerts; code quality endpoints return 404 unavailable (left off). Requery after push/CI.

## Scope and limits
Updating a DLL cannot create engine integration. Native runtime refresh and neural injection must remain distinct. API/bitness/runtime availability must determine the route. No claim of universal compatibility or anti-cheat safety without evidence.
- No new actual-game visual/FPS benchmark, Vulkan/OpenXR/VR session, or full legacy pack binary audit. Large upstream reference suite is retained, not a completed release gate. Application EXE is unsigned. AMD/Intel are verified dated pins; incompatible/static FSR and unknown/32-bit maintenance DLLs are preserved.
