# Changelog

## 2.1.0 - 2026-10-30
- New visual identity, replacing the look inherited from Autopilot: a conservation-record design. Neutral studio-grey ground, paper accession tags for games and chips, a scale-bar ruler for navigation and filters, vendor swatches (NVIDIA, AMD, Intel) in the runtime ledger, DIN-style Bahnschrift type, tag-shaped clipped-corner buttons, cyanotype blue as the single action colour and vermilion for risk only.
- Navigation moves from the left icon rail to a top bar with the pages set on the ruler; the log, help and watch controls keep their places on the right and bottom.
- Library, runtime updates, game, remix and VR pages recomposed; covers missing from a game show a lettered specimen plate instead of a controller icon. The page tint that followed the hovered cover is gone.
- New application icon and logo. Behaviour, safety logic, recovery and tests are unchanged.

## 2.0.2 - 2026-10-29
- Ship a one-folder build (`DLSS5-AIO.exe` + `_internal`) instead of a self-extracting single file. The 2.0.1 single-file EXE was blocked by Microsoft Defender (`Trojan:Win32/Suschil!rfn` on the ZIP, `Wacatac.B!ml`/`Contebrew.A!ml` on the EXE); these were false positives from the packed-executable layout. The one-folder build scans clean. No standalone EXE asset is published any more.
- Fix self-update on current Windows builds: the swap helper is now launched as `.\swap.bat` because `cmd /c <bare name>` no longer resolves from the working directory.
- Build script works from a virtual environment and Python versions without bundled Tcl/Tk notices (official Tcl/Tk license texts are vendored in `app/`).

## 2.0.1 - 2026-10-15
- Fix installer backup failures, interrupted writes and recovery records; preserve later personal edits and unowned files during reinstall, removal and optional-component changes.
- Constrain all recovery paths to the game and retain originals/records when recovery fails. Legacy records without byte ownership require conservative recovery.
- Bind caches to source URLs and archive digests, serialize cache/profile mutations, bound transfers and validate archive entries before extraction.
- Verify the entire self-update package and preserve rollback files when native replacement fails. Require a valid NVIDIA publisher signature for new unpinned mirror runtimes.
- Prevent shutdown or overlapping modal actions from terminating active writers; fix CLI recovery gates and unsupported check exit status.
- Correct native-upscaler detection, preserve preferences/configuration, redact issue-report details, and restore missing DLLs in the legacy refresher.
- Add failure-injection, concurrency, native Windows and component recovery checks from the whole-project re-audit.

## 2.0.0 - 2026-10-14
- Add a portable game-focused application with game discovery, renderer/architecture detection, installation previews, neural-rendering routes, diagnostics and removal.
- Combine compatible NVIDIA, AMD FidelityFX and Intel XeSS runtime maintenance in one page, with verified downloads and originals retained.
- Reuse the MIT-licensed DLSS 5 Autopilot game engine; isolate AIO settings and omit screen/video workflows.
- Add cross-process game write locking and detect same-version file changes during downloads.
- Fix the legacy refresher's backup, replacement and restore failure handling; validate pack sources and protect later personal edits.
- Replace universal compatibility and anti-cheat-safe claims with explicit support boundaries.
- Record the October 16 faster neural-rendering model as upcoming, separate from October 13 Frame Generation beta.

## 1.4.8
- Original manual component pack and PowerShell DLL refresher. Its release and archive hashes remain available for rollback.
