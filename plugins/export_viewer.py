"""Export preview window: what the ZIP sent to JLCPCB contains, face by face.

Rebuilt from the files of the ZIP (Gerbers, drills) plus the colour composite
that was encrypted. Layers can be shown or hidden; wheel zooms around the
cursor, drag pans. The pre-flight checks and the warnings of the export are
listed underneath.
"""
import glob
import os

import wx

from .color_silkscreen import export_preview, precheck
from .version import VERSION

LAYER_LABELS = (("image", "Image couleur"), ("silk", "Sérigraphie (Gerber)"), ("copper", "Cuivre nu"),
                ("drills", "Perçages"), ("outline", "Contour"))
PX_PER_MM = 24


def _to_bitmap(img):
    img = img.convert("RGBA")
    w, h = img.size
    wx_img = wx.Image(w, h)
    wx_img.SetData(img.convert("RGB").tobytes())
    wx_img.SetAlpha(img.getchannel("A").tobytes())
    return wx.Bitmap(wx_img)


class PreviewPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetMinSize(wx.Size(640, 640))
        self.bitmap = None
        self.zoom, self.pan, self._drag = 1.0, [0.0, 0.0], None
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_SIZE, lambda e: (self.Refresh(), e.Skip()))
        self.Bind(wx.EVT_MOUSEWHEEL, self.on_wheel)
        self.Bind(wx.EVT_LEFT_DOWN, self.on_down)
        self.Bind(wx.EVT_LEFT_UP, lambda e: setattr(self, "_drag", None))
        self.Bind(wx.EVT_MOTION, self.on_motion)
        self.Bind(wx.EVT_LEFT_DCLICK, lambda e: self.reset_view())

    def set_bitmap(self, bitmap):
        self.bitmap = bitmap
        self.Refresh()

    def reset_view(self):
        self.zoom, self.pan = 1.0, [0.0, 0.0]
        self.Refresh()

    def _fit(self):
        w, h = self.GetClientSize()
        bw, bh = self.bitmap.GetWidth(), self.bitmap.GetHeight()
        k = min(w / bw, h / bh) * self.zoom
        return k, (w - bw * k) / 2 + self.pan[0], (h - bh * k) / 2 + self.pan[1]

    def on_paint(self, _):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(wx.Colour(40, 42, 46)))
        dc.Clear()
        if not self.bitmap:
            return
        gc = wx.GraphicsContext.Create(dc)
        k, ox, oy = self._fit()
        gc.SetInterpolationQuality(wx.INTERPOLATION_GOOD if self.zoom < 4 else wx.INTERPOLATION_NONE)
        gc.DrawBitmap(self.bitmap, ox, oy, self.bitmap.GetWidth() * k, self.bitmap.GetHeight() * k)

    def on_wheel(self, evt):
        if not self.bitmap:
            return
        f = 1.25 if evt.GetWheelRotation() > 0 else 0.8
        new_zoom = min(40.0, max(1.0, self.zoom * f))
        f = new_zoom / self.zoom
        w, h = self.GetClientSize()
        cx, cy = evt.GetX() - w / 2, evt.GetY() - h / 2
        self.pan = [cx - (cx - self.pan[0]) * f, cy - (cy - self.pan[1]) * f]
        self.zoom = new_zoom
        if self.zoom == 1.0:
            self.pan = [0.0, 0.0]
        self.Refresh()

    def on_down(self, evt):
        self._drag = (evt.GetX(), evt.GetY(), list(self.pan))

    def on_motion(self, evt):
        if self._drag and evt.Dragging():
            x, y, pan = self._drag
            self.pan = [pan[0] + evt.GetX() - x, pan[1] + evt.GetY() - y]
            self.Refresh()


class ExportViewer(wx.Frame):
    def __init__(self, zip_path, composites, checks=None, warnings=None):
        super().__init__(None, title="Aperçu de l'export JLCPCB (v{}) — {}".format(VERSION, os.path.basename(zip_path)),
                         size=wx.Size(980, 900))
        self.files = export_preview.read_zip(zip_path)
        self.composites = composites or {}
        self.cache = {}
        self.side = "top"

        self.side_box = wx.RadioBox(self, choices=["Vue de dessus", "Vue de dessous (carte retournée)"])
        self.side_box.Bind(wx.EVT_RADIOBOX, self.on_side)
        layer_row = wx.BoxSizer(wx.HORIZONTAL)
        self.layer_checks = {}
        for key, label in LAYER_LABELS:
            chk = wx.CheckBox(self, label=label)
            chk.SetValue(True)
            chk.Bind(wx.EVT_CHECKBOX, lambda e: self.refresh_image())
            layer_row.Add(chk, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 12)
            self.layer_checks[key] = chk
        hint = wx.StaticText(self, label="Molette : zoom · glisser : déplacer · double-clic : vue entière")
        layer_row.Add(hint, 0, wx.ALIGN_CENTER_VERTICAL)

        self.panel = PreviewPanel(self)
        self.report = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_NO_HEADER, size=wx.Size(-1, 170))
        self.report.InsertColumn(0, "", width=60)
        self.report.InsertColumn(1, "", width=860)
        for c in checks or []:
            i = self.report.InsertItem(self.report.GetItemCount(), "OK" if c["ok"] else ("ERREUR" if c["level"] == "error" else "ATTENTION"))
            self.report.SetItem(i, 1, "{} — {}".format(c["code"], c["message"]))
            if not c["ok"]:
                self.report.SetItemTextColour(i, wx.Colour(200, 30, 30) if c["level"] == "error" else wx.Colour(190, 120, 0))
        for w in warnings or []:
            if w.get("code", "").startswith("I_"):
                continue
            i = self.report.InsertItem(self.report.GetItemCount(), "INFO")
            self.report.SetItem(i, 1, "{} — {}".format(w.get("code"), w.get("message")))
        if not checks:
            i = self.report.InsertItem(0, "—")
            self.report.SetItem(i, 1, "Pas de pré-contrôle disponible pour cet export.")

        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(self.side_box, 0, wx.ALL, 6)
        s.Add(layer_row, 0, wx.LEFT | wx.RIGHT, 6)
        s.Add(self.panel, 1, wx.EXPAND | wx.ALL, 6)
        s.Add(self.report, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        self.SetSizer(s)
        self.refresh_image()

    def layers(self, side):
        if side not in self.cache:
            self.cache[side], _ = export_preview.render_layers(self.files, side, self.composites.get(side), PX_PER_MM)
        return self.cache[side]

    def on_side(self, _):
        self.side = ("top", "bottom")[self.side_box.GetSelection()]
        self.refresh_image()

    def visible(self):
        return ("board",) + tuple(k for k, chk in self.layer_checks.items() if chk.GetValue())

    def rendered(self):
        return export_preview.compose(self.layers(self.side), self.visible())

    def refresh_image(self):
        busy = wx.BusyCursor()
        try:
            self.panel.set_bitmap(_to_bitmap(self.rendered()))
        finally:
            del busy


def show_export_viewer(zip_path, composites, checks=None, warnings=None):
    try:
        frame = ExportViewer(zip_path, composites, checks, warnings)
        frame.Show()
        return frame
    except Exception as e:  # the export itself is done; never fail on the preview
        wx.MessageBox("Aperçu impossible : {}".format(e), "Sérigraphie couleur", wx.OK | wx.ICON_WARNING)
        return None


def open_last_export(production_dir):
    """Open the viewer on the newest ZIP of a production folder (checks re-run, no generation)."""
    zips = sorted(glob.glob(os.path.join(production_dir, "*.zip")), key=os.path.getmtime)
    if not zips:
        wx.MessageBox("Aucun export dans {}.".format(production_dir), "Sérigraphie couleur", wx.OK | wx.ICON_INFORMATION)
        return None
    composites = {s: p for s in ("top", "bottom")
                  for p in [os.path.join(production_dir, "color_{}_composite.png".format(s))] if os.path.exists(p)}
    from PIL import Image
    files = export_preview.read_zip(zips[-1])
    blanked = tuple(s for s, n in (("top", "Gerber_TopSilkscreenLayer.GTO"), ("bottom", "Gerber_BottomSilkscreenLayer.GBO"))
                    if b"printed in the colour image" in files.get(n, b""))
    sides = tuple(s for s, n in (("top", "Fabrication_ColorfulTopSilkscreen.FCTS"),
                                 ("bottom", "Fabrication_ColorfulBottomSilkscreen.FCBS")) if n in files)
    checks = precheck.run(files, os.path.getsize(zips[-1]), sides, blanked,
                          {s: Image.open(p) for s, p in composites.items()})
    return show_export_viewer(zips[-1], composites, checks)
