"""Colours, type, glyphs and scale for the whole window - one place.

The look is a conservation record: objects photographed on a neutral studio
grey, each carrying a warm paper tag, measured against a ruler. Every screen
and dialog takes its look from here, so a colour changed once changes
everywhere and no dialog drifts into a look of its own.
"""
from __future__ import annotations

import tkinter.font as tkfont

BG = "#1b1c1b"          # the studio floor: neutral grey, a hair warm
RAIL = "#131413"        # the ruler bar across the top
SURF = "#252725"        # fields, rows, plates
SURF2 = "#2f312e"       # buttons, menus, a raised surface
LINE = "#43463f"        # hairlines, hover on SURF2
TEXT = "#ebe7dc"        # paper white
MUTED = "#a9aca3"
DIM = "#868a80"
AMBER = "#7fb6d6"       # cyanotype blue: the one action colour (name kept for callers)
PAPER = "#e8e2d2"       # accession-tag stock
INK = "#191a18"         # print on the paper
INK_SOFT = "#58594f"    # secondary print on the paper
OK = "#8fc49b"          # calibration green
WARN = "#f06f52"        # vermilion: risk, and only risk
LOG_BG = "#101110"

# Vendor identity is a colour-checker patch, never a logo.
VENDOR = {"nvidia": ("#86b53e", "N"), "amd": ("#d9704a", "A"), "intel": ("#5b8fd4", "I")}

UI_FAMILIES = ("Bahnschrift", "Segoe UI Variable Text", "Segoe UI")
COND_FAMILIES = ("Bahnschrift SemiCondensed", "Bahnschrift", "Segoe UI Semibold", "Segoe UI")
DATA_FAMILIES = ("Consolas", "Cascadia Mono", "Courier New")
MONO_FAMILIES = DATA_FAMILIES      # older callers
ICON_FAMILIES = ("Segoe Fluent Icons", "Segoe MDL2 Assets", "Segoe UI Symbol")

# Segoe MDL2 Assets / Fluent Icons code points (the same in both)
GLYPH = {
    "search": "", "scan": "", "gear": "", "play": "",
    "check": "", "cross": "", "game": "", "video": "",
    "remix": "", "help": "", "eye": "", "down": "",
    "up": "", "back": "", "folder": "", "trash": "",
    "compare": "", "people": "", "pilot": "",
    "close": "", "add": "", "warn": "", "info": "",
    "bug": "", "copy": "", "download": "", "link": "",
    "hide": "", "more": "", "refresh": "", "save": "",
    "camera": "", "headset": "", "screen": "", "file": "", "update": "", "chip": "",
}

SCALE = 1.0             # pixels per 96-DPI pixel, set once at start


def set_scale(dpi: float) -> None:
    global SCALE
    SCALE = max(1.0, dpi / 96.0)


def px(n: float) -> int:
    """A layout length in pixels at the current scale."""
    return max(1, round(n * SCALE))


_families: dict[str, str] = {}


def _first_available(names: tuple[str, ...]) -> str:
    key = names[0]
    if key not in _families:
        have = set(tkfont.families())
        _families[key] = next((n for n in names if n in have), names[-1])
    return _families[key]


def mono(size: int = 10, bold: bool = False) -> tuple:
    """The interface face (DIN-style). Sizes are points, which Tk scales with
    the display on its own. Named `mono` for the callers that predate the
    redesign; only `data` is monospaced now."""
    return (_first_available(UI_FAMILIES), size, "bold" if bold else "normal")


ui = mono


def label(size: int = 9) -> tuple:
    """Semi-condensed face for tag lines and small caps-style labels."""
    return (_first_available(COND_FAMILIES), size, "normal")


def display(size: int = 30) -> tuple:
    """Large headings: the light cut, so a page title reads as lettering."""
    fam = _first_available(UI_FAMILIES)
    return ((fam + " Light") if fam == "Bahnschrift" and "Bahnschrift Light" in set(tkfont.families()) else fam,
            size, "normal")


def data(size: int = 10, bold: bool = False) -> tuple:
    """Hashes, paths and anything that must line up character by character."""
    return (_first_available(DATA_FAMILIES), size, "bold" if bold else "normal")


def icons(size: int = 12) -> tuple:
    return (_first_available(ICON_FAMILIES), size)


_measure: dict[tuple, tkfont.Font] = {}


def width(text: str, font: tuple) -> int:
    import tkinter as _tk
    key = (font, id(_tk._default_root))
    f = _measure.get(key)
    if f is None:
        f = _measure[key] = tkfont.Font(font=font)
    return f.measure(text)


def fit(text: str, font: tuple, room: int) -> str:
    """The text, cut with an ellipsis where it would not fit in `room` px."""
    if width(text, font) <= room:
        return text
    while text and width(text + "…", font) > room:
        text = text[:-1]
    return text.rstrip() + "…"


def tag_points(x1, y1, x2, y2, cut=None):
    """Polygon for a paper tag: a rectangle with its top-right corner clipped."""
    cut = px(8) if cut is None else cut
    return (x1, y1, x2 - cut, y1, x2, y1 + cut, x2, y2, x1, y2)


API_NAMES = {"DX8": "DirectX 8", "DX9": "DirectX 9", "DX10": "DirectX 10", "DX11": "DirectX 11",
             "DX12": "DirectX 12", "OPENGL": "OpenGL", "VULKAN": "Vulkan"}


def api_name(api: str | None) -> str:
    return API_NAMES.get(str(api or "").upper().replace(" ", ""), str(api or "?"))
