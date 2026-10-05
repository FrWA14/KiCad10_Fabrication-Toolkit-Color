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
