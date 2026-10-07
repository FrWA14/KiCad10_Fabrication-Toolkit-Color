"""Visual editor: place and resize the colour images on the top and bottom faces.

Mouse: drag the image to move it, drag a corner handle to resize (aspect kept
unless "Proportions libres" is ticked or Shift is held), wheel to zoom the
image around the cursor. Arrow keys nudge by 0.1 mm (Shift: 1 mm).
The board is drawn as JLCPCB will make it: white solder mask, gold bare
copper (no ink there) and the components of that face as grey boxes.
"""
import os

import wx

from .color_silkscreen import placement as pl
from .version import VERSION
from .color_silkscreen.board_view import side_geometry, view_x

HANDLE_PX = 7
SIDE_LABELS = ("Vue de dessus", "Vue de dessous (carte retournée)")
SIDES = ("top", "bottom")
IMAGE_WILDCARD = "Images PNG/JPG (*.png;*.jpg;*.jpeg)|*.png;*.jpg;*.jpeg"


class PlacementCanvas(wx.Panel):
    def __init__(self, parent, view, placements, on_change):
        super().__init__(parent, style=wx.WANTS_CHARS)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetMinSize(wx.Size(560, 520))
        self.view = view
        self.side = "top"
        self.placements = placements          # side -> placement dict or None
        self.silk_print = {"top": None, "bottom": None}  # side -> {"enabled", "color"} or None
        self.on_change = on_change
        self.opacity = 0.85
        self.clip_preview = True
        self.show_components = True
        self.show_silk = {"top": True, "bottom": True}   # F.Silkscreen / B.Silkscreen
        self.free_ratio = False
        self._images = {}                     # path -> wx.Image (preview resolution)
        self._bitmaps = {}                    # (path, rot, opacity) -> wx.Bitmap
        self._drag = None
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_SIZE, lambda e: (self.Refresh(), e.Skip()))
        self.Bind(wx.EVT_LEFT_DOWN, self.on_down)
        self.Bind(wx.EVT_LEFT_UP, self.on_up)
        self.Bind(wx.EVT_MOTION, self.on_motion)
        self.Bind(wx.EVT_MOUSEWHEEL, self.on_wheel)
        self.Bind(wx.EVT_KEY_DOWN, self.on_key)

    # ------------------------------------------------------------------ geometry
    @property
    def current(self):
        return self.placements.get(self.side)

    def transform(self, size=None):
        w, h = size or self.GetClientSize()
        margin = 24
        k = min((w - 2 * margin) / self.view["width"], (h - 2 * margin) / self.view["height"])
        k = max(k, 0.01)
        ox = (w - self.view["width"] * k) / 2
        oy = (h - self.view["height"] * k) / 2
        return k, ox, oy

    def to_px(self, x, y, t=None):
        k, ox, oy = t or self.transform()
        return ox + x * k, oy + y * k

    def to_mm(self, px, py):
        k, ox, oy = self.transform()
        return (px - ox) / k, (py - oy) / k

    def image_rect_px(self, t=None):
        p = self.current
        x0, y0 = self.to_px(p["cx"] - p["w"] / 2, p["cy"] - p["h"] / 2, t)
        x1, y1 = self.to_px(p["cx"] + p["w"] / 2, p["cy"] + p["h"] / 2, t)
        return x0, y0, x1, y1

    def source_image(self, path):
        if path not in self._images:
            img = wx.Image(path) if os.path.isfile(path) else wx.Image()
            if img.IsOk():
                self._images[path] = (img, (img.GetWidth(), img.GetHeight()))
            else:
                self._images[path] = (None, (1, 1))
        return self._images[path][0]

    def source_size(self, path):
        self.source_image(path)
        return self._images[path][1]

    def bitmap(self, p):
        key = (p["image"], p["rot"], round(self.opacity, 2))
        if key not in self._bitmaps:
            img = self.source_image(p["image"])
            if img is None:
                return None
            img = img.Copy()
            longest = max(img.GetWidth(), img.GetHeight())
            if longest > 1600:  # preview resolution only; export uses the full file
                f = 1600 / longest
                img.Rescale(max(1, int(img.GetWidth() * f)), max(1, int(img.GetHeight() * f)), wx.IMAGE_QUALITY_HIGH)
            for _ in range(p["rot"] // 90):
                img = img.Rotate90(True)
            if not img.HasAlpha():
                img.InitAlpha()
            img = img.AdjustChannels(1.0, 1.0, 1.0, self.opacity)
            self._bitmaps[key] = wx.Bitmap(img)
        return self._bitmaps[key]

    # ------------------------------------------------------------------ drawing
    def on_paint(self, _):
        dc = wx.AutoBufferedPaintDC(self)
        gc = wx.GraphicsContext.Create(dc)
        self.draw(gc, self.GetClientSize())

    def render_to_bitmap(self, w, h):
        """Off-screen render (tests / previews), never touches the screen."""
        bmp = wx.Bitmap(w, h)
        dc = wx.MemoryDC(bmp)
        gc = wx.GraphicsContext.Create(dc)
        self.draw(gc, wx.Size(w, h))
        del gc
        dc.SelectObject(wx.NullBitmap)
        return bmp

    def _outline_path(self, gc, geo, t):
        path = gc.CreatePath()
        for chain in geo["outlines"] + geo["holes"]:
            pts = [self.to_px(x, y, t) for x, y in chain]
            path.MoveToPoint(*pts[0])
            for q in pts[1:]:
                path.AddLineToPoint(*q)
            path.CloseSubpath()
        return path

    def draw(self, gc, size):
        t = self.transform(size)
        k = t[0]
        geo = side_geometry(self.view, self.side)
        gc.SetBrush(wx.Brush(wx.Colour(52, 56, 64)))
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.DrawRectangle(0, 0, size[0], size[1])

        board = self._outline_path(gc, geo, t)
        gc.SetBrush(wx.Brush(wx.Colour(250, 250, 248)))
        gc.FillPath(board, wx.ODDEVEN_RULE)

        p = self.current
        if p:
            bmp = self.bitmap(p)
            x0, y0, x1, y1 = self.image_rect_px(t)
            if bmp:
                if self.clip_preview:
                    gc.PushState()
                    gc.Clip(wx.Region([wx.Point(int(round(x)), int(round(y)))
                                       for x, y in (self.to_px(a, b, t) for a, b in geo["outlines"][0])]))
                gc.DrawBitmap(bmp, x0, y0, x1 - x0, y1 - y0)
                if self.clip_preview:
                    gc.PopState()

        # silkscreen: this face in black on the white mask (above the colour image),
        # the other face as a faint grey "see-through" like KiCad's back layers
        other = "bottom" if self.side == "top" else "top"
        printed = self.silk_print.get(self.side)
        own = wx.Colour(printed["color"]) if printed else wx.Colour(20, 20, 20)
        for layer_side, colour in ((other, wx.Colour(120, 120, 130, 70)), (self.side, own)):
            chains = self.view.get("silk", {}).get(layer_side, [])
            # printed silkscreen is part of the colour image: always shown, in its colour
            visible = self.show_silk[layer_side] or (layer_side == self.side and printed)
            if not visible or not chains:
                continue
            silk = gc.CreatePath()
            for chain in chains:
                pts = [self.to_px(view_x(self.view, self.side, x), y, t) for x, y in chain]
                silk.MoveToPoint(*pts[0])
                for q in pts[1:]:
                    silk.AddLineToPoint(*q)
                silk.CloseSubpath()
            gc.SetPen(wx.TRANSPARENT_PEN)
            gc.SetBrush(wx.Brush(colour))
            gc.FillPath(silk, wx.WINDING_RULE)

        # bare copper of this face (no ink is printed there)
        gc.SetBrush(wx.Brush(wx.Colour(214, 172, 70)))
        gc.SetPen(wx.Pen(wx.Colour(150, 110, 30), 1))
        for pad in geo["pads"]:
            cx, cy = self.to_px(pad["x"], pad["y"], t)
            w, h = pad["w"] * k, pad["h"] * k
            if pad["round"]:
                gc.DrawEllipse(cx - w / 2, cy - h / 2, w, h)
            else:
                gc.DrawRoundedRectangle(cx - w / 2, cy - h / 2, w, h, min(w, h) * 0.2)
            if pad["drill"]:
                d = pad["drill"] * k
                gc.SetBrush(wx.Brush(wx.Colour(30, 32, 36)))
                gc.DrawEllipse(cx - d / 2, cy - d / 2, d, d)
                gc.SetBrush(wx.Brush(wx.Colour(214, 172, 70)))

        if self.show_components:
            gc.SetBrush(wx.Brush(wx.Colour(90, 90, 100, 60)))
            gc.SetPen(wx.Pen(wx.Colour(90, 90, 100, 160), 1))
            gc.SetFont(wx.Font(wx.FontInfo(7)), wx.Colour(60, 60, 70))
            for fp in geo["footprints"]:
                x, y = self.to_px(fp["x"], fp["y"], t)
                gc.DrawRectangle(x, y, fp["w"] * k, fp["h"] * k)
                if fp["w"] * k > 18:
                    gc.DrawText(fp["ref"], x + 2, y + 1)

        gc.SetBrush(wx.TRANSPARENT_BRUSH)
        gc.SetPen(wx.Pen(wx.Colour(0, 150, 60), 2))
        gc.StrokePath(board)

        if p:
            x0, y0, x1, y1 = self.image_rect_px(t)
            pen = wx.Pen(wx.Colour(40, 120, 255), 1, wx.PENSTYLE_SHORT_DASH)
            gc.SetPen(pen)
            gc.DrawRectangle(x0, y0, x1 - x0, y1 - y0)
            gc.SetPen(wx.Pen(wx.Colour(40, 120, 255), 1))
            gc.SetBrush(wx.Brush(wx.WHITE))
            for hx, hy in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
                gc.DrawRectangle(hx - HANDLE_PX / 2, hy - HANDLE_PX / 2, HANDLE_PX, HANDLE_PX)
        else:
            gc.SetFont(wx.Font(wx.FontInfo(11)), wx.Colour(120, 120, 120))
            label = "Aucune image sur cette face : « Charger une image… »"
            tw, th = gc.GetTextExtent(label)
            gc.DrawText(label, (size[0] - tw) / 2, (size[1] - th) / 2)

        gc.SetFont(wx.Font(wx.FontInfo(9).Bold()), wx.Colour(235, 235, 235))
        gc.DrawText(SIDE_LABELS[SIDES.index(self.side)] + "  —  {:.2f} x {:.2f} mm".format(
            self.view["width"], self.view["height"]), 8, 4)

    # ------------------------------------------------------------------ interaction
    def hit(self, px, py):
        if not self.current:
            return None
        x0, y0, x1, y1 = self.image_rect_px()
        for name, (hx, hy) in (("tl", (x0, y0)), ("tr", (x1, y0)), ("bl", (x0, y1)), ("br", (x1, y1))):
            if abs(px - hx) <= HANDLE_PX and abs(py - hy) <= HANDLE_PX:
                return name
        if x0 <= px <= x1 and y0 <= py <= y1:
            return "move"
        return None

    def on_down(self, evt):
        self.SetFocus()
        mode = self.hit(evt.GetX(), evt.GetY())
        if mode:
            self._drag = (mode, self.to_mm(evt.GetX(), evt.GetY()), dict(self.current))
            self.CaptureMouse()

    def on_up(self, _):
        if self._drag:
            self._drag = None
            if self.HasCapture():
                self.ReleaseMouse()

    def on_motion(self, evt):
        if not self._drag:
            mode = self.hit(evt.GetX(), evt.GetY())
            self.SetCursor(wx.Cursor({"move": wx.CURSOR_SIZING, "tl": wx.CURSOR_SIZENWSE, "br": wx.CURSOR_SIZENWSE,
                                      "tr": wx.CURSOR_SIZENESW, "bl": wx.CURSOR_SIZENESW}.get(mode, wx.CURSOR_ARROW)))
            return
        mode, start, orig = self._drag
        mx, my = self.to_mm(evt.GetX(), evt.GetY())
        if mode == "move":
            self.update(cx=orig["cx"] + mx - start[0], cy=orig["cy"] + my - start[1])
        else:
            self.resize_corner(mode, mx, my, orig, free=self.free_ratio or evt.ShiftDown())

    def resize_corner(self, corner, mx, my, orig, free=False):
        """Drag `corner` to (mx, my) mm; the opposite corner stays put."""
        ax = orig["cx"] + orig["w"] / 2 * (1 if "l" in corner else -1)
        ay = orig["cy"] + orig["h"] / 2 * (1 if "t" in corner else -1)
        w, h = max(abs(mx - ax), 0.5), max(abs(my - ay), 0.5)
        if not free:
            k = max(w / orig["w"], h / orig["h"])
            w, h = orig["w"] * k, orig["h"] * k
        sx = -1 if "l" in corner else 1
        sy = -1 if "t" in corner else 1
        self.update(cx=ax + sx * w / 2, cy=ay + sy * h / 2, w=w, h=h)

    def on_wheel(self, evt):
        if not self.current:
            return
        f = 1.05 if evt.GetWheelRotation() > 0 else 1 / 1.05
        self.zoom(f, self.to_mm(evt.GetX(), evt.GetY()))

    def zoom(self, f, around=None):
        p = self.current
        ax, ay = around or (p["cx"], p["cy"])
        self.update(cx=ax + (p["cx"] - ax) * f, cy=ay + (p["cy"] - ay) * f, w=p["w"] * f, h=p["h"] * f)

    def on_key(self, evt):
        step = 1.0 if evt.ShiftDown() else 0.1
        moves = {wx.WXK_LEFT: (-step, 0), wx.WXK_RIGHT: (step, 0), wx.WXK_UP: (0, -step), wx.WXK_DOWN: (0, step)}
        if self.current and evt.GetKeyCode() in moves:
            dx, dy = moves[evt.GetKeyCode()]
            self.update(cx=self.current["cx"] + dx, cy=self.current["cy"] + dy)
        else:
            evt.Skip()

    def update(self, **fields):
        self.current.update(fields)
        self.Refresh()
        self.on_change()


class PlacementDialog(wx.Dialog):
    def __init__(self, parent, view, placements, silk=None, offsets=None):
        super().__init__(parent, title="Sérigraphie couleur — placement des images (v{})".format(VERSION),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.view = view
        self.placements = {s: (dict(placements[s]) if placements.get(s) else None) for s in SIDES}

        self.side_box = wx.RadioBox(self, choices=list(SIDE_LABELS), style=wx.RA_SPECIFY_COLS)
        self.canvas = PlacementCanvas(self, view, self.placements, self.sync_fields)
        self.silk_print = {side: (dict(silk[side]) if silk and silk.get(side) else {"enabled": False, "color": "#000000"})
                           for side in SIDES}
        self.offsets = {side: list(pl.normalize_offset((offsets or {}).get(side))) for side in SIDES}

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.btn = {}
        for key, label, tip in (("load", "Charger une image…", "PNG ou JPG pour cette face"),
                                ("remove", "Retirer", "Pas d'impression couleur sur cette face"),
                                ("contain", "Contenir", "Image entière dans le contour"),
                                ("cover", "Couvrir", "Remplit tout le contour (rogne l'image)"),
                                ("center", "Centrer", "Centre l'image sur la carte"),
                                ("rotate", "Rotation 90°", "Tourne l'image d'un quart de tour (sens horaire)")):
            b = wx.Button(self, label=label)
            b.SetToolTip(tip)
            b.Bind(wx.EVT_BUTTON, lambda e, k=key: self.action(k))
            buttons.Add(b, 0, wx.RIGHT, 4)
            self.btn[key] = b

        self.fields = {}
        values = wx.BoxSizer(wx.HORIZONTAL)
        for key, label in (("cx", "Centre X"), ("cy", "Centre Y"), ("w", "Largeur"), ("h", "Hauteur")):
            values.Add(wx.StaticText(self, label=label + " (mm)"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 3)
            ctrl = wx.TextCtrl(self, size=wx.Size(70, -1), style=wx.TE_PROCESS_ENTER)
            ctrl.Bind(wx.EVT_TEXT_ENTER, self.on_field)
            ctrl.Bind(wx.EVT_KILL_FOCUS, lambda e: (self.on_field(e), e.Skip()))
            values.Add(ctrl, 0, wx.RIGHT, 10)
            self.fields[key] = ctrl
        self.dpi_label = wx.StaticText(self, label="")
        values.Add(self.dpi_label, 0, wx.ALIGN_CENTER_VERTICAL)

        opts = wx.BoxSizer(wx.HORIZONTAL)
        self.chk_free = wx.CheckBox(self, label="Proportions libres")
        self.chk_clip = wx.CheckBox(self, label="Aperçu découpé au contour")
        self.chk_clip.SetValue(True)
        self.chk_fp = wx.CheckBox(self, label="Afficher les composants")
        self.chk_fp.SetValue(True)
        printing = wx.BoxSizer(wx.HORIZONTAL)
        self.chk_print_silk = wx.CheckBox(self, label="Imprimer la sérigraphie de cette face dans l'image couleur")
        self.chk_print_silk.SetToolTip("En sérigraphie couleur (PCB blanc, ENIG), la sérigraphie blanche classique n'est pas "
                                       "imprimée : cette option la dessine dans l'image, dans la couleur choisie.")
        self.silk_colour = wx.ColourPickerCtrl(self, colour=wx.Colour(0, 0, 0))
        self.silk_colour.SetToolTip("Couleur de la sérigraphie imprimée")
        printing.Add(self.chk_print_silk, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        printing.Add(wx.StaticText(self, label="Couleur :"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        printing.Add(self.silk_colour, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 16)
        printing.Add(wx.StaticText(self, label="Correction d'impression X / Y (mm) :"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        self.offset_fields = []
        for _ in range(2):
            ctrl = wx.TextCtrl(self, size=wx.Size(55, -1), style=wx.TE_PROCESS_ENTER)
            ctrl.SetToolTip("Décale toute l'impression couleur de cette face pour compenser un écart mesuré avec la mire "
                            "de calage (vue de la face, X vers la droite, Y vers le bas). L'aperçu reste à la position voulue.")
            ctrl.Bind(wx.EVT_TEXT_ENTER, self.on_offset)
            ctrl.Bind(wx.EVT_KILL_FOCUS, lambda e: (self.on_offset(e), e.Skip()))
            printing.Add(ctrl, 0, wx.RIGHT, 4)
            self.offset_fields.append(ctrl)
        self.chk_print_silk.Bind(wx.EVT_CHECKBOX, self.on_silk_print)
        self.silk_colour.Bind(wx.EVT_COLOURPICKER_CHANGED, self.on_silk_print)

        layers = wx.BoxSizer(wx.HORIZONTAL)
        layers.Add(wx.StaticText(self, label="Sérigraphie :"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.chk_silk = {}
        for side, label, tip in (("top", "F.Silkscreen", "Sérigraphie du dessus : noire en vue de dessus, grisée en vue de dessous"),
                                 ("bottom", "B.Silkscreen", "Sérigraphie du dessous : noire en vue de dessous, grisée en vue de dessus")):
            chk = wx.CheckBox(self, label=label)
            chk.SetValue(True)
            chk.SetToolTip(tip)
            chk.Bind(wx.EVT_CHECKBOX, self.on_options)
            layers.Add(chk, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 12)
            self.chk_silk[side] = chk
        n_silk = {s: len(view.get("silk", {}).get(s, [])) for s in SIDES}
        layers.Add(wx.StaticText(self, label="({} forme(s) dessus, {} dessous)".format(n_silk["top"], n_silk["bottom"])),
                   0, wx.ALIGN_CENTER_VERTICAL)
        self.opacity = wx.Slider(self, value=85, minValue=20, maxValue=100, size=wx.Size(120, -1))
        self.opacity.SetToolTip("Opacité de l'aperçu (export toujours à 100 %)")
        for c in (self.chk_free, self.chk_clip, self.chk_fp):
            opts.Add(c, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 12)
            c.Bind(wx.EVT_CHECKBOX, self.on_options)
        opts.Add(wx.StaticText(self, label="Opacité"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        opts.Add(self.opacity, 0)
        self.opacity.Bind(wx.EVT_SLIDER, self.on_options)

        hint = wx.StaticText(self, label="Glisser : déplacer · coins : redimensionner (Maj : libre) · molette : zoom · "
                                         "flèches : 0,1 mm. Doré = cuivre nu, sans encre. Ce qui dépasse du contour "
                                         "Edge.Cuts est retiré à l'export.")
        hint.Wrap(760)
        ok = wx.Button(self, wx.ID_OK, "Valider")
        cancel = wx.Button(self, wx.ID_CANCEL, "Annuler")
        bottom = wx.StdDialogButtonSizer()
        bottom.AddButton(ok)
        bottom.AddButton(cancel)
        bottom.Realize()

        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(self.side_box, 0, wx.ALL, 6)
        s.Add(buttons, 0, wx.LEFT | wx.RIGHT, 6)
        s.Add(self.canvas, 1, wx.EXPAND | wx.ALL, 6)
        s.Add(values, 0, wx.LEFT | wx.RIGHT, 6)
        s.Add(opts, 0, wx.ALL, 6)
        s.Add(layers, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        s.Add(printing, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        s.Add(hint, 0, wx.LEFT | wx.RIGHT, 6)
        s.Add(bottom, 0, wx.ALL | wx.ALIGN_RIGHT, 6)
        self.SetSizerAndFit(s)
        self.SetSize(wx.Size(820, 860))
        self.side_box.Bind(wx.EVT_RADIOBOX, self.on_side)
        self.set_side("top")

    # ------------------------------------------------------------------ actions
    def on_silk_print(self, _=None):
        state = self.silk_print[self.canvas.side]
        state["enabled"] = self.chk_print_silk.GetValue()
        state["color"] = self.silk_colour.GetColour().GetAsString(wx.C2S_HTML_SYNTAX)
        self.silk_colour.Enable(state["enabled"])
        self.show_offset()
        self.canvas.silk_print = {s: (v if v["enabled"] else None) for s, v in self.silk_print.items()}
        self.canvas.Refresh()

    def on_offset(self, _=None):
        try:
            values = [float(c.GetValue().replace(",", ".") or 0) for c in self.offset_fields]
            self.offsets[self.canvas.side] = list(pl.normalize_offset(values))
        except (ValueError, pl.ColorSilkError):
            pass
        self.show_offset()

    def show_offset(self):
        for ctrl, v in zip(self.offset_fields, self.offsets[self.canvas.side]):
            ctrl.ChangeValue("{:.2f}".format(v))

    def set_silk_print(self, side, enabled, color="#000000"):
        self.silk_print[side] = {"enabled": bool(enabled), "color": color}
        if side == self.canvas.side:
            self.chk_print_silk.SetValue(bool(enabled))
            self.silk_colour.SetColour(wx.Colour(color))
        self.canvas.silk_print = {s: (v if v["enabled"] else None) for s, v in self.silk_print.items()}
        self.canvas.Refresh()

    def set_side(self, side):
        self.side_box.SetSelection(SIDES.index(side))
        self.canvas.side = side
        state = self.silk_print[side]
        self.chk_print_silk.SetLabel("Imprimer la sérigraphie {} dans l'image couleur".format(
            "F.Silkscreen" if side == "top" else "B.Silkscreen"))
        self.chk_print_silk.SetValue(state["enabled"])
        self.silk_colour.SetColour(wx.Colour(state["color"]))
        self.silk_colour.Enable(state["enabled"])
        self.canvas.silk_print = {s: (v if v["enabled"] else None) for s, v in self.silk_print.items()}
        self.canvas.Refresh()
        self.sync_fields()

    def on_side(self, _):
        self.set_side(SIDES[self.side_box.GetSelection()])

    def load_image(self, path, side=None):
        side = side or self.canvas.side
        img = wx.Image(path)
        if not img.IsOk():
            wx.MessageBox("Image illisible : " + path, "Sérigraphie couleur", wx.OK | wx.ICON_ERROR)
            return
        px = (img.GetWidth(), img.GetHeight())
        self.placements[side] = dict(pl.fit(self.view, px, 0, "contain"), image=path)
        self.canvas.Refresh()
        self.sync_fields()

    def action(self, key):
        p = self.canvas.current
        if key == "load":
            with wx.FileDialog(self, "Image couleur", wildcard=IMAGE_WILDCARD,
                               style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dlg:
                if dlg.ShowModal() == wx.ID_OK:
                    self.load_image(dlg.GetPath())
            return
        if not p:
            return
        if key == "remove":
            self.placements[self.canvas.side] = None
        elif key in ("contain", "cover"):
            p.update(pl.fit(self.view, self.canvas.source_size(p["image"]), p["rot"], key))
        elif key == "center":
            p.update(cx=self.view["width"] / 2, cy=self.view["height"] / 2)
        elif key == "rotate":
            p.update(rot=(p["rot"] + 90) % 360, w=p["h"], h=p["w"])
        self.canvas.Refresh()
        self.sync_fields()

    def on_options(self, _):
        self.canvas.free_ratio = self.chk_free.GetValue()
        self.canvas.clip_preview = self.chk_clip.GetValue()
        self.canvas.show_components = self.chk_fp.GetValue()
        self.canvas.show_silk = {side: chk.GetValue() for side, chk in self.chk_silk.items()}
        self.canvas.opacity = self.opacity.GetValue() / 100.0
        self.canvas.Refresh()

    def on_field(self, _):
        p = self.canvas.current
        if not p:
            return
        try:
            vals = {k: float(c.GetValue().replace(",", ".")) for k, c in self.fields.items()}
        except ValueError:
            self.sync_fields()
            return
        if vals["w"] <= 0 or vals["h"] <= 0:
            self.sync_fields()
            return
        if not self.chk_free.GetValue():
            if abs(vals["w"] - p["w"]) > 1e-6:
                vals["h"] = p["h"] * vals["w"] / p["w"]
            elif abs(vals["h"] - p["h"]) > 1e-6:
                vals["w"] = p["w"] * vals["h"] / p["h"]
        p.update(vals)
        self.canvas.Refresh()
        self.sync_fields()

    def sync_fields(self):
        p = self.canvas.current
        for k, c in self.fields.items():
            c.Enable(bool(p))
            c.ChangeValue("{:.2f}".format(p[k]) if p else "")
        for k in ("remove", "contain", "cover", "center", "rotate"):
            self.btn[k].Enable(bool(p))
        if p:
            dpi = pl.effective_dpi(p, self.canvas.source_size(p["image"]))
            self.dpi_label.SetLabel("{} — {:.0f} DPI{}".format(
                os.path.basename(p["image"]), dpi, "  (faible : viser 300+)" if dpi < 150 else ""))
            self.dpi_label.SetForegroundColour(wx.Colour(200, 40, 40) if dpi < 150 else wx.Colour(30, 120, 40))
        else:
            self.dpi_label.SetLabel("")

    def result_offsets(self):
        return {s: (list(v) if any(v) else None) for s, v in self.offsets.items()}

    def result_silk(self):
        return {s: (pl.normalize_silk(v) if v["enabled"] else None) for s, v in self.silk_print.items()}

    def result(self):
        return {s: (pl.normalize(self.placements[s]) if self.placements[s] else None) for s in SIDES}
