"""The vr page: DLSS 5 on what the headset shows, and what that needs.

A VR game on OpenXR draws the headset's picture through the OpenXR runtime;
the window on the desktop is a mirror of it. A proxy DLL or the Vulkan layer
reaches that mirror only, so the headset sees nothing (issue #33). ReShade 6
ships an OpenXR API layer, and that layer is the one thing that reaches the
picture the eyes get - registered once per user, not per game.

This page is the whole of that in one place: whether the layer is registered
and by whom, which games in the library carry OpenXR's own loader (the only
hard evidence a game goes through OpenXR at all), what is still unproven,
and the way to take the registration out again. Installing it stays where
installs live - the game's own page, the 'VR headset' box - because it is an
install like any other.

Nobody here has a headset. Every line on this page says what is known and
what is not, and asks for the report that would settle it.
"""
from __future__ import annotations

import threading
import time
import webbrowser

from .. import openxr, prefs
from . import theme as T
from .shell import Page

# What a game that goes through OpenXR carries. The loader is the runtime's
# own DLL: a game that ships it asks OpenXR for the headset.
XR_FILES = ("openxr_loader.dll", "openxr_loader64.dll")

RESHADE_XR = "https://reshade.me/forum/general-discussion/6451-reshade-in-vr"
OUR_DOCS = "https://github.com/SenjuWoo/dlss5-aio/blob/main/docs/vr.md"


class VrPage(Page):
    name = "vr"
    rail = 3

    def __init__(self, shell, app):
        super().__init__(shell)
        self.app = app
        self.found: dict[str, list[str]] | None = None    # game folder -> files found
        self.looking = False

    def shown(self) -> None:
        self._layer_seen = None
        if self.found is None and not self.looking:
            self.look()

    def _layer(self):
        """(manifest or None, is it ours) - cached for this visit."""
        hit = getattr(self, "_layer_seen", None)
        if hit is not None:
            return hit
        where = None
        try:
            where = openxr.existing_registration()
        except Exception:
            where = None
        ours = False
        if where is not None:
            try:
                ours = bool(openxr.is_ours(where))
            except Exception:
                ours = False
        self._layer_seen = (where, ours)
        return self._layer_seen

    def refresh(self) -> int:
        self.shell.redraw()
        return self.shell.content_h

    # ------------------------------------------------------------ the search
    def look(self) -> None:
        """Which games carry OpenXR's loader - a folder walk, so on a worker."""
        self.looking = True
        games = [g for g in (self.app.all_games or []) if getattr(g, "install_dir", None)]

        def work():
            out: dict[str, list[str]] = {}
            end = time.monotonic() + 20.0      # a budget, like every other walk
            for g in games:
                hits: list[str] = []
                try:
                    for name in XR_FILES:
                        # the first hit, not every hit: the slice ran after
                        # the whole tree had been walked, twice per game
                        p = next(g.install_dir.rglob(name), None)
                        if p is not None:
                            hits.append(p.name)
                        if time.monotonic() > end:
                            break
                except OSError:
                    pass
                if time.monotonic() > end:
                    break
                if hits:
                    out[str(g.install_dir)] = sorted(set(hits))
            self.app.q.put(("vrfound", out))
        threading.Thread(target=work, daemon=True).start()

    def got_found(self, out) -> None:
        self.found, self.looking = out, False
        if self.shell.page is self:
            self.shell.redraw()

    # ------------------------------------------------------------ the layer
    def remove_layer(self) -> None:
        where = openxr.existing_registration()
        if where is None:
            self.shell.info("vr", "ReShade's OpenXR layer is not registered for this user, so there is "
                                  "nothing to take out.")
            return
        if not openxr.is_ours(where):
            self.shell.info("vr", f"The registered layer is not one this tool wrote:\n\n{where}\n\n"
                                  f"It came from ReShade's own installer, so it is left alone - remove it "
                                  f"from there.")
            return
        if not self.shell.ask("vr", "Take ReShade's OpenXR layer out of this user's registration? VR games "
                                    "stop loading ReShade, and a DLSS 5 install in a game folder is left "
                                    "as it is.", "remove", "keep", danger=True):
            return
        gone = openxr.unregister()
        self._layer_seen = None
        self.app.write(f"> the OpenXR layer registration was {'removed' if gone else 'not found'}",
                       "ok" if gone else "warn")
        self.shell.status("the OpenXR layer is out" if gone else "nothing to remove")
        self.shell.redraw()

    # ------------------------------------------------------------ drawing
    def draw(self, width: int) -> int:
        a, c, k = self.app, self.c, self.kit
        pad = T.px(44)
        tags = ("page",)
        w = min(width - 2 * pad, T.px(1100))
        c.create_text(pad, T.px(52), text="vr", font=T.display(34), fill=T.TEXT, anchor="w", tags=tags)
        c.create_text(pad + T.px(2), T.px(90),
                      text="dlss 5 on what the headset shows, through reshade's openxr layer",
                      font=T.mono(10), fill=T.MUTED, anchor="w", tags=tags)
        y = T.px(130)

        # --- what is registered right now, read once per visit and after
        # anything that changes it, never on every redraw: it enumerates a
        # registry key and resolves paths, and draw() runs on the Tk thread
        where, ours = self._layer()
        if where is None:
            state, colour, detail = "not registered", T.DIM, (
                "no OpenXR layer is registered for this user. Open a 64-bit game's page, tick "
                "'VR headset (OpenXR layer)' in its settings and install: the layer is registered then.")
        elif ours:
            state, colour, detail = "registered", T.OK, str(where)
        else:
            state, colour, detail = "registered by ReShade itself", T.AMBER, (
                f"{where} - not a file this tool wrote, so it is reused and never changed.")
        y = self._card(pad, y, w, "the openxr layer", state, colour, detail)
        if ours:
            k.button(pad, y, T.width("remove the layer", T.mono(10, True)) + T.px(70), "remove the layer",
                     self.remove_layer, glyph="trash", h=T.px(38), tags=tags, size=10,
                     tip="takes this user's registration out; VR games stop loading ReShade")
            y += T.px(58)

        # --- the games that go through OpenXR at all
        y += T.px(10)
        c.create_text(pad, y, text="games that carry openxr's loader", font=T.mono(9, True), fill=T.MUTED,
                      anchor="w", tags=tags)
        c.create_line(pad + T.width("games that carry openxr's loader", T.mono(9, True)) + T.px(14), y,
                      pad + w, y, fill=T.LINE, tags=tags)
        y += T.px(30)
        if self.found is None:
            c.create_text(pad, y, text="reading the library..." if self.looking else "nothing read yet",
                          font=T.mono(9), fill=T.DIM, anchor="w", tags=tags)
            y += T.px(30)
        elif not self.found:
            c.create_text(pad, y, text=T.fit(
                "none of the games in the library ships openxr_loader.dll. That is not proof a game has no "
                "VR mode - some load the runtime from the system - but it is the only evidence read from "
                "disk, so nothing here is guessed.", T.mono(9), w), font=T.mono(9), fill=T.DIM,
                anchor="w", tags=tags)
            y += T.px(36)
        else:
            for g in (a.all_games or []):
                hits = self.found.get(str(getattr(g, "install_dir", "")))
                if not hits:
                    continue
                tag, wid = k.link(pad, y, T.fit(g.name, T.mono(10), T.px(420)),
                                  lambda gg=g: a.open_game(gg), glyph="game", colour=T.TEXT,
                                  tags=tags, tip="open this game's page, where the VR box is")
                c.create_text(pad + T.px(460), y, text=", ".join(hits), font=T.mono(9), fill=T.DIM,
                              anchor="w", tags=tags)
                y += T.px(30)
            y += T.px(10)

        # --- what is known and what is not
        y += T.px(10)
        y = self._card(pad, y, w, "what is proven", "nothing, in a headset", T.WARN, (
            "The layer registers and the files land where they should - that much runs here. Whether the "
            "feeder, the bridge and the DLSS 5 add-on behave inside an OpenXR swapchain has never been "
            "tried on a headset by the author: there is none on this machine. If you have one, install "
            "with the VR box ticked and share the result - it is the one thing that would settle this, and "
            "it lands in the shared results like every other report."))
        row = [("read reshade's own notes on vr", RESHADE_XR), ("what this page is for", OUR_DOCS)]
        x = pad
        for label, url in row:
            tag, wid = k.link(x, y, label, lambda u=url: webbrowser.open(u), glyph="link", colour=T.AMBER,
                              tags=tags)
            x += wid + T.px(30)
        y += T.px(40)
        return y + T.px(40)

    def _card(self, x, y, w, head, state, colour, detail) -> int:
        """A block: a heading, one word of state in its colour, and the why
        under it over as many rows as it needs. Measured before it is drawn,
        so the background is the right height the first time."""
        c, tags = self.c, ("page",)
        text = " ".join(str(detail).split())
        probe = c.create_text(0, -9999, text=text, font=T.mono(9), anchor="nw", width=w - T.px(40))
        pbox = c.bbox(probe)
        c.delete(probe)
        body = (pbox[3] - pbox[1]) if pbox else T.px(40)
        bottom = y + T.px(52) + body + T.px(18)
        c.create_polygon(T.tag_points(x, y, x + w, bottom, T.px(10)), fill=T.SURF,
                         outline=T.LINE, tags=tags)
        c.create_rectangle(x + T.px(20), y + T.px(20), x + T.px(28), y + T.px(28), fill=colour, outline="", tags=tags)
        c.create_text(x + T.px(40), y + T.px(26), text=head, font=T.mono(10, True), fill=T.TEXT,
                      anchor="w", tags=tags)
        c.create_text(x + T.px(40) + T.width(head, T.mono(10, True)) + T.px(20), y + T.px(26),
                      text=state, font=T.mono(10), fill=colour, anchor="w", tags=tags)
        c.create_text(x + T.px(20), y + T.px(44), text=text, font=T.mono(9), fill=T.MUTED,
                      anchor="nw", width=w - T.px(40), tags=tags)
        return bottom + T.px(16)
