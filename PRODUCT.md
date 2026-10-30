# Product

<!-- impeccable:product-schema 1 -->

> Inferred from the repository and the request; the scoping round was declined, so every line marked (assumed) is unconfirmed.

## Platform

desktop (native Windows, Tk canvas UI; not web, not mobile)

## Users

PC gamers and modders with NVIDIA, AMD or Intel GPUs who keep many games installed and want the upscaling/frame-generation DLLs in each game current, or want a DLSS 5 neural-rendering route installed. They want to see exactly which file changes and be able to put the original back. (assumed: tinkerers who want control, not casual one-click users)

## Product Purpose

One portable game-focused app: discover games, update compatible NVIDIA/AMD/Intel runtime DLLs with verified downloads, install a compatible neural-rendering route, keep originals, and restore them. Success is a user who trusts what it touched, because every change is previewed, backed up and reversible.

## Positioning

Trust and reversibility are the product: verified publisher builds, byte-checked backups, recovery records, and a clear "what will happen?" preview. A neighbouring installer (the upstream Autopilot) is route-first; this app is runtime-maintenance plus recovery-first.

## Operating Context

Windows desktop, long sessions beside games and launchers, often at night in a dim room, mouse and keyboard, 1280x800 up to 4K, DPI scaling. Pages: games library, per-game install page, runtime updates, RTX Remix, VR, settings panel, log drawer, dialogs.

## Capabilities and Constraints

- All behaviour, safety logic, recovery and tests stay untouched; this is a visual and layout overhaul only.
- UI is drawn on a Tk Canvas through `app/core/ui/kit.py` with tokens in `theme.py`; fonts must come from Windows system fonts or a bundled OFL face; no new runtime dependencies.
- Screen capture, video and image-processing workflows stay excluded.
- Online-game and anti-cheat warnings must stay prominent.

## Brand Commitments

- Name: DLSS 5 AIO. Owner: SenjuWoo. MIT licence; upstream MIT credit to DLSS5-Autopilot is retained in docs and licences.
- (assumed) Stay a dark app. Do not resemble the Autopilot look: left icon rail, monospace type, amber-on-black, thin accent bars. Avoid neon, glow and gradient "AI-dark" styling.
- The current double-chevron icon is inherited from upstream and should be replaced.

## Evidence on Hand

Screenshots of the current build in `docs/images/` (fixture games only). No real cover art for fixtures. No user testimonials, benchmarks or performance claims exist; none may be invented.

## Product Principles

1. Show what will change before it changes; make every change visibly reversible.
2. Versions, hashes and file paths are first-class content, not decoration.
3. Quiet by default, loud only for risk (online games, unverified files, failed recovery).
4. One coherent material and type system across every page and dialog.

## Accessibility & Inclusion

Text contrast at least 4.5:1, state never conveyed by colour alone, full keyboard reach for controls, honour Windows DPI scaling.
