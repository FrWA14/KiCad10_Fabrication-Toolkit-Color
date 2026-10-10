"""Pre-flight checks of the final ZIP against everything JLCPCB rejected so far.

Each check: {"code", "ok", "level" ("error"|"warning"), "message"}.
History behind the checks (TESTS.md): "outdated" EasyEDA version markers,
missing EasyEDA fingerprint on a blanked Gerber (colour not applied),
conventional silkscreen printed again in black, pads under the ink.
"""
import re

from .jlc_convert import verify_hash_aperture
from .outline import parse_outline_bounds

MIN_EASYEDA = (3, 2, 135)
REQUIRED = ("Gerber_BoardOutlineLayer.GKO", "Gerber_TopLayer.GTL", "Gerber_BottomLayer.GBL",
            "Gerber_TopSolderMaskLayer.GTS", "Gerber_BottomSolderMaskLayer.GBS",
            "Gerber_TopSilkscreenLayer.GTO", "Gerber_BottomSilkscreenLayer.GBO")
COLOR_FILE = {"top": "Fabrication_ColorfulTopSilkscreen.FCTS", "bottom": "Fabrication_ColorfulBottomSilkscreen.FCBS"}
SILK_FILE = {"top": "Gerber_TopSilkscreenLayer.GTO", "bottom": "Gerber_BottomSilkscreenLayer.GBO"}
MAX_ZIP_BYTES = 20 * 1024 * 1024


def _check(results, code, ok, message, level="error"):
    results.append({"code": code, "ok": bool(ok), "level": level, "message": message})


def run(files, zip_bytes=None, colour_sides=(), blanked_sides=(), composites=None):
    """files: {name: bytes}. colour_sides: faces that must carry a colour file.
    blanked_sides: faces whose conventional silkscreen must be empty. composites: {side: PIL image}."""
    results = []
    missing = [n for n in REQUIRED if n not in files]
    _check(results, "P_FILESET", not missing, "Couches Gerber présentes" if not missing else "Manquant : " + ", ".join(missing))

    bad_header, bad_hash, bad_version = [], [], []
    for name, data in sorted(files.items()):
        if not name.startswith("Gerber_"):
            continue
        text = data.decode("utf-8", "replace")
        m = re.match(r"G04 EasyEDA Pro v(\d+)\.(\d+)\.(\d+)", text)
        if not m:
            bad_header.append(name)
        elif tuple(int(v) for v in m.groups()) < MIN_EASYEDA:
            bad_version.append("{} ({})".format(name, ".".join(m.groups())))
        has_ad = re.search(r"(?m)^%ADD", text)
        draws = re.search(r"(?m)D0[13]\*", text)
        if (has_ad or draws) and not (has_ad and verify_hash_aperture(text)):
            bad_hash.append(name)
    _check(results, "P_HEADER", not bad_header, "En-tête EasyEDA sur chaque Gerber" if not bad_header
           else "Sans en-tête EasyEDA : " + ", ".join(bad_header))
    _check(results, "P_VERSION", not bad_version, "Version EasyEDA >= {}".format(".".join(map(str, MIN_EASYEDA)))
           if not bad_version else "Version trop ancienne (« outdated ») : " + ", ".join(bad_version))
    _check(results, "P_FINGERPRINT", not bad_hash, "Empreinte EasyEDA valide sur chaque Gerber" if not bad_hash
           else "Empreinte absente ou fausse : " + ", ".join(bad_hash))

    for side in colour_sides:
        name = COLOR_FILE[side]
        size = len(files.get(name, b""))
        _check(results, "P_COLOR_" + side.upper(), size >= 528,
               "{} présent ({} octets)".format(name, size) if size >= 528 else "{} absent ou vide".format(name))
    for name in ("Fabrication_ColorfulBoardOutlineLayer.FCBO", "Fabrication_ColorfulBoardOutlineMark.FCBM"):
        if colour_sides:
            _check(results, "P_" + name.split(".")[-1], name in files, name + (" présent" if name in files else " absent"))

    for side in ("top", "bottom"):
        text = files.get(SILK_FILE[side], b"").decode("utf-8", "replace")
        drawn = bool(re.search(r"(?m)D0[13]\*", text))
        if side in blanked_sides:
            _check(results, "P_SILK_" + side.upper(), not drawn and verify_hash_aperture(text) and re.search(r"(?m)^%ADD", text),
                   "Sérigraphie classique {} vidée, avec empreinte".format(side) if not drawn
                   else "La sérigraphie classique {} serait imprimée en noir par-dessus la couleur".format(side))

    if composites and "Gerber_BoardOutlineLayer.GKO" in files:
        b = parse_outline_bounds(files["Gerber_BoardOutlineLayer.GKO"].decode("utf-8", "replace"))
        for side, img in composites.items():
            ratio = (img.width / img.height) / (b.width / b.height)
            _check(results, "P_ASPECT_" + side.upper(), abs(ratio - 1) < 0.002,
                   "Image {} aux proportions du contour".format(side) if abs(ratio - 1) < 0.002
                   else "Image {} déformée ({:.4f})".format(side, ratio))

    if zip_bytes is not None:
        _check(results, "P_ZIP_SIZE", zip_bytes <= MAX_ZIP_BYTES, "ZIP de {:.1f} Mo".format(zip_bytes / 1048576),
               level="warning")
    return results


def summary(results):
    errors = [r for r in results if not r["ok"] and r["level"] == "error"]
    warnings = [r for r in results if not r["ok"] and r["level"] != "error"]
    return errors, warnings
