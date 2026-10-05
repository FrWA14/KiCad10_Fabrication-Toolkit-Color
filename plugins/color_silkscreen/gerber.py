"""Minimal RS-274X reader: just enough to get the board outline and mask openings.

Handles what KiCad emits: %FS / %MO / %AD / %AM, G01/G02/G03/G36/G37/G75,
D01/D02/D03, modal coordinates, I/J arc offsets. Everything else is skipped.
"""
import math
import re

from .errors import ColorSilkError

_TOKEN = re.compile(r"%[^%]*%|[^%*]*\*", re.S)
_COORD = re.compile(r"([XYIJ])([+-]?\d+(?:\.\d+)?)")


class Aperture:
    def __init__(self, kind, params):
        self.kind = kind          # 'C', 'R', 'O', 'P' or a macro name
        self.params = params      # list of floats (mm)


class Flash:
    def __init__(self, aperture, x, y):
        self.aperture, self.x, self.y = aperture, x, y


class Stroke:
    """D01 outside a region. `arc` is (cx, cy, clockwise) or None."""

    def __init__(self, aperture, start, end, arc=None):
        self.aperture, self.start, self.end, self.arc = aperture, start, end, arc


class Region:
    """G36/G37 contour. Each segment is (start, end, arc-or-None)."""

    def __init__(self, segments):
        self.segments = segments


class GerberDocument:
    def __init__(self):
        self.unit_scale = 1.0     # multiply file values by this to get mm
        self.int_digits = 4
        self.dec_digits = 6
        self.apertures = {}
        self.macros = {}
        self.flashes = []
        self.strokes = []
        self.regions = []
        self.points = []          # every coordinate visited (mm), for bounds
        self.arcs = []            # (start, end, cx, cy, clockwise) for bounds
        self.g54_selects = False  # aperture selected as G54Dnn (TransJLC's parser misses these)


def parse(text, error_code="E_OUTLINE_PARSE"):
    doc = GerberDocument()
    try:
        _parse_into(doc, text)
    except ColorSilkError:
        raise
    except Exception as e:  # malformed numbers, unknown macro syntax...
        raise ColorSilkError(error_code, "Gerber illisible : {}".format(e))
    return doc


def _parse_into(doc, text):
    x = y = 0.0
    interp = "G01"
    in_region = False
    region_segments = []
    current = None

    def number(raw, axis):
        if "." in raw:
            return float(raw) * doc.unit_scale
        return int(raw) / (10 ** doc.dec_digits) * doc.unit_scale

    for token in _TOKEN.findall(text):
        token = token.strip()
        if not token:
            continue
        if token.startswith("%"):
            _extended(doc, token.strip("%"))
            continue

        word = re.sub(r"\s+", "", token.rstrip("*"))
        if not word or word.startswith("G04"):
            continue
        if word.startswith("G54"):
            word = word[3:]
            doc.g54_selects = True
        if word in ("G01", "G02", "G03"):
            interp = word
            continue
        if word.startswith(("G01", "G02", "G03")) and len(word) > 3:
            interp, word = word[:3], word[3:]
        if word == "G36":
            in_region, region_segments = True, []
            continue
        if word == "G37":
            if region_segments:
                doc.regions.append(Region(region_segments))
            in_region, region_segments = False, []
            continue
        if word in ("G74", "G75", "M02", "M00", "M01") or word.startswith("G7"):
            continue

        m = re.fullmatch(r"D(\d+)", word)
        if m and int(m.group(1)) >= 10:
            current = doc.apertures.get(int(m.group(1)))
            continue

        op = re.search(r"D0?([123])$", word)
        coords = dict((k, v) for k, v in _COORD.findall(word))
        if not coords and not op:
            continue
        nx = number(coords["X"], "X") if "X" in coords else x
        ny = number(coords["Y"], "Y") if "Y" in coords else y
        code = op.group(1) if op else "1"  # deprecated modal D01

        if code == "2":
            if in_region and region_segments:
                doc.regions.append(Region(region_segments))
                region_segments = []
        elif code == "1":
            arc = None
            if interp in ("G02", "G03"):
                i = number(coords.get("I", "0"), "I")
                j = number(coords.get("J", "0"), "J")
                arc = (x + i, y + j, interp == "G02")
                doc.arcs.append(((x, y), (nx, ny), arc[0], arc[1], arc[2]))
            if in_region:
                region_segments.append(((x, y), (nx, ny), arc))
            else:
                doc.strokes.append(Stroke(current, (x, y), (nx, ny), arc))
            doc.points.append((x, y))
        elif code == "3":
            doc.flashes.append(Flash(current, nx, ny))
        doc.points.append((nx, ny))
        x, y = nx, ny

    if in_region and region_segments:
        doc.regions.append(Region(region_segments))


def _extended(doc, body):
    for block in [b.strip() for b in body.split("*") if b.strip()]:
        if block.startswith("FS"):
            m = re.search(r"X(\d)(\d)", block)
            if m:
                doc.int_digits, doc.dec_digits = int(m.group(1)), int(m.group(2))
        elif block.startswith("MO"):
            doc.unit_scale = 25.4 if block[2:4] == "IN" else 1.0
        elif block.startswith("AD"):
            m = re.fullmatch(r"ADD(\d+)([A-Za-z_.$][\w.$]*)(?:,(.*))?", block)
            if m:
                params = [float(p) * doc.unit_scale for p in m.group(3).split("X")] if m.group(3) else []
                doc.apertures[int(m.group(1))] = Aperture(m.group(2), params)
        if block.startswith("AM"):
            name = block[2:]
            doc.macros[name] = [b.strip() for b in body.split("*")[1:] if b.strip()]
            return


def arc_extrema(start, end, cx, cy, clockwise):
    """Points on the arc that bound it (endpoints + crossed axis extremes)."""
    r = math.hypot(start[0] - cx, start[1] - cy)
    a0 = math.atan2(start[1] - cy, start[0] - cx)
    a1 = math.atan2(end[1] - cy, end[0] - cx)
    if clockwise:
        a0, a1 = a1, a0
    if a1 <= a0 + 1e-12:
        a1 += 2 * math.pi
    pts = [start, end]
    k = math.ceil(a0 / (math.pi / 2))
    while k * math.pi / 2 < a1:
        a = k * math.pi / 2
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        k += 1
    return pts
