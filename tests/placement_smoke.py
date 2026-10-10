"""Placement editor + compositor smoke test, off-screen (KiCad Python).

    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tests/placement_smoke.py [board.kicad_pcb] [top.png] [bottom.png]

Builds the dialog, simulates move / corner resize / zoom / rotate / numeric
entry, renders both views to out/placement/*.png (no screen capture) and
composes the clipped 1200 DPI images. Exit code 0 when every check passes.
"""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import pcbnew  # type: ignore  # noqa: E402
import wx  # noqa: E402

package = types.ModuleType("plugins")  # skip plugins/__init__.py (action plugin registration)
package.__path__ = [os.path.join(ROOT, "plugins")]
sys.modules["plugins"] = package

from plugins.color_silkscreen import board_view, placement as pl  # noqa: E402
from plugins.placement_dialog import PlacementDialog  # noqa: E402

OUT = os.path.join(ROOT, "out", "placement")


def check(cond, label, failures):
    print(("OK   " if cond else "FAIL ") + label)
    if not cond:
        failures.append(label)


def main():
    board_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "tests", "boards", "T2.kicad_pcb")
    top = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "tests", "img", "logo.png")
    bottom = sys.argv[3] if len(sys.argv) > 3 else os.path.join(ROOT, "tests", "img", "photo.jpg")
    os.makedirs(OUT, exist_ok=True)
    failures = []

    view = board_view.extract(pcbnew.LoadBoard(board_path))
    print("board", view["width"], "x", view["height"], "mm,", len(view["outlines"][0]), "outline points")
    app = wx.App(False)
    # saved corrections must be displayed when the editor opens (bug fixed in 0.3.0)
    reopened = PlacementDialog(None, view, {"top": None, "bottom": None}, None, {"top": None, "bottom": [-0.22, -0.2]})
    shown = {}
    for side in ("top", "bottom"):
        reopened.set_side(side)
        shown[side] = [c.GetValue() for c in reopened.offset_fields]
    check(shown == {"top": ["0.00", "0.00"], "bottom": ["-0.22", "-0.20"]}, "saved corrections displayed on reopen", failures)
    reopened.Destroy()
    dlg = PlacementDialog(None, view, {"top": None, "bottom": None})
    dlg.load_image(top, "top")
    dlg.load_image(bottom, "bottom")
    c = dlg.canvas

    # --- top: move, corner resize (aspect kept), wheel zoom, rotate, numeric entry
    dlg.set_side("top")
    p0 = dict(c.current)
    c.update(cx=p0["cx"] + 5, cy=p0["cy"] - 3)
    check(abs(c.current["cx"] - p0["cx"] - 5) < 1e-9, "move", failures)
    orig = dict(c.current)
    anchor = (orig["cx"] - orig["w"] / 2, orig["cy"] - orig["h"] / 2)
    c.resize_corner("br", orig["cx"] + orig["w"] / 2 + 10, orig["cy"] + orig["h"] / 2 + 1, orig)
    p = c.current
    check(abs((p["cx"] - p["w"] / 2) - anchor[0]) < 1e-9 and abs((p["cy"] - p["h"] / 2) - anchor[1]) < 1e-9,
          "resize keeps the opposite corner", failures)
    check(abs(p["w"] / p["h"] - orig["w"] / orig["h"]) < 1e-9, "resize keeps aspect ratio", failures)
    c.zoom(1 / 1.05 ** 4)
    dlg.action("rotate")
    check(c.current["rot"] == 90, "rotate 90", failures)
    dlg.action("rotate")
    dlg.action("rotate")
    dlg.action("rotate")
    dlg.fields["w"].ChangeValue("30")
    dlg.on_field(None)
    check(abs(c.current["w"] - 30) < 1e-9 and abs(c.current["w"] / c.current["h"] - orig["w"] / orig["h"]) < 1e-6,
          "numeric width keeps aspect", failures)
    dlg.action("center")

    # --- bottom: cover the whole outline
    dlg.set_side("bottom")
    dlg.action("cover")
    check(c.current["w"] >= view["width"] - 1e-6 and c.current["h"] >= view["height"] - 1e-6, "cover fills board", failures)

    for side in ("top", "bottom"):
        dlg.set_side(side)
        c.render_to_bitmap(900, 900).SaveFile(os.path.join(OUT, "editor_{}.png".format(side)), wx.BITMAP_TYPE_PNG)
    # silkscreen toggle: rendering differs when the board has silk on that face
    dlg.set_side("top")
    with_silk = c.render_to_bitmap(300, 300).ConvertToImage().GetData()
    dlg.chk_silk["top"].SetValue(False)
    dlg.on_options(None)
    without = c.render_to_bitmap(300, 300).ConvertToImage().GetData()
    c.render_to_bitmap(900, 900).SaveFile(os.path.join(OUT, "editor_top_nosilk.png"), wx.BITMAP_TYPE_PNG)
    has_silk = bool(view["silk"]["top"])
    print("     silkscreen polygons: top", len(view["silk"]["top"]), "bottom", len(view["silk"]["bottom"]))
    check((with_silk != without) == has_silk, "silkscreen show/hide checkbox", failures)
    dlg.chk_silk["top"].SetValue(True)
    dlg.on_options(None)

    # silkscreen printed in colour on the top face
    dlg.set_side("top")
    dlg.set_silk_print("top", True, "#c0392b")
    c.render_to_bitmap(900, 900).SaveFile(os.path.join(OUT, "editor_top_silkprint.png"), wx.BITMAP_TYPE_PNG)
    silk_result = dlg.result_silk()
    check(silk_result["top"] == {"enabled": True, "color": "#C0392B"} and silk_result["bottom"] is None,
          "silk print result", failures)
    if view["silk"]["top"]:
        canvas = pl.compose(view, "top", None, silk=silk_result["top"])
        colours = canvas.getcolors(maxcolors=1 << 20) or []
        check(any(col[:3] == (0xC0, 0x39, 0x2B) and col[3] == 255 for _, col in colours),
              "silkscreen rendered in the chosen colour", failures)
        with open(os.path.join(OUT, "composite_silk_only_small.png"), "wb") as fh:
            fh.write(pl.preview_bytes(canvas, 900))

    dlg.chk_keep_classic.SetValue(True)
    dlg.on_silk_print()
    check(dlg.result_silk()["top"].get("keep_classic") is True, "keep classic silkscreen option", failures)
    dlg.chk_keep_classic.SetValue(False)
    dlg.on_silk_print()
    dlg.set_side("bottom")
    dlg.offset_fields[0].ChangeValue("-0,3")
    dlg.offset_fields[1].ChangeValue("0.05")
    dlg.on_offset()
    dlg.set_side("top")
    dlg.set_side("bottom")
    check(dlg.result_offsets() == {"top": None, "bottom": [-0.3, 0.05]} and dlg.offset_fields[0].GetValue() == "-0.30",
          "printing correction per face", failures)
    dlg.set_side("top")

    result = dlg.result()
    check(set(result) == {"top", "bottom"} and all(result.values()), "dialog result", failures)
    pl.save_placements(os.path.join(OUT, "placement.json"), result, view)
    check(pl.load_placements(os.path.join(OUT, "placement.json")) == result, "placement json round trip", failures)

    for side in ("top", "bottom"):
        canvas = pl.compose(view, side, result[side])
        exp = (round(view["width"] / 25.4 * 1200), round(view["height"] / 25.4 * 1200))
        check(canvas.size == exp, "{} composite size {} at 1200 DPI".format(side, canvas.size), failures)
        alpha = canvas.getchannel("A")
        corners_cut = (0.0, 0.0) not in [(round(x, 2), round(y, 2)) for x, y in view["outlines"][0]]
        if corners_cut:  # chamfered/rounded board: the bounding-box corners are outside the outline
            check(alpha.getpixel((0, 0)) == 0 and alpha.getpixel((canvas.width - 1, 0)) == 0,
                  "{}: corners outside the outline are transparent".format(side), failures)
        path, png = pl.save_composite(canvas, OUT, side)
        print("     ", side, os.path.basename(path), os.path.getsize(path) // 1024, "KiB")
        with open(os.path.join(OUT, "composite_{}_small.png".format(side)), "wb") as fh:
            fh.write(pl.preview_bytes(canvas, 900))

    dlg.Destroy()
    app.Destroy()
    print("PLACEMENT SMOKE", "OK" if not failures else "FAILED: " + ", ".join(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
