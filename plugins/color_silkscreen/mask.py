"""Solder-mask openings -> SVG path data (port of TransJLC mask.rs).

Coordinates are converted to 10-mil units with Y inverted, the frame used by
the colour SVG. Two modes:

* ``exact`` (default): true shapes. Circles become arcs, every other aperture
  (rect, obround, polygon, KiCad macros such as RoundRect) becomes the convex
  hull of its primitives; regions keep their arcs; strokes become stadiums.
* ``transjlc``: byte-for-byte TransJLC behaviour (aperture bounding boxes,
  regions linearised, strokes ignored). Used for parity tests.

The clip path uses fill-rule evenodd, so overlapping openings cancel out;
`warnings` reports the cases where that can happen (strokes).
"""
import math
import re

from . import gerber
from .errors import ColorSilkError
from .numfmt import f
from .union import covered_points, merge_openings

UNIT = 0.254  # mm per 10 mil
CIRCLE_SEGMENTS = 48


def to_svg(x_mm, y_mm):
    return x_mm / UNIT, -(y_mm / UNIT)


def parse_solder_mask(text, mode="exact", warnings=None):
    if warnings is None:
        warnings = []
    if not text or not text.strip():
        return []
    doc = gerber.parse(text, "E_MASK_PARSE")
    if mode == "transjlc":
        return _transjlc_paths(doc)
    return _exact_paths(doc, warnings)


# --------------------------------------------------------------------------- TransJLC mode

def _transjlc_bbox(ap):
    if ap.kind == "C" and ap.params:
        return ap.params[0], ap.params[0]
    if ap.kind in ("R", "O") and len(ap.params) >= 2:
        return ap.params[0], ap.params[1]
    if ap.kind == "RoundRect" and len(ap.params) >= 3:
        coords = ap.params[1:]
        pairs = [coords[i:i + 2] for i in range(0, len(coords), 2) if len(coords[i:i + 2]) == 2]
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        return abs(max(xs) - min(xs)), abs(max(ys) - min(ys))
    return None


def _rect_path(cx, cy, w_mm, h_mm):
    hw, hh = w_mm / UNIT / 2.0, h_mm / UNIT / 2.0
    x0, x1, y0, y1 = cx - hw, cx + hw, cy - hh, cy + hh
    return "M {x0} {y0} L {x1} {y0} {x1} {y1} {x0} {y1} {x0} {y0} ".format(
        x0=f(x0), x1=f(x1), y0=f(y0), y1=f(y1))


def _transjlc_paths(doc):
    shapes = []
    fallback = doc.apertures[max(doc.apertures)] if doc.apertures else None
    for flash in doc.flashes:
        # TransJLC 0.4.0's gerber parser ignores G54Dnn selects and falls back to
        # the highest aperture code, i.e. the tiny hash aperture it just added.
        ap = fallback if doc.g54_selects else (flash.aperture or fallback)
        bbox = _transjlc_bbox(ap) if ap else None
        if bbox:
            cx, cy = to_svg(flash.x, flash.y)
            shapes.append(_rect_path(cx, cy, bbox[0], bbox[1]))
    for region in doc.regions:
        pts = [to_svg(*region.segments[0][0])] + [to_svg(*s[1]) for s in region.segments]
        d = "".join(("M {} {} " if i == 0 else "L {} {} ").format(f(x), f(y)) for i, (x, y) in enumerate(pts))
        shapes.append(d + "Z")
    return shapes


# --------------------------------------------------------------------------- exact mode

def _circle_points(cx, cy, r, n=CIRCLE_SEGMENTS):
    return [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def _rotate(points, deg):
    if not deg:
        return points
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [(x * c - y * s, x * s + y * c) for x, y in points]


def _convex_hull(points):
    pts = sorted(set((round(x, 9), round(y, 9)) for x, y in points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


_SAFE_EXPR = re.compile(r"^[0-9.+\-*/()v\[\] ]*$")


def _eval_expr(expr, variables):
    py = re.sub(r"\$(\d+)", lambda m: "v[{}]".format(int(m.group(1))), expr.replace("x", "*").replace("X", "*"))
    if not _SAFE_EXPR.match(py):
        raise ValueError("expression de macro non supportée : " + expr)
    return float(eval(py, {"__builtins__": {}}, {"v": variables}))


def _macro_points(primitives, params):
    """Outline points (mm, aperture-centred) of every exposure-on primitive."""
    v = _VarList(params)
    pts = []
    for prim in primitives:
        if prim.startswith("0"):
            continue
        if prim.startswith("$"):
            name, expr = prim.split("=", 1)
            v[int(name[1:])] = _eval_expr(expr, v)
            continue
        fields = [_eval_expr(x, v) for x in prim.split(",")]
        code = int(fields[0])
        a = fields[1:]
        if code == 1:  # circle: exposure, diameter, x, y[, rot]
            if a[0] == 0:
                continue
            c = _rotate([(a[2], a[3])], a[4] if len(a) > 4 else 0)[0]
            pts += _circle_points(c[0], c[1], a[1] / 2)
        elif code in (2, 20):  # vector line: exp, width, sx, sy, ex, ey, rot
            if a[0] == 0:
                continue
            (sx, sy), (ex, ey), w = (a[2], a[3]), (a[4], a[5]), a[1]
            ang = math.atan2(ey - sy, ex - sx)
            nx, ny = -math.sin(ang) * w / 2, math.cos(ang) * w / 2
            pts += _rotate([(sx + nx, sy + ny), (ex + nx, ey + ny), (ex - nx, ey - ny), (sx - nx, sy - ny)], a[6])
        elif code == 21:  # centre line: exp, w, h, cx, cy, rot
            if a[0] == 0:
                continue
            w, h, cx, cy = a[1], a[2], a[3], a[4]
            pts += _rotate([(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2),
                            (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)], a[5])
        elif code == 4:  # outline: exp, n, x0, y0, ... , rot
            if a[0] == 0:
                continue
            n = int(a[1])
            coords = a[2:2 + 2 * (n + 1)]
            rot = a[2 + 2 * (n + 1)] if len(a) > 2 + 2 * (n + 1) else 0
            pts += _rotate([(coords[i], coords[i + 1]) for i in range(0, len(coords), 2)], rot)
        elif code == 5:  # polygon: exp, n, cx, cy, diameter, rot
            if a[0] == 0:
                continue
            n, cx, cy, r = int(a[1]), a[2], a[3], a[4] / 2
            poly = [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)) for k in range(n)]
            pts += _rotate(poly, a[5] if len(a) > 5 else 0)
        elif code == 7:  # thermal: cx, cy, outer, inner, gap, rot -> outer circle
            pts += _circle_points(a[0], a[1], a[2] / 2)
    return pts


class _VarList(dict):
    def __init__(self, params):
        super().__init__((i + 1, p) for i, p in enumerate(params))

    def __getitem__(self, k):
        return self.get(k, 0.0)


def _aperture_outline(doc, ap):
    """Return ('circle', r) or ('poly', [points mm centred]) or None."""
    p = ap.params
    if ap.kind == "C" and p:
        return ("circle", p[0] / 2)
    if ap.kind == "R" and len(p) >= 2:
        return ("poly", [(-p[0] / 2, -p[1] / 2), (p[0] / 2, -p[1] / 2), (p[0] / 2, p[1] / 2), (-p[0] / 2, p[1] / 2)])
    if ap.kind == "O" and len(p) >= 2:
        w, h = p[0], p[1]
        r = min(w, h) / 2
        if w >= h:
            pts = _circle_points(-(w / 2 - r), 0, r) + _circle_points(w / 2 - r, 0, r)
        else:
            pts = _circle_points(0, -(h / 2 - r), r) + _circle_points(0, h / 2 - r, r)
        return ("poly", _convex_hull(pts))
    if ap.kind == "P" and len(p) >= 2:
        n = int(p[1])
        rot = p[2] if len(p) > 2 else 0
        pts = [(p[0] / 2 * math.cos(2 * math.pi * k / n), p[0] / 2 * math.sin(2 * math.pi * k / n)) for k in range(n)]
        return ("poly", _rotate(pts, rot))
    if ap.kind in doc.macros:
        # Macro parameters are stored in mm already; only lengths are scaled
        # for inch files, which KiCad never emits.
        pts = _macro_points(doc.macros[ap.kind], p)
        hull = _convex_hull(pts)
        return ("poly", hull) if len(hull) >= 3 else None
    return None


def _poly_path(points):
    d = "".join(("M {} {} " if i == 0 else "L {} {} ").format(f(x), f(y)) for i, (x, y) in enumerate(points))
    return d + "Z "


def _circle_path(cx, cy, r):
    return "M {a} {y} A {r} {r} 0 0 0 {b} {y} {r} {r} 0 0 0 {a} {y} Z ".format(
        a=f(cx + r), b=f(cx - r), y=f(cy), r=f(r))


def _arc_cmd(start, end, arc):
    """SVG arc from gerber arc (start/end/centre in mm). Full circles split in two."""
    cx, cy, clockwise = arc
    r = math.hypot(start[0] - cx, start[1] - cy)
    a0 = math.atan2(start[1] - cy, start[0] - cx)
    a1 = math.atan2(end[1] - cy, end[0] - cx)
    span = (a0 - a1) if clockwise else (a1 - a0)
    span %= 2 * math.pi
    if span < 1e-9:
        span = 2 * math.pi
    sweep = 1 if clockwise else 0
    rs = f(r / UNIT)
    if span > math.pi + 1e-9 and abs(span - 2 * math.pi) < 1e-9:
        mid = (2 * cx - start[0], 2 * cy - start[1])
        mx, my = to_svg(*mid)
        ex, ey = to_svg(*end)
        return "A {r} {r} 0 0 {s} {mx} {my} {r} {r} 0 0 {s} {ex} {ey} ".format(
            r=rs, s=sweep, mx=f(mx), my=f(my), ex=f(ex), ey=f(ey))
    ex, ey = to_svg(*end)
    return "A {r} {r} 0 {l} {s} {ex} {ey} ".format(r=rs, l=1 if span > math.pi else 0, s=sweep, ex=f(ex), ey=f(ey))


def _stadium(start, end, width):
    r = width / 2
    if r <= 0:
        return None
    pts = _circle_points(start[0], start[1], r, 24) + _circle_points(end[0], end[1], r, 24)
    return [to_svg(x, y) for x, y in _convex_hull(pts)]


def _exact_paths(doc, warnings):
    items = []          # (svg path d, polygon in SVG units) - polygon used for overlap tests
    centres = []        # flash centres: every pad must stay open
    unknown = set()
    for flash in doc.flashes:
        ap = flash.aperture
        if ap is None:
            continue
        try:
            outline = _aperture_outline(doc, ap)
        except Exception as e:
            raise ColorSilkError("E_MASK_PARSE", "Ouverture '{}' illisible : {}".format(ap.kind, e))
        if outline is None:
            unknown.add(ap.kind)
            continue
        cx, cy = to_svg(flash.x, flash.y)
        centres.append((cx, cy))
        if outline[0] == "circle":
            r = outline[1] / UNIT
            items.append((_circle_path(cx, cy, r), _circle_points(cx, cy, r)))
        else:
            poly = [to_svg(flash.x + x, flash.y + y) for x, y in outline[1]]
            items.append((_poly_path(poly), poly))

    for region in doc.regions:
        sx, sy = to_svg(*region.segments[0][0])
        d = "M {} {} ".format(f(sx), f(sy))
        poly = [(sx, sy)]
        for start, end, arc in region.segments:
            if arc:
                d += _arc_cmd(start, end, arc)
                poly += [to_svg(*q) for q in _sample_arc(start, end, arc)[1:]]
            else:
                ex, ey = to_svg(*end)
                d += "L {} {} ".format(f(ex), f(ey))
                poly.append((ex, ey))
        if len(poly) >= 3:
            items.append((d + "Z ", poly))

    for stroke in doc.strokes:
        ap = stroke.aperture
        if ap is None or ap.kind != "C" or not ap.params:
            continue
        pts = _sample_arc(stroke.start, stroke.end, stroke.arc) if stroke.arc else [stroke.start, stroke.end]
        for a, b in zip(pts, pts[1:]):
            poly = _stadium(a, b, ap.params[0])
            if poly:
                items.append((_poly_path(poly), poly))

    if unknown:
        warnings.append({"code": "W_MASK_APERTURE",
                         "message": "Ouvertures de masque ignorées (forme inconnue) : " + ", ".join(sorted(unknown))})

    # Even-odd clip: overlapping openings would cancel and get ink. Merge them first.
    shapes, polys, stats = merge_openings(items)
    if stats["duplicates_removed"] or stats["groups_merged"] or stats["contained_removed"]:
        warnings.append({"code": "I_MASK_MERGED",
                         "message": "Ouvertures de masque superposées fusionnées : {} doublon(s) retiré(s) (ex. pastilles "
                                    "USB-C empilées), {} ouverture(s) incluse(s) dans une autre, {} groupe(s) unifié(s)."
                                    .format(stats["duplicates_removed"], stats["contained_removed"], stats["groups_merged"])})
    bad = covered_points(centres, polys)
    if bad:
        warnings.append({"code": "E_MASK_COVERED",
                         "message": "{} pastille(s) resteraient sous l'encre couleur.".format(len(bad)),
                         "points_mm": [[round(x * UNIT, 3), round(-y * UNIT, 3)] for x, y in bad]})
    warnings.append({"code": "I_MASK_POLYGONS", "polygons": polys, "centres": centres})  # for checks/tests
    return shapes


def _sample_arc(start, end, arc):
    cx, cy, clockwise = arc
    r = math.hypot(start[0] - cx, start[1] - cy)
    a0 = math.atan2(start[1] - cy, start[0] - cx)
    a1 = math.atan2(end[1] - cy, end[0] - cx)
    span = ((a0 - a1) if clockwise else (a1 - a0)) % (2 * math.pi) or 2 * math.pi
    n = max(2, int(span / (math.pi / 16)) + 1)
    sign = -1 if clockwise else 1
    return [(cx + r * math.cos(a0 + sign * span * k / n), cy + r * math.sin(a0 + sign * span * k / n))
            for k in range(n + 1)]
