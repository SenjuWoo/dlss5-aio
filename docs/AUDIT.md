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
