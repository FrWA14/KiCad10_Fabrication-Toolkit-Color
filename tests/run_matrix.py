"""Board x image matrix through the real headless CLI (KiCad Python required).

    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tests/run_matrix.py

Writes out/matrix/<case>/{report.json, color_silkscreen.log, production/},
out/matrix.json, and refreshes the results table in TESTS.md.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import BOARDS, IMAGES, KICAD_PYTHON, ROOT  # noqa: E402

OUT = os.path.join(ROOT, "out", "matrix")
COLOR_FILES = {"Fabrication_ColorfulBoardOutlineLayer.FCBO", "Fabrication_ColorfulBoardOutlineMark.FCBM"}
TOP, BOTTOM = "Fabrication_ColorfulTopSilkscreen.FCTS", "Fabrication_ColorfulBottomSilkscreen.FCBS"

# id, board, top, bottom, extra args, expected status, expected error code, expected warnings, checks
CASES = [
    ("T1-top", "T1", "logo.png", None, [], "ok", None, [], {}),
    ("T1-none", "T1", None, None, [], "ok", None, [], {}),
    ("T1-tiny", "T1", "tiny.png", None, [], "error", "E_IMAGE_TOO_SMALL", [], {}),
    ("T1-bmp", "T1", "bad.bmp", None, [], "error", "E_IMAGE_FORMAT", [], {}),
    ("T1-missing", "T1", "nope.png", None, [], "error", "E_IMAGE_MISSING", [], {}),
    ("T2-both", "T2", "logo.png", "photo.jpg", [], "ok", None, [], {"mask_top": 4, "mask_bottom": 1}),
    # legacy TransJLC markers are now rejected by JLCPCB ("outdated"): the pre-flight check must say so
    ("T2-transjlc", "T2", "logo.png", "photo.jpg", ["--colorProfile", "transjlc"], "error", "E_PRECHECK", [], {}),
    ("T3-alpha", "T3", "alpha.png", None, [], "ok", None, [], {"bounds": [100, -110, 150, -80]}),
    ("T4-auxorigin", "T4", "logo.png", None, [], "ok", None, [], {"bounds": [-7.5, 0, 42.5, 30]}),
    ("T5-4layers", "T5", None, "photo.jpg", [], "ok", None, [],
     {"zip_has": ["Gerber_InnerLayer1.G1", "Gerber_InnerLayer2.G2"]}),
    ("T6-no-outline", "T6", "logo.png", None, [], "error", "E_OUTLINE_MISSING", [], {}),
    ("T7-huge", "T7", "huge.png", None, [], "ok", None, ["W_IMAGE_RESAMPLED"], {}),
    ("T3-placement", "T3", None, None, ["--placement", "AUTO"], "ok", None, [],
     {"compose": ["top", "bottom"], "bounds": [100, -110, 150, -80]}),
    ("T2-silk-only", "T2", None, None, ["--topSilkColor", "#C0392B"], "ok", None, [], {"compose": ["top"]}),
    ("T5-calibration", "T5", None, None, ["--calibration", "--bottomOffset=-0.3,0"], "ok", None, ["W_CALIBRATION"],
     {"compose": ["top", "bottom"]}),
    ("T7-contain", "T7", "logo.png", None, ["--colorFit", "contain"], "ok", None, ["W_IMAGE_PADDED"], {}),
]


def run_case(case):
    cid, board, top, bottom, extra, exp_status, exp_code, exp_warn, checks = case
    work = os.path.join(OUT, cid)
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    board_path = os.path.join(work, board + ".kicad_pcb")
    shutil.copyfile(os.path.join(BOARDS, board + ".kicad_pcb"), board_path)
    report_path = os.path.join(work, "report.json")
    cmd = [KICAD_PYTHON, "-m", "plugins.cli", "-p", board_path, "-nI", "-nB", "--archiveName", cid,
           "--report", report_path, "--log", os.path.join(work, "color_silkscreen.log"),
           "--debugSvg", os.path.join(work, "svg")] + extra
    if top:
        cmd += ["--topColorImage", os.path.join(IMAGES, top)]
    if bottom:
        cmd += ["--bottomColorImage", os.path.join(IMAGES, bottom)]
    if "AUTO" in cmd:  # placement made in the editor frame: logo top-left on top, photo covering the bottom
        placement = os.path.join(work, "placement.json")
        with open(placement, "w", encoding="utf-8") as fh:
            json.dump({"top": {"image": os.path.join(IMAGES, "logo.png"), "cx": 15, "cy": 10, "w": 20, "h": 12, "rot": 0},
                       "bottom": {"image": os.path.join(IMAGES, "photo.jpg"), "cx": 25, "cy": 15, "w": 60, "h": 36,
                                  "rot": 90}}, fh)
        cmd[cmd.index("AUTO")] = placement
        top, bottom = "logo.png (placé)", "photo.jpg (placé, 90°)"
    proc = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    result = {"id": cid, "board": board, "top": top, "bottom": bottom, "args": extra,
              "exit_code": proc.returncode, "problems": []}
    problems = result["problems"]

    report = None
    if os.path.exists(report_path):
        with open(report_path, encoding="utf-8") as fh:
            report = json.load(fh)
    zip_path = os.path.join(work, "production", cid + ".zip")
    names = []
    if os.path.exists(zip_path):
        with zipfile.ZipFile(zip_path) as z:
            names = z.namelist()
    result["zip_files"] = names

    if not top and not bottom and not any(a.endswith("SilkColor") or a == "--calibration" for a in extra):
        status = "ok" if proc.returncode == 0 and names else "error"
        if report is not None:
            problems.append("report written although no image was given")
        if any(n.startswith("Fabrication_Colorful") for n in names):
            problems.append("colour files present without image")
        result.update(status=status, code=None, warnings=[])
    else:
        if report is None:
            problems.append("no report.json")
            result.update(status="error", code="NO_REPORT", warnings=[])
        else:
            result.update(status=report["status"],
                          code=report["errors"][0]["code"] if report["errors"] else None,
                          warnings=[w["code"] for w in report["warnings"]])
            steps = {s["name"]: s for s in report["steps"]}
            if report["status"] == "ok":
                expected = set(COLOR_FILES) | ({TOP} if top or "compose_top" in steps else set()) |                     ({BOTTOM} if bottom or "compose_bottom" in steps else set())
                if not expected <= set(names):
                    problems.append("missing in zip: {}".format(sorted(expected - set(names))))
                if any(k.startswith("compose_") for k in steps):
                    if not steps.get("precheck", {}).get("ok"):
                        problems.append("precheck failed")
                    for name in ("preview_top.png", "preview_bottom.png"):
                        if not os.path.exists(os.path.join(work, "production", name)):
                            problems.append("missing " + name)
                if "board_vs_gerber" in steps:
                    result["delta_mm"] = steps["board_vs_gerber"]["delta_mm"]
                result["bounds_mm"] = steps["outline_bounds"]["bounds_mm"]
                for side in ("top", "bottom"):
                    if "encrypt_" + side in steps:
                        result["bytes_" + side] = steps["encrypt_" + side]["bytes"]
            for side in checks.get("compose", []):
                if "compose_" + side not in steps:
                    problems.append("no compose_" + side)
                elif not os.path.exists(os.path.join(work, "production", "color_placement.json")):
                    problems.append("color_placement.json missing")
            for key in ("mask_top", "mask_bottom"):
                if key in checks and steps.get(key, {}).get("openings") != checks[key]:
                    problems.append("{} openings {} != {}".format(key, steps.get(key, {}).get("openings"), checks[key]))
            if "bounds" in checks and result.get("bounds_mm") != checks["bounds"]:
                problems.append("bounds {} != {}".format(result.get("bounds_mm"), checks["bounds"]))
    for n in checks.get("zip_has", []):
        if n not in names:
            problems.append("missing {}".format(n))

    if result["status"] != exp_status:
        problems.append("status {} != {}".format(result["status"], exp_status))
    if result["code"] != exp_code:
        problems.append("code {} != {}".format(result["code"], exp_code))
    if (result["exit_code"] == 0) != (exp_status == "ok"):
        problems.append("exit code {}".format(result["exit_code"]))
    for w in exp_warn:
        if w not in result["warnings"]:
            problems.append("missing warning {}".format(w))
    result["pass"] = not problems
    if problems:
        result["output_tail"] = proc.stdout.decode("utf-8", "replace")[-2000:]
    return result


def update_tests_md(results):
    path = os.path.join(ROOT, "TESTS.md")
    rows = ["| Cas | Carte | Image dessus | Image dessous | Options | Attendu | Obtenu | Avertissements | Résultat |",
            "|---|---|---|---|---|---|---|---|---|"]
    for case, r in zip(CASES, results):
        expected = case[5] + (" / " + case[6] if case[6] else "")
        got = r["status"] + (" / " + r["code"] if r["code"] else "")
        rows.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            r["id"], r["board"], r["top"] or "—", r["bottom"] or "—", " ".join(r["args"]) or "—",
            expected, got, ", ".join(r["warnings"]) or "—", "✅" if r["pass"] else "❌ " + "; ".join(r["problems"])))
    table = "\n".join(rows)
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    text = re.sub(r"(<!-- matrix:start -->\n).*?(<!-- matrix:end -->)", lambda m: m.group(1) + table + "\n" + m.group(2),
                  text, flags=re.S)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def main():
    os.makedirs(OUT, exist_ok=True)
    results = [run_case(c) for c in CASES]
    with open(os.path.join(ROOT, "out", "matrix.json"), "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)
    for r in results:
        print("{:16} {:5} {:28} {}".format(r["id"], r["status"], r["code"] or "", "PASS" if r["pass"] else
                                           "FAIL " + "; ".join(r["problems"])))
    if "--no-md" not in sys.argv and os.path.exists(os.path.join(ROOT, "TESTS.md")):
        update_tests_md(results)
    return 0 if all(r["pass"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
