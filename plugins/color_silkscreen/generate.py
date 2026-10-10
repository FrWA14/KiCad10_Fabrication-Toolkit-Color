"""Entry point: turn a Fabrication Toolkit Gerber folder into a JLCPCB colour set."""
import logging
import os
import re

from . import crypto, jlc_convert, marker, mask, svg_builder
from .errors import ColorSilkError
from .image import load_image
from .outline import parse_outline_bounds
from .report import LOGGER_NAME

TOP_FILE = "Fabrication_ColorfulTopSilkscreen.FCTS"
BOTTOM_FILE = "Fabrication_ColorfulBottomSilkscreen.FCBS"
OUTLINE_FILE = "Fabrication_ColorfulBoardOutlineLayer.FCBO"
MARK_FILE = "Fabrication_ColorfulBoardOutlineMark.FCBM"
MAX_ADJUST_MM = 2.0  # JLCPCB drops the colour print beyond this Gerber adjustment


class Options:
    def __init__(self, fit="stretch", profile="default", debug_svg_dir=None,
                 public_key_pem=crypto.JLC_RSA_PUBLIC_KEY_PEM, expected_bounds_mm=None,
                 mark_inset_mm=svg_builder.MARK_INSET_MM, key_material=None,
                 eda_version=None, easyeda_version=None, blank_silk_sides=()):
        self.fit = fit                      # 'stretch' | 'contain'
        self.profile = profile              # 'default' | 'transjlc'
        self.debug_svg_dir = debug_svg_dir  # write plaintext SVGs here when set
        self.public_key_pem = public_key_pem
        self.expected_bounds_mm = expected_bounds_mm  # (min_x, min_y, max_x, max_y) from pcbnew
        self.mark_inset_mm = mark_inset_mm
        self.key_material = key_material    # tests: fixed key/IV
        transjlc = profile == "transjlc"
        # SVG eda-version and Gerber "EasyEDA Pro vX" header (JLCPCB version checks)
        self.eda_version = eda_version or (svg_builder.EDA_VERSION_TRANSJLC if transjlc else svg_builder.EDA_VERSION)
        # Faces whose silkscreen is printed inside the colour image: their conventional
        # silkscreen Gerber is emptied, otherwise JLCPCB prints it again in black on top.
        self.blank_silk_sides = tuple(blank_silk_sides)
        self.easyeda_version = easyeda_version or (
            jlc_convert.EASYEDA_VERSION_TRANSJLC if transjlc else jlc_convert.EASYEDA_VERSION)


def _read(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def _write_bytes(path, data):
    try:
        with open(path, "wb") as fh:
            fh.write(data)
    except OSError as e:
        raise ColorSilkError("E_ZIP", "Écriture de {} impossible : {}".format(path, e))


def _svg_box(svg):
    m = re.search(r'viewBox="([^"]+)"', svg)
    return [float(v) for v in m.group(1).split()]


def generate_color_silkscreen(gerber_dir, top_image=None, bottom_image=None, report=None, options=None):
    """Rewrite `gerber_dir` in place. Raises ColorSilkError; fills `report` as it goes."""
    log = logging.getLogger(LOGGER_NAME)
    options = options or Options()
    if not top_image and not bottom_image:
        return []

    layers, dropped = jlc_convert.convert_directory(gerber_dir, log, app_version=options.easyeda_version,
                                                    fingerprint_all=options.profile != "transjlc")
    report.step("jlc_convert", easyeda_version=options.easyeda_version, eda_version=options.eda_version, files=sorted(os.path.basename(p) for p in layers.values()), dropped=dropped)
    for side in options.blank_silk_sides:
        key = "F_SILK" if side == "top" else "B_SILK"
        if key in layers:
            jlc_convert.write_blank_silkscreen(layers[key], side, options.easyeda_version)
            report.step("silk_gerber_blanked", side=side, file=os.path.basename(layers[key]))
            report.warn({"code": "I_SILK_GERBER_BLANKED",
                         "message": "Sérigraphie classique {} vidée : elle est imprimée dans l'image couleur.".format(
                             "dessus" if side == "top" else "dessous")})

    outline_text = _read(layers["OUTLINE"])
    bounds = parse_outline_bounds(outline_text, include_arc_extrema=options.profile != "transjlc")
    report.step("outline_bounds", bounds_mm=bounds.as_list(),
                size_mm=[round(bounds.width, 4), round(bounds.height, 4)])

    if options.expected_bounds_mm:
        e = options.expected_bounds_mm
        delta = max(abs(a - b) for a, b in zip(bounds.as_list(), e))
        report.step("board_vs_gerber", ok=delta <= MAX_ADJUST_MM, delta_mm=round(delta, 4), board_bounds_mm=list(e))
        if delta > MAX_ADJUST_MM:
            raise ColorSilkError("E_BOARD_TOO_LARGE_ADJUST",
                                 "Le contour Gerber {} diffère du contour de la carte {} de {:.3f} mm (> {} mm).".format(
                                     bounds.as_list(), list(e), delta, MAX_ADJUST_MM))

    km = options.key_material or crypto.KeyMaterial(options.public_key_pem)
    written = []
    mask_mode = "transjlc" if options.profile == "transjlc" else "exact"

    for side, image_path, mask_key, target, builder in (
            ("top", top_image, "F_MASK", TOP_FILE, svg_builder.build_top_svg),
            ("bottom", bottom_image, "B_MASK", BOTTOM_FILE, svg_builder.build_bottom_svg)):
        if not image_path:
            continue
        warnings = []
        image = load_image(image_path, bounds.width, bounds.height, warnings, options.fit, options.profile)
        report.step("image_" + side, path=image_path, format=image.format, pixels=[image.width, image.height],
                    dpi=round(min(image.width / (bounds.width / 25.4), image.height / (bounds.height / 25.4)), 1),
                    bytes=len(image.bytes))

        mask_paths = []
        if mask_key in layers:
            mask_paths = mask.parse_solder_mask(_read(layers[mask_key]), mask_mode, warnings)
        else:
            warnings.append({"code": "W_NO_MASK", "message": "Pas de Gerber de masque {} : aucune ouverture.".format(side)})
        report.step("mask_" + side, openings=len(mask_paths), mode=mask_mode)
        for w in warnings:
            if w["code"] == "I_MASK_POLYGONS":  # internal geometry, not a user-facing warning
                continue
            if w["code"] == "E_MASK_COVERED":
                raise ColorSilkError("E_MASK_COVERED", "Face {} : {} Positions (mm, Gerber) : {}".format(
                    side, w["message"], w["points_mm"][:10]))
            report.warn(w)

        svg = builder(bounds, image, mask_paths, options.mark_inset_mm, options.eda_version)
        box = _svg_box(svg)
        delta = max(abs(box[0] * 0.254 - bounds.min_x), abs(-box[1] * 0.254 - bounds.max_y),
                    abs(box[2] * 0.254 - bounds.width), abs(box[3] * 0.254 - bounds.height))
        report.step("svg_" + side, bytes=len(svg.encode("utf-8")), gerber_delta_mm=round(delta, 6))
        if delta > MAX_ADJUST_MM:
            raise ColorSilkError("E_BOARD_TOO_LARGE_ADJUST", "SVG {} décalé de {:.3f} mm.".format(side, delta))
        _debug(options, target, svg)

        blob = crypto.encrypt_svg(svg, km)
        expected = 2 * km.rsa_bytes + len(svg.encode("utf-8")) + 16
        if len(blob) != expected:
            raise ColorSilkError("E_CRYPTO_BACKEND", "Taille chiffrée {} ≠ {} attendue.".format(len(blob), expected))
        _write_bytes(os.path.join(gerber_dir, target), blob)
        report.step("encrypt_" + side, bytes=len(blob), backend=crypto.selected_backend() or "fixed")
        written.append(target)

    outline_svg = svg_builder.build_board_outline_svg(bounds, options.profile)
    _debug(options, OUTLINE_FILE, outline_svg)
    _write_bytes(os.path.join(gerber_dir, OUTLINE_FILE), crypto.encrypt_svg(outline_svg, km))
    marks = svg_builder.mark_points(bounds, options.mark_inset_mm)
    _write_bytes(os.path.join(gerber_dir, MARK_FILE),
                 marker.build_outline_mark_gerber(bounds, marks).encode("ascii"))
    written += [OUTLINE_FILE, MARK_FILE]
    report.step("color_files", files=written)
    log.info("fichiers couleur : %s", ", ".join(written))
    return written


def _debug(options, name, svg):
    if options.debug_svg_dir:
        os.makedirs(options.debug_svg_dir, exist_ok=True)
        with open(os.path.join(options.debug_svg_dir, name + ".svg"), "w", encoding="utf-8", newline="") as fh:
            fh.write(svg)
