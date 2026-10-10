"""Integration through the real CLI. Run with KiCad's Python (pcbnew + Pillow).

The upstream comparison needs the reference clone in ref/Fabrication-Toolkit.
"""
import os
import re
import shutil
import subprocess
import sys
import unittest
import zipfile

from helpers import BOARDS, KICAD_PYTHON, OUT, ROOT, have_pcbnew

UPSTREAM = os.path.join(ROOT, "ref", "Fabrication-Toolkit")

# Lines that legitimately change between two exports of the same board.
VOLATILE = re.compile(r"^(G04 #@! TF\.CreationDate|%TF\.CreationDate|G04 Created by KiCad|; DRILL file .* date|;.*(date|Date))"
                      r"[^\r\n]*", re.M)


def _export(cwd, board, name):
    work = os.path.join(OUT, "nonreg_" + name)
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    path = os.path.join(work, board + ".kicad_pcb")
    shutil.copyfile(os.path.join(BOARDS, board + ".kicad_pcb"), path)
    subprocess.run([KICAD_PYTHON, "-m", "plugins.cli", "-p", path, "-nI", "-nB", "--archiveName", board],
                   cwd=cwd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    production = os.path.join(work, "production")
    with zipfile.ZipFile(os.path.join(production, board + ".zip")) as z:
        files = {n: VOLATILE.sub("", z.read(n).decode("utf-8", "replace")) for n in z.namelist()}
    # KiCad 10.0.4 writes an uninitialised soldermask field on IPC-D-356 VIA
    # records (changes on every run, upstream too): ignore it.
    others = {n: re.sub(r"(VIA .*S)-?\d+", r"\1?", open(os.path.join(production, n), encoding="utf-8").read())
              for n in os.listdir(production) if n.endswith((".csv", ".ipc"))}
    return files, others


@unittest.skipUnless(have_pcbnew(), "needs KiCad's Python (pcbnew)")
class Integration(unittest.TestCase):
    def test_matrix(self):
        sys.path.insert(0, os.path.join(ROOT, "tests"))
        import run_matrix
        failures = [r for r in map(run_matrix.run_case, run_matrix.CASES) if not r["pass"]]
        self.assertEqual(failures, [])

    def test_cpl_only_lists_bom_parts(self):
        """A mounting hole excluded from the BOM but not from position files must not be in the CPL."""
        work = os.path.join(OUT, "cpl_T8")
        shutil.rmtree(work, ignore_errors=True)
        os.makedirs(work)
        path = os.path.join(work, "T8.kicad_pcb")
        shutil.copyfile(os.path.join(BOARDS, "T8.kicad_pcb"), path)
        subprocess.run([KICAD_PYTHON, "-m", "plugins.cli", "-p", path, "-nI", "-nB", "--archiveName", "T8"],
                       cwd=ROOT, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(os.path.join(work, "production", "T8_positions.csv"), encoding="utf-8-sig") as fh:
            cpl = [line.split(",")[0] for line in fh.read().splitlines()[1:]]
        with open(os.path.join(work, "production", "T8_bom.csv"), encoding="utf-8-sig") as fh:
            bom = fh.read()
        self.assertEqual(cpl, ["R1"])
        self.assertNotIn("H1", bom)

    def test_tented_via_not_cut_pads_cut(self):
        """Ink goes over tented vias; bare copper (mask openings) and pad holes are cut."""
        import pcbnew  # type: ignore
        from plugins.color_silkscreen import board_view, placement as pl
        view = board_view.extract(pcbnew.LoadBoard(os.path.join(BOARDS, "T2.kicad_pcb")))
        k = pl.DPI / 25.4
        p = {"image": os.path.join(ROOT, "tests", "img", "logo.png"), "cx": 25, "cy": 15, "w": 50, "h": 30, "rot": 0}
        a = pl.compose(view, "top", p).getchannel("A")
        self.assertEqual(a.getpixel((int(16 * k), int(15 * k))), 255)   # tented via (116, -95): ink over it
        self.assertEqual(a.getpixel((int(10 * k), int(15 * k))), 0)     # SMD pad: cut
        self.assertEqual(a.getpixel((int(22 * k), int(15 * k))), 0)     # THT pad and its hole: cut
        b = pl.compose(view, "bottom", p).getchannel("A")
        self.assertEqual(b.getpixel((int((50 - 16) * k), int(15 * k))), 255)  # tented on the bottom too
        self.assertEqual(b.getpixel((int((50 - 22) * k), int(15 * k))), 0)    # THT pad open on the bottom

    @unittest.skipUnless(os.path.isdir(os.path.join(UPSTREAM, "plugins")), "no upstream clone in ref/")
    def test_no_image_identical_to_upstream(self):
        """§6.3.9: without image, same ZIP (and BOM/CPL) as Fabrication Toolkit."""
        for board in ("T2", "T5"):
            ours, ours_other = _export(ROOT, board, "ours_" + board)
            theirs, theirs_other = _export(UPSTREAM, board, "upstream_" + board)
            self.assertEqual(sorted(ours), sorted(theirs), board)
            for name in ours:
                self.assertEqual(ours[name], theirs[name], "{}: {}".format(board, name))
            self.assertEqual(ours_other, theirs_other, board)


if __name__ == "__main__":
    unittest.main()
