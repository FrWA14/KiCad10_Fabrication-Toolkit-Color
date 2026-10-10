"""Unit tests: no KiCad needed. Run with any Python 3.8+ (pytest or unittest)."""
import io
import os
import random
import re
import shutil
import unittest
import zipfile

from helpers import (FIXTURES, IMAGES, OUT, ensure_images, have_cryptography, image_placement, read)

from plugins.color_silkscreen import crypto, gerber, jlc_convert, marker, mask, svg_builder
from plugins.color_silkscreen.errors import ColorSilkError
from plugins.color_silkscreen.generate import Options, generate_color_silkscreen
from plugins.color_silkscreen.image import load_image
from plugins.color_silkscreen.numfmt import f
from plugins.color_silkscreen.outline import BoardBounds, parse_outline_bounds
from plugins.color_silkscreen.report import Report

T2 = os.path.join(FIXTURES, "T2_gerbers")
TOP_KEY = bytes([96, 251, 63, 138, 10, 53, 0, 203, 150, 177, 136, 29, 83, 139, 70, 130])
TOP_IV = bytes([102, 221, 239, 247, 95, 55, 142, 28, 51, 165, 68, 208, 7, 250, 86, 5])
BOTTOM_KEY = bytes([90, 50, 20, 193, 6, 67, 43, 228, 131, 126, 89, 124, 77, 32, 217, 139])
BOTTOM_IV = bytes([122, 69, 187, 114, 43, 165, 6, 126, 105, 24, 156, 226, 43, 12, 151, 131])
PRIV = read(os.path.join(FIXTURES, "test_rsa_private.pem"))
PUB = read(os.path.join(FIXTURES, "test_rsa_public.pem"))


class CryptoTests(unittest.TestCase):
    """§6.3.3 / §6.3.4: binary structure and round trip with a local key pair."""

    def _vector(self, name, svg, key, iv):
        plain = read(os.path.join(FIXTURES, "transjlc", svg), "rb")
        expected = read(os.path.join(FIXTURES, "transjlc", name), "rb")
        return plain, key, iv, expected[512:]

    def test_transjlc_vectors_all_backends(self):
        # The sample .FCTS/.FCBS come from TransJLC's test data (EasyEDA output).
        for name, svg, key, iv in (("Fabrication_ColorfulTopSilkscreen.FCTS", "test_top.svg", TOP_KEY, TOP_IV),
                                   ("Fabrication_ColorfulBottomSilkscreen.FCBS", "test_bottom.svg", BOTTOM_KEY, BOTTOM_IV)):
            plain, key, iv, tail = self._vector(name, svg, key, iv)
            for backend in ("python", "openssl", "cryptography"):
                try:
                    out = crypto.aes_gcm_encrypt(key, iv, plain, backend=backend)
                except Exception as e:  # backend absent in this interpreter
                    if backend == "python":
                        raise
                    print("backend {} skipped: {}".format(backend, e))
                    continue
                self.assertEqual(out, tail, "{} / {}".format(backend, name))

    def test_gcm_decrypt_vector(self):
        plain, key, iv, tail = self._vector("Fabrication_ColorfulTopSilkscreen.FCTS", "test_top.svg", TOP_KEY, TOP_IV)
        self.assertEqual(crypto.aes_gcm_decrypt(key, iv, tail), plain)
        with self.assertRaises(ValueError):
            crypto.aes_gcm_decrypt(key, iv, tail[:-1] + bytes([tail[-1] ^ 1]))

    def test_gcm_odd_lengths(self):
        for n in (0, 1, 15, 16, 17, 1000):
            data = bytes(random.getrandbits(8) for _ in range(n))
            out = crypto.aes_gcm_encrypt(b"k" * 16, b"i" * 16, data, backend="python")
            self.assertEqual(len(out), n + 16)
            self.assertEqual(crypto.aes_gcm_decrypt(b"k" * 16, b"i" * 16, out), data)

    def test_jlc_public_key_is_2048_bits(self):
        n, e = crypto.load_public_key(crypto.JLC_RSA_PUBLIC_KEY_PEM)
        self.assertEqual(n.bit_length(), 2048)
        self.assertEqual(e, 65537)

    def test_envelope_round_trip_with_test_key(self):
        svg = '<svg xmlns="http://www.w3.org/2000/svg">é</svg>'
        km = crypto.KeyMaterial(PUB)
        blob = crypto.encrypt_svg(svg, km)
        self.assertEqual(len(blob), 512 + len(svg.encode("utf-8")) + 16)
        self.assertEqual(crypto.decrypt_file(blob, PRIV).decode("utf-8"), svg)

    @unittest.skipUnless(have_cryptography(), "cryptography absent")
    def test_oaep_interoperates_with_cryptography(self):
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        priv = serialization.load_pem_private_key(PRIV.encode(), None)
        n, e = crypto.load_public_key(PUB)
        ct = crypto.rsa_oaep_encrypt(n, e, b"0123456789abcdef")
        oaep = padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
        self.assertEqual(priv.decrypt(ct, oaep), b"0123456789abcdef")
        ct2 = priv.public_key().encrypt(b"fedcba9876543210", oaep)
        n, _, d = crypto.load_private_key(PRIV)
        self.assertEqual(crypto.rsa_oaep_decrypt(n, d, ct2), b"fedcba9876543210")


class NumberFormatTests(unittest.TestCase):
    def test_rust_display(self):
        self.assertEqual(f(50.0), "50")
        self.assertEqual(f(-0.5), "-0.5")
        self.assertEqual(f(196.8503937007874), "196.8503937007874")
        self.assertEqual(f(1e-7), "0.0000001")
        self.assertEqual(f(0.1 + 0.2), "0.30000000000000004")


class OutlineTests(unittest.TestCase):
    def test_fixture_rectangle(self):
        b = parse_outline_bounds(read(os.path.join(T2, "T2-Edge_Cuts.gm1")))
        self.assertEqual(b.as_list(), [100.0, -110.0, 150.0, -80.0])

    def test_arc_extrema(self):
        # Half circle bulging past its endpoints: only the extrema catch it.
        arc = "%FSLAX46Y46*%\n%MOMM*%\n%ADD10C,0.1*%\nD10*\nG75*\nX10000000Y0D02*\n{}X10000000Y2000000I0J1000000D01*\nM02*\n"
        self.assertAlmostEqual(parse_outline_bounds(arc.format("G03")).max_x, 11.0)  # counter-clockwise: right
        self.assertAlmostEqual(parse_outline_bounds(arc.format("G02")).min_x, 9.0)   # clockwise: left
        with self.assertRaises(ColorSilkError):  # TransJLC (endpoints only) sees a zero-width outline
            parse_outline_bounds(arc.format("G03"), include_arc_extrema=False)

    def test_inches(self):
        g = "%FSLAX24Y24*%\n%MOIN*%\nX0Y0D02*\nX10000Y20000D01*\nM02*\n"
        self.assertEqual(parse_outline_bounds(g).as_list(), [0, 0, 25.4, 50.8])

    def test_empty_outline(self):
        empty = "%FSLAX46Y46*%\n%MOMM*%\nG04 nothing*\nM02*\n"
        with self.assertRaises(ColorSilkError) as cm:
            parse_outline_bounds(empty)
        self.assertEqual(cm.exception.code, "E_OUTLINE_MISSING")

    def test_garbage_outline(self):
        with self.assertRaises(ColorSilkError) as cm:
            parse_outline_bounds("%FSLAX46Y46*%\nX0Y0D02*\nX0Y5000000D01*\n")  # zero width
        self.assertEqual(cm.exception.code, "E_OUTLINE_PARSE")


class MaskTests(unittest.TestCase):
    def setUp(self):
        self.text = read(os.path.join(T2, "T2-F_Mask.gts"))

    def test_exact_shapes(self):
        paths = mask.parse_solder_mask(self.text)
        self.assertEqual(len(paths), 4)  # rect, circle (PTH), RoundRect, oval
        self.assertIn(" A ", paths[1])  # circle drawn with arcs
        # rect 2.0 x 1.2 mm at (110, -95): 10-mil frame, Y inverted.
        xs = [float(v) for v in re.findall(r"-?\d+\.?\d*", paths[0])[0::2]]
        self.assertAlmostEqual(max(xs) - min(xs), 2.0 / 0.254, places=6)
        # RoundRect hull includes the corner radius: full 1.6 x 1.0 mm.
        nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", paths[2])]
        xs, ys = nums[0::2], nums[1::2]
        self.assertAlmostEqual((max(xs) - min(xs)) * 0.254, 1.6, places=3)
        self.assertAlmostEqual((max(ys) - min(ys)) * 0.254, 1.0, places=3)

    def test_transjlc_bbox_mode(self):
        paths = mask.parse_solder_mask(self.text.replace("D1", "D1"), "transjlc")
        self.assertEqual(len(paths), 4)
        self.assertTrue(paths[0].startswith("M "))
        self.assertTrue(paths[0].endswith(" "))

    def test_region_and_stroke(self):
        g = ("%FSLAX46Y46*%\n%MOMM*%\n%ADD10C,0.2*%\nG36*\nX0Y0D02*\nX1000000Y0D01*\n"
             "G03X1000000Y1000000I0J500000D01*\nX0Y0D01*\nG37*\nG01*\nD10*\nX0Y0D02*\nX5000000Y0D01*\nM02*\n")
        warnings = []
        paths = mask.parse_solder_mask(g, warnings=warnings)
        codes = {w["code"]: w for w in warnings}
        # region and stroke touch at (0, 0): merged into non-overlapping rectangles
        self.assertIn("1 groupe(s) unifié", codes["I_MASK_MERGED"]["message"])
        self.assertNotIn("E_MASK_COVERED", codes)
        self.assertTrue(all(p.startswith("M ") and p.endswith("Z ") for p in paths))
        # a region alone keeps its true arcs
        alone = mask.parse_solder_mask(g.replace("D10*\nX0Y0D02*\nX5000000Y0D01*\n", ""))
        self.assertEqual(len(alone), 1)
        self.assertIn("A ", alone[0])


class MaskOverlapTests(unittest.TestCase):
    """Even-odd clip: overlapping openings must not cancel (USB-C stacked pads A1/B12 bug)."""

    GERBER = ("%FSLAX46Y46*%\n%MOMM*%\n%ADD10R,0.600000X1.300000*%\n%ADD11C,6.400000*%\n%ADD12C,0.800000*%\n"
              "%ADD13R,1.000000X1.000000*%\n"
              "D10*\nX10000000Y-5000000D03*\nX10000000Y-5000000D03*\n"          # two stacked identical pads
              "D11*\nX30000000Y-10000000D03*\nD12*\nX31700000Y-10000000D03*\n"  # via inside a big pad
              "D13*\nX50000000Y-5000000D03*\nX50600000Y-5000000D03*\n"          # two partly overlapping pads
              "M02*\n")

    def test_every_pad_stays_open(self):
        from plugins.color_silkscreen.union import covered_points
        warnings = []
        mask.parse_solder_mask(self.GERBER, warnings=warnings)
        codes = {w["code"]: w for w in warnings}
        self.assertNotIn("E_MASK_COVERED", codes)
        merged = codes["I_MASK_MERGED"]["message"]
        self.assertIn("1 doublon", merged)
        self.assertIn("1 ouverture(s) incluse", merged)
        self.assertIn("1 groupe(s) unifié", merged)
        polys = codes["I_MASK_POLYGONS"]["polygons"]
        extra = [mask.to_svg(50.3, -5), mask.to_svg(31.7, -10)]  # overlap zone, contained via
        self.assertEqual(covered_points(codes["I_MASK_POLYGONS"]["centres"] + extra, polys), [])

    def test_naive_even_odd_would_fail(self):
        from plugins.color_silkscreen import union
        sq = [(0, 0), (1, 0), (1, 1), (0, 1)]
        self.assertEqual(union.covered_points([(0.5, 0.5)], [sq, sq]), [(0.5, 0.5)])  # the original bug
        rects = union.union_rectangles([sq, [(0.5, 0), (1.5, 0), (1.5, 1), (0.5, 1)]], 0.1)
        self.assertEqual(rects, [(0.0, 0.0, 1.5, 1.0)])


class JlcConvertTests(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(jlc_convert.classify("b-NPTH.drl")[1], "Drill_NPTH_Through.DRL")
        self.assertEqual(jlc_convert.classify("b-PTH.drl")[1], "Drill_PTH_Through.DRL")
        self.assertEqual(jlc_convert.classify("b-Edge_Cuts.gm1")[1], "Gerber_BoardOutlineLayer.GKO")
        self.assertEqual(jlc_convert.classify("b-In2_Cu.g2")[1], "Gerber_InnerLayer2.G2")
        self.assertEqual(jlc_convert.classify("b-In1_Cu.gbr")[1], "Gerber_InnerLayer1.G1")
        self.assertIsNone(jlc_convert.classify("b-PTH-drl_map.gbr"))
        self.assertIsNone(jlc_convert.classify("b-job.gbrjob"))

    def test_hash_aperture(self):
        g = "%FSLAX24Y24*%\n%MOMM*%\n%ADD10C,0.1*%\n%ADD11C,0.2*%\nG54D10*\nX0Y0D02*\nG54D11*\nX100Y100D01*\nM02*\n"
        out = jlc_convert.add_hash_aperture(g)
        self.assertIn("%ADD12C,0.", out)
        self.assertTrue(jlc_convert.verify_hash_aperture(out))
        stale = "%ADD10C,0.1*%\n%ADD11C,0.1234*%\nG54D10*\nX0Y0D02*\nM02*\n"
        out = jlc_convert.add_hash_aperture(stale)
        self.assertNotIn("%ADD11C,0.1234*%", out)
        self.assertTrue(jlc_convert.verify_hash_aperture(out))

    def test_g54_and_normalisation(self):
        self.assertTrue(jlc_convert.has_missing_g54_prefix("D10*\nG54D11*\n"))
        self.assertFalse(jlc_convert.has_missing_g54_prefix("X30584000Y-7866000D03*\n"))
        out = jlc_convert.add_missing_g54_prefix("X1Y1D03*\nD10*\n%ADD12C,0.1*%")
        self.assertIn("G54D10*", out)
        self.assertIn("X1Y1D03*", out)
        n = jlc_convert.normalize_aperture_decimals(
            jlc_convert.strip_deprecated_attribute_blocks(jlc_convert.split_combined_fs_mo(
                "%FSLAX24Y24*MOMM*%\n%IR0*IPPOS*OFA0B0*MIA0B0*SFA1B1*%\n%ADD10C,.15*%\n")))
        self.assertIn("%FSLAX24Y24*%\n%MOMM*%", n)
        self.assertNotIn("%IR0", n)
        self.assertIn("%ADD10C,0.15*%", n)
        self.assertIn("T01C0.01", jlc_convert.normalize_excellon("T01C.01\n"))

    def test_convert_directory(self):
        work = os.path.join(OUT, "convert")
        shutil.rmtree(work, ignore_errors=True)
        shutil.copytree(T2, work)
        layers, dropped = jlc_convert.convert_directory(work)
        names = sorted(os.listdir(work))
        self.assertIn(jlc_convert.NOTICE_NAME, names)
        self.assertIn("Gerber_TopSolderMaskLayer.GTS", names)
        self.assertEqual(sorted(dropped), ["T2-NPTH-drl_map.gbr", "T2-PTH-drl_map.gbr"])
        gts = read(os.path.join(work, "Gerber_TopSolderMaskLayer.GTS"))
        self.assertTrue(gts.startswith("G04 EasyEDA Pro v{}, ".format(jlc_convert.EASYEDA_VERSION)))
        self.assertTrue(jlc_convert.add_gerber_header("M02*\n", app_version="2.2.42.2").startswith("G04 EasyEDA Pro v2.2.42.2, "))
        self.assertTrue(jlc_convert.verify_hash_aperture(gts))
        self.assertIn("G54D10*", gts)


class MarkerTests(unittest.TestCase):
    """§6.3.7: plain Gerber, three flashes inside the outline at the inset."""

    def test_marks(self):
        b = BoardBounds(100, -110, 150, -80)
        text = marker.build_outline_mark_gerber(b, svg_builder.mark_points(b))
        doc = gerber.parse(text)
        self.assertEqual(len(doc.flashes), 3)
        for fl in doc.flashes:
            self.assertTrue(b.min_x < fl.x < b.max_x and b.min_y < fl.y < b.max_y)
            inset = min(fl.x - b.min_x, b.max_x - fl.x, fl.y - b.min_y, b.max_y - fl.y)
            self.assertAlmostEqual(inset, 0.0762, places=5)
        self.assertEqual(len(doc.strokes), 4)
        self.assertIn("X+10007620Y-10992380D03*", text)


class ImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_images()

    def load(self, name, w=50, h=30, fit="stretch"):
        warnings = []
        img = load_image(os.path.join(IMAGES, name), w, h, warnings, fit)
        return img, [x["code"] for x in warnings]

    def test_png_and_jpeg(self):
        img, warns = self.load("logo.png")
        self.assertTrue(img.data_uri.startswith("data:image/png;base64,"))
        self.assertEqual(warns, [])
        img, _ = self.load("photo.jpg")
        self.assertTrue(img.data_uri.startswith("data:image/jpeg;base64,"))

    def test_alpha_png_is_kept(self):
        img, _ = self.load("alpha.png")
        from PIL import Image
        import base64
        decoded = Image.open(io.BytesIO(base64.b64decode(img.data_uri.split(",", 1)[1])))
        self.assertIn("A", decoded.mode)

    def test_bmp_rejected(self):
        with self.assertRaises(ColorSilkError) as cm:
            self.load("bad.bmp")
        self.assertEqual(cm.exception.code, "E_IMAGE_FORMAT")

    def test_tiny_rejected(self):
        with self.assertRaises(ColorSilkError) as cm:
            self.load("tiny.png")
        self.assertEqual(cm.exception.code, "E_IMAGE_TOO_SMALL")

    def test_huge_resampled_to_1200_dpi(self):
        img, warns = self.load("huge.png", 100, 100)
        self.assertIn("W_IMAGE_RESAMPLED", warns)
        self.assertEqual((img.width, img.height), (4724, 4724))

    def test_aspect(self):
        _, warns = self.load("logo.png", 30, 30)
        self.assertIn("W_IMAGE_ASPECT", warns)
        img, warns = self.load("logo.png", 30, 30, fit="contain")
        self.assertIn("W_IMAGE_PADDED", warns)
        self.assertEqual(img.width, img.height)


class SvgTests(unittest.TestCase):
    """§6.3.6 (structural form): the image covers exactly the board, bottom is mirrored."""

    class _Img:
        width, height, data_uri = 100, 60, "data:image/png;base64,AAAA"

    def test_top_and_bottom_placement(self):
        b = BoardBounds(100, -110, 150, -80)
        for builder, mirrored in ((svg_builder.build_top_svg, False), (svg_builder.build_bottom_svg, True)):
            svg = builder(b, self._Img(), [])
            x0, x1, y0, y1, group_mirror, image_mirror = image_placement(svg)
            self.assertAlmostEqual(x0 * 0.254, 100)
            self.assertAlmostEqual(x1 * 0.254, 150)
            self.assertAlmostEqual(-y1 * 0.254, -110)
            self.assertAlmostEqual(-y0 * 0.254, -80)
            self.assertEqual(group_mirror, mirrored)
            self.assertEqual(image_mirror, mirrored)  # double mirror: image reads correctly from below

    def test_outline_svg_frames(self):
        b = BoardBounds(100, -110, 150, -80)
        self.assertIn('viewBox="393.7007874015748 314.96062992125985', svg_builder.build_board_outline_svg(b))
        self.assertIn('viewBox="393.7007874015748 -433.07086614173227',
                      svg_builder.build_board_outline_svg(b, "transjlc"))


class GenerateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_images()

    def run_generate(self, name, **opts):
        work = os.path.join(OUT, name)
        shutil.rmtree(work, ignore_errors=True)
        shutil.copytree(T2, work)
        report = Report()
        options = Options(public_key_pem=PUB, debug_svg_dir=work + "_svg", **opts)
        written = generate_color_silkscreen(work, os.path.join(IMAGES, "logo.png"),
                                            os.path.join(IMAGES, "photo.jpg"), report, options)
        return work, written, report

    def test_full_set_and_round_trip(self):
        work, written, report = self.run_generate("gen_default")
        self.assertEqual(sorted(written), sorted([
            "Fabrication_ColorfulTopSilkscreen.FCTS", "Fabrication_ColorfulBottomSilkscreen.FCBS",
            "Fabrication_ColorfulBoardOutlineLayer.FCBO", "Fabrication_ColorfulBoardOutlineMark.FCBM"]))
        for name in written[:-1]:
            blob = read(os.path.join(work, name), "rb")
            svg = read(os.path.join(work + "_svg", name + ".svg"))
            self.assertEqual(len(blob), 512 + len(svg.encode("utf-8")) + 16)
            self.assertEqual(crypto.decrypt_file(blob, PRIV).decode("utf-8"), svg)
        steps = {s["name"]: s for s in report.data["steps"]}
        self.assertLess(steps["svg_top"]["gerber_delta_mm"], 2.0)
        self.assertEqual(steps["mask_top"]["openings"], 4)

    def test_board_mismatch_over_2mm(self):
        with self.assertRaises(ColorSilkError) as cm:
            self.run_generate("gen_mismatch", expected_bounds_mm=(100, -110, 152.5, -80))
        self.assertEqual(cm.exception.code, "E_BOARD_TOO_LARGE_ADJUST")

    def test_board_match_within_2mm(self):
        _, _, report = self.run_generate("gen_match", expected_bounds_mm=(100.025, -110.025, 150.025, -79.975))
        self.assertTrue(report.ok)

    def test_zip_like_fabrication_toolkit(self):
        work, _, _ = self.run_generate("gen_zip")
        path = shutil.make_archive(work, "zip", work)
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
        self.assertIn("Gerber_BoardOutlineLayer.GKO", names)
        self.assertIn("Fabrication_ColorfulTopSilkscreen.FCTS", names)


if __name__ == "__main__":
    unittest.main()
