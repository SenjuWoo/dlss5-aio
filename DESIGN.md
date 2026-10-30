# Design system: DLSS 5 AIO

Recorded from the built window (2.1.0). Source of truth in code: `app/core/ui/theme.py` (tokens), `kit.py` (controls), `shell.py` (bar, banners, toasts, dialogs).

## Idea

A conservation record. Each game is an object that is tagged, documented and treated reversibly. The window is the studio: neutral grey floor, paper tags for things that are catalogued, a scale bar under everything that is measured. It refuses the dark-dashboard default of a left icon rail, monospace type and one amber accent.

## Colour

| Role | Token | Value |
| --- | --- | --- |
| Floor | `BG` | `#1b1c1b` |
| Bar | `RAIL` | `#131413` |
| Plate | `SURF` / `SURF2` | `#252725` / `#2f312e` |
| Hairline | `LINE` | `#43463f` |
| Text | `TEXT` / `MUTED` / `DIM` | `#ebe7dc` / `#a9aca3` / `#868a80` |
| Paper (tags, active page, chips) | `PAPER` | `#e8e2d2` |
| Print on paper | `INK` / `INK_SOFT` | `#191a18` / `#58594f` |
| Action (cyanotype) | `AMBER` (name kept for callers) | `#7fb6d6` |
| Good | `OK` | `#8fc49b` |
| Risk (vermilion) | `WARN` | `#f06f52` |
| Vendors | `VENDOR` | NVIDIA `#86b53e`, AMD `#d9704a`, Intel `#5b8fd4` |

One action colour (cyanotype) and one risk colour (vermilion). State is always a swatch plus words, never colour alone. Vendors appear only as small swatches.

## Type

- Interface: Bahnschrift (falls back to Segoe UI Variable, Segoe UI). `T.mono()` is the historical name for this face.
- Labels and button text: Bahnschrift SemiCondensed, upper-case (`T.label`).
- Page titles: Bahnschrift Light 34 pt (`T.display`).
- Hashes, paths and the log: Consolas (`T.data`). Nothing else is monospaced.

## Shapes and material

- Tag: a rectangle with its top-right corner clipped (`T.tag_points`). Buttons, menus, toasts, callouts, record plates and chips all use it; the corner size grows with the object.
- Paper tags hang under a cover plate in the library and carry name, status swatch with words, and bitness.
- Ruler (`Kit.ruler`): a hairline with ticks every 8 px and a longer tick every fifth. Under the top bar, under the library filters (the active filter is a cyan block on the bar), along the foot of each cover plate, and in dialogs. Three canvas items per ruler.
- No shadows, no gradients, no glow. Depth comes from paper against grey and from 1px hairlines.
- No coloured edge bars on cards, callouts or banners; urgency is outline colour or a swatch.

## Layout

- Top bar 64 px: mark and name, pages set on the ruler (active page is a paper tag), watch and help right-aligned.
- Pages: 44 px side padding, a light 34 pt title, one muted line under it, content below.
- Library: 176 x 264 plates in a fluid grid, 62 px tag under each. Runtimes: one plate per game as a ledger of components (vendor swatch, component, current build, arrow, new build) with the update button at the right.

## Controls

- Primary: cyanotype fill, ink text. Secondary: `SURF2` fill, 1px `LINE` outline. Danger: vermilion. Disabled: `SURF`, dim text.
- Field: recessed `SURF` with a 1px outline that turns cyanotype on focus. Slider cursor: a narrow upright bar. Dropdown: outline turns cyanotype when changed.
- Menus drop from the control that opened them, clipped corner, hover is `LINE`.

## Icon

A pixel-built 5 in paper on a dark rounded tile with a hairline edge; one pixel (top right) is cyanotype, the one that "resolved" (`docs/images/logo.svg`, `app/dlss5-aio.ico`, `app/core/icon_png.py`).

## Not covered

The settings panel (checked open on a game page) and the compare and report dialogs inherit these tokens and controls and were not individually recomposed; compare/report were not rendered. The game page's hero-art layout (a game with a real backdrop) was restyled in place and not rendered here, because the fixtures have no art.
