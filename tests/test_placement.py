"""Placement compositor tests: pure Python + Pillow, no KiCad needed."""
import os
import shutil
import unittest

from helpers import IMAGES, OUT, ensure_images

from plugins.color_silkscreen import placement as pl
from plugins.color_silkscreen.board_view import side_geometry
from plugins.color_silkscreen.errors import ColorSilkError

# 50 x 30 mm board with 5 mm chamfers, a 4 x 4 mm cut-out, one pad per face.
OUTLINE = [(5, 0), (45, 0), (50, 5), (50, 25), (45, 30), (5, 30), (0, 25), (0, 5)]
VIEW = {"width": 50.0, "height": 30.0, "origin_mm": (100.0, 80.0), "outlines": [OUTLINE],
        "holes": [[(30, 13), (34, 13), (34, 17), (30, 17)]],
        "pads": {"top": [{"x": 10, "y": 15, "w": 2, "h": 1, "round": False, "drill": 0}],
                 "bottom": [{"x": 10, "y": 15, "w": 2, "h": 1, "round": True, "drill": 0.5}]},
        "footprints": {"top": [{"ref": "R1", "x": 8, "y": 14, "w": 4, "h": 2}], "bottom": []}}
PX = 1200 / 25.4


class PlacementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_images()
        cls.logo = os.path.join(IMAGES, "logo.png")  # 1200 x 720, red top-left, green bottom-right

    def test_fit(self):
        p = pl.fit(VIEW, (1200, 720), 0, "contain")
        self.assertAlmostEqual(p["w"], 50)
        self.assertAlmostEqual(p["h"], 30)
        p = pl.fit(VIEW, (1000, 1000), 0, "cover")
        self.assertAlmostEqual(p["w"], 50)
        p = pl.fit(VIEW, (1000, 500), 90, "contain")  # rotated: 500 x 1000 -> height limited
        self.assertAlmostEqual(p["h"], 30)
        self.assertAlmostEqual(p["w"], 15)

    def test_compose_size_clip_and_hole(self):
        c = pl.compose(VIEW, "top", dict(pl.fit(VIEW, (1200, 720), 0, "cover"), image=self.logo))
        self.assertEqual(c.size, (round(50 * PX), round(30 * PX)))
        a = c.getchannel("A")
        self.assertEqual(a.getpixel((2, 2)), 0)                                   # chamfer: removed
        self.assertEqual(a.getpixel((int(25 * PX), int(2 * PX))), 255)            # inside
        self.assertEqual(a.getpixel((int(32 * PX), int(15 * PX))), 0)             # cut-out: removed

    def test_compose_position_and_bottom_mirror_frame(self):
        p = {"image": self.logo, "cx": 15, "cy": 10, "w": 10, "h": 6, "rot": 0}
        c = pl.compose(VIEW, "top", p)
        a = c.getchannel("A")
        self.assertEqual(a.getpixel((int(15 * PX), int(10 * PX))), 255)
        self.assertEqual(a.getpixel((int(25 * PX), int(10 * PX))), 0)  # outside the placed image
        r, g, b, _ = c.getpixel((int(10.2 * PX), int(7.2 * PX)))     # top-left marker of logo.png
        self.assertGreater(r, 200)
        self.assertLess(g, 60)
        # Bottom: placement is in the bottom view frame; same numbers, same pixels.
        cb = pl.compose(VIEW, "bottom", p)
        self.assertEqual(cb.getpixel((int(10.2 * PX), int(7.2 * PX)))[:3], c.getpixel((int(10.2 * PX), int(7.2 * PX)))[:3])

    def test_rotation_clockwise(self):
        p = {"image": self.logo, "cx": 25, "cy": 15, "w": 12, "h": 20, "rot": 90}
        c = pl.compose(VIEW, "top", p)
        # After a clockwise quarter turn the red (top-left) marker sits top-right.
        r, g, b, _ = c.getpixel((int(30.5 * PX), int(5.5 * PX)))
        self.assertGreater(r, 200)
        self.assertLess(g, 60)

    def test_partly_outside_and_bad_values(self):
        p = {"image": self.logo, "cx": -2, "cy": 15, "w": 20, "h": 12, "rot": 0}
        c = pl.compose(VIEW, "top", p)
        self.assertEqual(c.getchannel("A").getpixel((int(6 * PX), int(15 * PX))), 255)
        with self.assertRaises(ColorSilkError):
            pl.normalize({"image": self.logo, "cx": 0, "cy": 0, "w": 0, "h": 1})
        with self.assertRaises(ColorSilkError):
            pl.normalize({"image": self.logo, "cx": 0, "cy": 0, "w": 1, "h": 1, "rot": 45})
        with self.assertRaises(ColorSilkError) as cm:
            pl.compose(VIEW, "top", {"image": os.path.join(IMAGES, "bad.bmp"), "cx": 1, "cy": 1, "w": 1, "h": 1})
        self.assertEqual(cm.exception.code, "E_IMAGE_FORMAT")

    def test_side_geometry_mirror(self):
        g = side_geometry(VIEW, "bottom")
        self.assertEqual(g["pads"][0]["x"], 40)
        self.assertIn((45, 0), g["outlines"][0])
        self.assertEqual(side_geometry(VIEW, "top")["footprints"][0]["x"], 8)

    def test_silkscreen_as_image(self):
        view = dict(VIEW, silk={"top": [[(20, 5), (24, 5), (24, 9), (20, 9)]], "bottom": []})
        c = pl.compose(view, "top", None, silk={"enabled": True, "color": "#ff0000"})
        self.assertEqual(c.getpixel((int(22 * PX), int(7 * PX))), (255, 0, 0, 255))   # silk, no picture
        self.assertEqual(c.getchannel("A").getpixel((int(30 * PX), int(7 * PX))), 0)   # elsewhere: no ink
        # On top of a picture, the silkscreen wins.
        p = {"image": self.logo, "cx": 25, "cy": 15, "w": 50, "h": 30, "rot": 0}
        c = pl.compose(view, "top", p, silk={"enabled": True, "color": "#00FF00"})
        self.assertEqual(c.getpixel((int(22 * PX), int(7 * PX)))[:3], (0, 255, 0))
        # Bottom face: B.Silkscreen mirrored into the bottom view.
        view_b = dict(VIEW, silk={"top": [], "bottom": [[(20, 5), (24, 5), (24, 9), (20, 9)]]})
        cb = pl.compose(view_b, "bottom", None, silk={"enabled": True, "color": "#0000ff"})
        self.assertEqual(cb.getpixel((int(28 * PX), int(7 * PX))), (0, 0, 255, 255))  # x' = 50 - 22
        self.assertEqual(cb.getchannel("A").getpixel((int(22 * PX), int(7 * PX))), 0)
        # disabled / invalid
        self.assertIsNone(pl.normalize_silk({"enabled": False, "color": "#000000"}))
        with self.assertRaises(ColorSilkError):
            pl.normalize_silk({"enabled": True, "color": "red"})

    def test_offset_and_calibration(self):
        view = dict(VIEW, silk={"top": [[(20, 5), (24, 5), (24, 9), (20, 9)]], "bottom": []})
        c = pl.compose(view, "top", None, silk={"enabled": True, "color": "#ff0000"}, offset=(1.0, -0.5))
        self.assertEqual(c.getpixel((int(24.5 * PX), int(6 * PX)))[:3], (255, 0, 0))   # moved +1 mm in X
        self.assertEqual(c.getchannel("A").getpixel((int(20.5 * PX), int(6 * PX))), 0)
        with self.assertRaises(ColorSilkError):
            pl.normalize_offset((6, 0))
        cal = pl.compose(VIEW, "top", None, calibration=True)
        # crosshair through the pad centre (10, 15): red pixel there
        self.assertEqual(cal.getpixel((int(10 * PX), int(15 * PX)))[:3], (220, 0, 0))
        calb = pl.compose(VIEW, "bottom", None, calibration=True)
        self.assertEqual(calb.getpixel((int(40 * PX), int(15 * PX)))[:3], (220, 0, 0))  # mirrored pad x = 50 - 10

    def test_save_composite_and_json(self):
        out = os.path.join(OUT, "placement_unit")
        shutil.rmtree(out, ignore_errors=True)
        p = {"image": self.logo, "cx": 25, "cy": 15, "w": 50, "h": 30, "rot": 0}
        path, preview = pl.save_composite(pl.compose(VIEW, "top", p), out, "top")
        self.assertTrue(path.endswith(".png") and os.path.exists(preview))
        silk = {"top": None, "bottom": {"enabled": True, "color": "#ABCDEF"}}
        pl.save_placements(os.path.join(out, "p.json"), {"top": p, "bottom": None}, VIEW, silk)
        self.assertEqual(pl.load_placements(os.path.join(out, "p.json")), {"top": p, "bottom": None})
        self.assertEqual(pl.load_silk(os.path.join(out, "p.json")), silk)
        self.assertAlmostEqual(pl.effective_dpi(p, (1200, 720)), 609.6)


if __name__ == "__main__":
    unittest.main()
