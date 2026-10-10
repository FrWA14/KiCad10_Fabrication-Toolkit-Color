"""Pre-flight checks and JLCPCB-style preview of an export (no KiCad needed)."""
import os
import re
import shutil
import unittest
import zipfile

from helpers import FIXTURES, IMAGES, OUT, ensure_images

from plugins.color_silkscreen import export_preview, precheck
from plugins.color_silkscreen.generate import Options, generate_color_silkscreen
from plugins.color_silkscreen.report import Report

T2 = os.path.join(FIXTURES, "T2_gerbers")


class PreviewAndPrecheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_images()
        work = os.path.join(OUT, "precheck_T2")
        shutil.rmtree(work, ignore_errors=True)
        shutil.copytree(T2, work)
        generate_color_silkscreen(work, os.path.join(IMAGES, "logo.png"), None, Report(),
                                  Options(blank_silk_sides=("top",)))
        cls.zip = shutil.make_archive(work, "zip", work)
        cls.files = export_preview.read_zip(cls.zip)

    def codes(self, results):
        return {r["code"]: r["ok"] for r in results}

    def test_good_export_passes(self):
        res = precheck.run(self.files, os.path.getsize(self.zip), ("top",), ("top",))
        self.assertTrue(all(r["ok"] for r in res), [r for r in res if not r["ok"]])

    def test_detects_past_failures(self):
        files = dict(self.files)
        # 0.2.8 regression: blanked silkscreen without any aperture (no fingerprint)
        files["Gerber_TopSilkscreenLayer.GTO"] = b"G04 EasyEDA Pro v3.2.148, x*\n%FSLAX46Y46*%\n%MOMM*%\nM02*\n"
        self.assertFalse(self.codes(precheck.run(files, None, ("top",), ("top",)))["P_SILK_TOP"])
        # "outdated" version markers
        files = {n: (re.sub(rb"EasyEDA Pro v3\.2\.148", b"EasyEDA Pro v2.2.42.2", d) if n.startswith("Gerber_") else d)
                 for n, d in self.files.items()}
        self.assertFalse(self.codes(precheck.run(files, None, ("top",)))["P_VERSION"])
        # tampered Gerber: fingerprint no longer matches
        files = dict(self.files)
        files["Gerber_TopLayer.GTL"] = self.files["Gerber_TopLayer.GTL"].replace(b"M02*", b"G04 x*\nM02*")
        self.assertFalse(self.codes(precheck.run(files, None, ("top",)))["P_FINGERPRINT"])
        # colour file missing
        files = {n: d for n, d in self.files.items() if not n.endswith(".FCTS")}
        self.assertFalse(self.codes(precheck.run(files, None, ("top",)))["P_COLOR_TOP"])

    def test_excellon_parser(self):
        holes = export_preview.parse_excellon(self.files["Drill_PTH_Through.DRL"].decode())
        self.assertIn((116.0, -95.0, 116.0, -95.0, 0.4), holes)
        slot = export_preview.parse_excellon("M48\nMETRIC\nT1C0.800\n%\nT1\nX1.0Y2.0G85X3.0Y2.0\nM30\n")
        self.assertEqual(slot, [(1.0, 2.0, 3.0, 2.0, 0.8)])

    def test_preview_layers(self):
        from PIL import Image
        comp = Image.new("RGBA", (500, 300), (255, 0, 0, 255))
        layers, bounds = export_preview.render_layers(self.files, "top", comp, px_per_mm=10)
        self.assertEqual(layers["board"].size, (500, 300))
        k = 10
        def px(x, y):  # gerber mm -> top view pixel
            return int((x - bounds.min_x) * k), int((bounds.max_y - y) * k)
        # pad R1 (110, -95): bare copper, no ink
        self.assertGreater(layers["copper"].getpixel(px(110, -95))[3], 0)
        self.assertEqual(layers["image"].getpixel(px(110, -95))[3], 0)
        # away from pads: ink
        self.assertEqual(layers["image"].getpixel(px(140, -85))[3], 255)
        # drilled hole of the via (116, -95)
        self.assertGreater(layers["drills"].getpixel(px(116, -95))[3], 0)
        # bottom view is mirrored: the via appears at x' = max_x - 116
        lb, _ = export_preview.render_layers(self.files, "bottom", None, px_per_mm=10)
        self.assertGreater(lb["drills"].getpixel((int((bounds.max_x - 116) * k), int((bounds.max_y + 95) * k)))[3], 0)


if __name__ == "__main__":
    unittest.main()
