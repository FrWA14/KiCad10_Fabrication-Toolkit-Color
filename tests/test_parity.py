"""§6.3.5 parity with TransJLC: same input, compare the plaintext SVGs and files.

Needs a TransJLC build carrying tests/transjlc_debug_svg.patch (writes the SVG
before encryption when TRANSJLC_DEBUG_SVG is set):
    git -C ref/TransJLC apply ../../tests/transjlc_debug_svg.patch
    cargo build --release --manifest-path ref/TransJLC/Cargo.toml
"""
import os
import re
import shutil
import subprocess
import unittest

from helpers import FIXTURES, IMAGES, OUT, TRANSJLC_BIN, ensure_images, read

from plugins.color_silkscreen.generate import Options, generate_color_silkscreen
from plugins.color_silkscreen.report import Report

T2 = os.path.join(FIXTURES, "T2_gerbers")
COLOR_SVGS = ["Fabrication_ColorfulTopSilkscreen.FCTS", "Fabrication_ColorfulBottomSilkscreen.FCBS",
              "Fabrication_ColorfulBoardOutlineLayer.FCBO"]
NUM = re.compile(r"-?\d+(?:\.\d+)?")


def _mask_rects(svg):
    d = re.search(r'd="([^"]*)"\s+id="solder1"', svg).group(1)
    return [[float(v) for v in NUM.findall(sub)] for sub in d.split("M ")[2:]]


def _strip_volatile(gerber):
    """Header date and hash aperture are random/time based by design."""
    lines = [l for l in gerber.split("\n") if not l.startswith("G04 EasyEDA Pro v")]
    return "\n".join(l for l in lines if not re.fullmatch(r"%ADD\d+C,0\.\d{4}\*%", l))


@unittest.skipUnless(os.path.exists(TRANSJLC_BIN), "TransJLC binary not built")
class TransJlcParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_images()
        cls.ref = os.path.join(OUT, "parity_ref")
        cls.py = os.path.join(OUT, "parity_py")
        for d in (cls.ref, cls.py, cls.py + "_svg"):
            shutil.rmtree(d, ignore_errors=True)
        top, bottom = os.path.join(IMAGES, "logo.png"), os.path.join(IMAGES, "photo.jpg")
        env = dict(os.environ, TRANSJLC_DEBUG_SVG="1")
        subprocess.run([TRANSJLC_BIN, "-p", T2, "-o", cls.ref, "--top_color_image", top,
                        "--bottom_color_image", bottom, "--no-progress"], check=True, env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        shutil.copytree(T2, cls.py)
        generate_color_silkscreen(cls.py, top, bottom, Report(),
                                  Options(profile="transjlc", debug_svg_dir=cls.py + "_svg"))

    def test_debug_patch_applied(self):
        missing = [n for n in COLOR_SVGS if not os.path.exists(os.path.join(self.ref, n + ".svg"))]
        if missing:
            self.skipTest("TransJLC built without tests/transjlc_debug_svg.patch")

    def test_same_file_set(self):
        ref = sorted(n for n in os.listdir(self.ref) if not n.endswith(".svg"))
        self.assertEqual(sorted(os.listdir(self.py)), ref)

    def test_svgs_identical_except_mask_sizes(self):
        self.test_debug_patch_applied()
        for name in COLOR_SVGS:
            ref = read(os.path.join(self.ref, name + ".svg"))
            py = read(os.path.join(self.py + "_svg", name + ".svg"))
            if "solder1" not in ref:
                self.assertEqual(py, ref, name)
                continue
            # Outside the mask path, byte-identical.
            pattern = r'(d=")[^"]*("\s+id="solder1")'
            self.assertEqual(re.sub(pattern, r"\1\2", py), re.sub(pattern, r"\1\2", ref), name)
            # Mask openings: same count and centres; sizes differ because TransJLC
            # uses its random hash aperture for every flash (G54 parsing bug).
            r_rects, p_rects = _mask_rects(ref), _mask_rects(py)
            self.assertEqual(len(p_rects), len(r_rects), name)
            for a, b in zip(r_rects, p_rects):
                ca = ((a[0] + a[2]) / 2, (a[1] + a[5]) / 2)
                cb = ((b[0] + b[2]) / 2, (b[1] + b[5]) / 2)
                self.assertAlmostEqual(ca[0], cb[0], places=6)
                self.assertAlmostEqual(ca[1], cb[1], places=6)

    def test_mark_file_identical(self):
        name = "Fabrication_ColorfulBoardOutlineMark.FCBM"
        self.assertEqual(read(os.path.join(self.py, name)), read(os.path.join(self.ref, name)))

    def test_gerbers_identical_modulo_header_and_hash(self):
        for name in os.listdir(self.ref):
            if name.startswith("Gerber_") or name.startswith("Drill_"):
                self.assertEqual(_strip_volatile(read(os.path.join(self.py, name))),
                                 _strip_volatile(read(os.path.join(self.ref, name))), name)

    def test_encrypted_sizes(self):
        self.test_debug_patch_applied()
        for name in COLOR_SVGS:
            for blob_dir, svg_dir in ((self.ref, self.ref), (self.py, self.py + "_svg")):
                svg_len = len(read(os.path.join(svg_dir, name + ".svg"), "rb"))
                self.assertEqual(os.path.getsize(os.path.join(blob_dir, name)), 512 + svg_len + 16, blob_dir)


if __name__ == "__main__":
    unittest.main()
