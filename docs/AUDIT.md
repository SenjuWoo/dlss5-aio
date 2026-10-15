# Audit and implementation record

Baseline: main `731ff9b` / v1.4.8. Inspected repository source, release checks, supplied local app documentation and current upstream sources. The old release payload is a separate artifact; source inspection does not establish the identity or runtime behavior of every binary in that archive.

## Findings addressed

| Finding | Result |
| --- | --- |
| AIO required installing separate tools and manually assembling no-DLSS/32-bit routes. | Portable application reuses the MIT Autopilot game engine at its recorded immutable commit. Game discovery, executable analysis, preview, route-specific install, diagnostics and removal share one interface. |
| Refresher could continue after a backup failed and falsely report success. | Terminating file errors, verified original/ledger, staged replacement, rollback, failure exit status and functional failure tests. |
| Restore required finding the original pack, despite claims that backups were independent. | Restore uses local verified records and backups without resolving pack binaries. |
| Source selection trusted loose filenames and ambiguous Streamline directories. | Refresher verifies exact pack manifest entries and chooses sources deterministically; the new app records publisher provenance and verifies runtime downloads. |
| Refresher could traverse backups, protected reference trees and reparse points unnecessarily. | Protected subtree pruning; no junction recursion or rewriting another tool's restore copies. |
| No unified AMD/Intel maintenance. | Exact filename families share the existing updater's backup/restore engine. Different AMD API layouts remain separate; missing integration/dependencies are reported. |
| Version-only recheck could miss personal edits during a download. | Byte hash recheck before replacement; staged copies also verified by hash. |
| Concurrent AIO CLI/GUI mutations could overlap. | Shared per-game operating-system lock for install/remove/update/restore. |
| Root README claimed any-game compatibility and anti-cheat safety. | Removed. Renderer, architecture, GPU, runtime availability and game behavior constrain support. |
| October performance announcement could be mistaken for a released NR DLL. | NVIDIA's October 13 announcement says the faster NR model debuts October 16. The available FG performance beta is a separate feature. |
| Existing CI checked links and restricted filenames only. | Add actual Windows application/refresher tests and packaged executable checks. |
| Upstream profile, updater and reporting identity could overwrite another installed app. | Separate AIO profile/cache/log/mutex and repository identity. Automatic upstream community reads/sharing disabled. In-game installer record names stay compatible for recovery. |

## Reuse and comparison

- [DLSS 5 Autopilot](https://github.com/Kizzuwatnaa/DLSS5-Autopilot): MIT game discovery, eight route families, preview, backup/rollback, runtime log diagnosis, CLI and portable packaging. Reused rather than independently reimplemented. Exact commit and license are in `app/UPSTREAM.md` and `app/UPSTREAM-LICENSE.txt`.
- [DLSS Swapper](https://github.com/beeradmoore/dlss-swapper): reference for runtime inventory across vendors. Its update manifest is useful evidence; this app preserves exact publisher filenames and independently verified source identities.
- DLSS5-Swapper installed documentation points to `rakanki911/DLSS5-Swapper`; the public repository returned 404 during inspection. No unavailable implementation was invented or copied from the installed executable.
- [DLSS5 Manager](https://github.com/smartLanny/DLSS5-Manager-ZJZ): open manager shell; native neural implementation availability is separate. No private implementation is assumed.
- NeuralScreen and Visual Enhancer are outside the requested game workflows. Their installed settings and files were not changed.

## Compatibility boundaries

Runtime refresh updates existing compatible Windows x64 DLLs. It cannot upgrade statically linked FSR, invent missing engine integrations, convert an incompatible ABI, or turn a DLL swap into neural rendering. Unsupported filenames and missing dependencies remain explicit gaps.

Neural-rendering installation chooses among native NGX, upstream, OptiScaler, RenoDX, bridge, feeder/helper, standalone and existing RTX Remix routes. A route's installation success is not proof that the model evaluated frames. Use **did it work?** after a real game session. Original Saints Row: The Third's 32-bit DX11 executable and an actual DX9 game require different proxy/translation decisions. Never put an x64 proxy into an x86 executable directory.

Runtime DLL changes are not inherently anti-cheat safe. Running games and detected anti-cheat installations are held by default; bulk updates exclude them. Existing third-party tools do not share AIO's new write lock: close other mod managers before changing the same game.

## Evidence retained separately

`STATE.md` records commands, test/build results, release identity and exact remaining gaps. `docs/RUNTIME-SOURCES.md` records current publisher versions, immutable sources and the NR release-date distinction. No new in-game performance, visual quality or universal compatibility claim is made from fixture tests.

## Whole-project re-audit: October 15, 2026 / v2.0.1

The second audit started from clean `bd4752e` after v2.0.0 publication. It reviewed the game installer and removal paths, multivendor maintenance, component installers, transport and archives, self-update, discovery and route decisions, CLI/UI state, reports/privacy, settings/profiles, emulator settings, tuning, legacy PowerShell refresher, tests, build configuration and documentation. The original version/source research above remains dated evidence; unchanged publisher archives and signature results were reused. Actual games, installed reference applications and personal settings were not modified by the audit fixtures.

| Area | Confirmed failure and resulting change |
| --- | --- |
| Recovery and reinstall | A failed backup could be followed by replacement; later edits and unowned helper files could be deleted; incomplete removal could discard its journal. Staged verified copies and checkpoints now precede mutation, hashes record byte ownership, later edits survive separately, and failed restoration retains incomplete recovery records. Missing recorded originals block replacement. Reinstall retains the first original, sidelined-file references and original Remix option. |
| Option-off cleanup | Own-FG/MFG cleanup could restore an original while leaving it marked as app-owned, allowing later uninstall to delete it. Restored paths are removed from every ownership collection before the next durable checkpoint. Unknown originals are retained rather than silently adopted. |
| Windows settings and layers | A graphics preference could change before its recovery entry existed; an outside-game manifest record could target another program's preference. Candidates are journaled first, paths are constrained to the game, later user choices are rechecked, and restore failures keep the record. OpenXR/Vulkan reference transitions use the shared profile lock and retain references when unregister fails. |
| Configuration and tuning | Direct writes and swallowed errors could commit partial configuration or hide a failed tune. Merges run against verified isolated snapshots, refuse concurrent changes, and commit complete output through the journal boundary. Tuning validates the recorded route/ownership and updates the UI only after success. Vanished payloads report incomplete installation without guessing their cause or recommending blanket antivirus exclusions. |
| Download/cache trust | A fixed cache name could reuse another URL's bytes and overlapping jobs could share partial files. Exact source binding, shared cache locks, bounded responses, validated partial ranges and staged complete cache entries now protect this boundary. Failed refresh retains the preceding complete download. |
| Archive/component trust | Cached OptiScaler extraction could ignore changed archive bytes; unsafe external archive listings could reach extraction. Archive digests and extracted identities govern reuse; ZIP/7z inspection rejects unsafe paths, links, duplicate/ambiguous entries and excessive expansion. Extractor output/time limits terminate and reap owned children. Component placement uses the shared recovery writer. |
| Self-update | An executable-only checksum accepted a modified packaged runtime directory. Both the whole ZIP and executable must match unambiguous checksums. Native Windows batch tests verify failure rollback and paths containing Unicode, percent, exclamation and ampersand characters. |
| Runtime catalog and ABI | New mirror hashes alone did not establish a publisher or runtime family. Unpinned refreshed NVIDIA candidates now require fresh valid NVIDIA Authenticode verification and matching family metadata, format and FileVersion; exact audited DLL pins work offline. Runtime transfers use the exact expected size limit. AMD loader/effect dependencies and combined/split layouts remain distinct. |
| Discovery, CLI and UI | Streamline/FG/backend-only files could be mistaken for an upscaling integration. Detection now requires the relevant runtime evidence. Unsupported checks return nonzero; recovery works after executable removal and bypasses new-install GPU/API gates. Post-dialog busy checks and worker-close deferral prevent overlapping actions. Comparison exports use unused names and cancel pending callbacks on close. |
| Settings and local recipes | Concurrent profile saves, recipe copies and tune histories could overwrite another writer's work. Shared process locks, staged atomic replacements and refusal of unreadable/newer settings preserve complete state. Profile-name aliases are refused. Malformed and nonfinite tune data is ignored. |
| Emulator settings | Direct backend writes/restoration could overwrite later unrelated settings or use unproven backups. An adjacent byte record precedes staged writes. Restore merges only the original backend setting when appropriate and retains later choices, unverified originals and failures for review. |
| Report privacy | Prepared reports could expose common local identities and credentials, and the disclosure obscured when the browser transmits data. Shared serialization redacts common paths, email/IP addresses, credential fields and URL secrets. Review failure cannot fall through to a browser call. Opening the prefilled issue URL sends details to GitHub; publication still requires submitting it. Arbitrary prose is not guaranteed anonymous. |
| Legacy refresher | A verified backup could not restore a missing target DLL; restore now stages and atomically creates it. Re-audited backup/ledger, source identity, failure exits, pruning and locking. AMD split-loader requirements remain enforced. The console path remains separate from app-specific restoration records. |

### Recorded validation

- Combined `test_aio_*.py` suite: **142 passed**; runtime catalog: **17 passed**; scanner: **23 passed**; ReShade configuration: **6 scenarios passed**.
- Legacy refresher: **46 functional checks passed on both Windows PowerShell 5.1 and PowerShell 7**.
- Recovery suite: **42 passed**, including a real child-process crash immediately after file replacement and durable registry recovery before a simulated post-write crash. Product suite: **42 passed**, including restored own-FG original ownership, concurrent profiles/histories and six emulator config formats.
- Network suite: **22 passed**, including actual installed 7-Zip archive creation/listing/extraction, native batch rollback, pre-write streaming limits and bounded child-process cleanup. An independent adversarial fixture refused a genuinely signed wrong-family NVIDIA DLL and preserved a personal graphics-preference change between reads.
- Cached publisher x64/x86 components installed with SR 310.9.16, switched FEEDER -> NATIVE -> FEEDER, and restored completely in disposable game folders. Only the original fixture executable and AIO lock remained. Discovery/header/registry transports were substituted; shaders were not executed.
- Native Tk fixtures verified worker-close deferral and comparison PNG pixel/dimension/export/callback behavior. The expanded report/share disclosures were rendered, captured and visually inspected with all content fitting; cancellation opened no browser and produced no callback errors. Compilation of application/scripts and `git diff --check` passed. The exact CI, packaged-native, release and public-byte proof is recorded in `STATE.md`; source tests alone do not establish those later gates.

### Recovery and runtime limits

New hashes cannot certify historical bytes retroactively. With an older hashless install record, ordinary unproven files are preserved. A recorded legacy backup may be restored while its backup is retained and uninstall remains incomplete for review. Historical emulator and ASI-loader backups without the required identity record are refused for automatic restoration. Later personal emulator backend choices are also retained and reported as incomplete recovery. These outcomes preserve evidence; they do not imply the historical files were corrupted.

AIO's game/profile/cache locks coordinate its own processes. Other managers, emulators and game updaters do not honor them. Byte rechecks catch changes during staging but cannot prevent a foreign writer acting after a completed operation. Close those applications while modifying the same files.

No new actual-game FPS/visual benchmark, Vulkan/OpenXR/VR session, full-drive performance test, full legacy binary-pack audit or complete large upstream reference-suite result is claimed. The application remains unsigned. AMD/Intel remain dated snapshot pins, and static/incompatible integrations remain outside DLL maintenance coverage. The retained historical Saints Row evaluation log and native UI fixtures are not fresh game-rendering proof.
