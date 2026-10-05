"""Colour silkscreen SVG documents (port of TransJLC colorful/svg.rs).

Frame: 10-mil units, Y inverted (SVG y = -gerber y). Output layout reproduces
Rust's `xmlwriter` (indent 2, one attribute per line) so the TransJLC profile
can be compared byte for byte.
"""
from .numfmt import f

UNIT = 0.254
SVG_HEADER = '<?xml version="1.0" encoding="UTF-8" standalone="no"?>'
EDA_VERSION = "1.6(2025-08-27)"
CLIP_MARGIN = 0.8374  # shrink, 10-mil units (same value as the EasyEDA sample)
EXPAND = 0.5          # expand, 10-mil units

# Registration mark inset. TransJLC uses 0.0762 mm (3 mil); the genuine EasyEDA
# sample in TransJLC's test data shows 3 units of 10 mil (0.762 mm). [À VÉRIFIER]
MARK_INSET_MM = 0.0762


def mil10(mm):
    return mm / UNIT


def mark_points(bounds, inset_mm=MARK_INSET_MM):
    min_x, max_x = bounds.min_x + inset_mm, bounds.max_x - inset_mm
    min_y, max_y = bounds.min_y + inset_mm, bounds.max_y - inset_mm
    return [(min_x, min_y), (min_x, max_y), (max_x, max_y)]


class _XmlWriter:
    def __init__(self):
        self.out = []
        self.stack = []        # [name, has_children]
        self.open_tag = False

    def start(self, name):
        if self.open_tag:
            self.out.append(">")
            self.open_tag = False
        if self.stack:
            self.stack[-1][1] = True
        if self.out:
            self.out.append("\n")
        self.out.append("  " * len(self.stack) + "<" + name)
        self.stack.append([name, False])
        self.open_tag = True

    def attr(self, name, value):
        value = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        self.out.append("\n" + "  " * len(self.stack) + '{}="{}"'.format(name, value))

    def end(self):
        name, has_children = self.stack.pop()
        if self.open_tag:
            self.out.append("/>")
            self.open_tag = False
        else:
            self.out.append("\n" + "  " * len(self.stack) + "</{}>".format(name))

    def document(self):
        while self.stack:
            self.end()
        return SVG_HEADER + "\n" + "".join(self.out) + "\n"


def _rect_d(x0, y0, x1, y1, x2, y2, x3, y3):
    return "M {} {} L {} {} {} {} {} {} {} {} ".format(
        f(x0), f(y0), f(x1), f(y1), f(x2), f(y2), f(x3), f(y3), f(x0), f(y0))


def _frame(bounds):
    min_x, max_x = mil10(bounds.min_x), mil10(bounds.max_x)
    min_y, max_y = -mil10(bounds.max_y), -mil10(bounds.min_y)
    return min_x, max_x, min_y, max_y, mil10(bounds.width), mil10(bounds.height)


def _silkscreen_svg(bounds, image, mask_paths, bottom, inset_mm):
    min_x, max_x, min_y, max_y, w, h = _frame(bounds)
    marks = " ".join("{} {}".format(f(mil10(x)), f(mil10(y))) for x, y in mark_points(bounds, inset_mm))

    xw = _XmlWriter()
    xw.start("svg")
    xw.attr("width", "{}mm".format(f(bounds.width)))
    xw.attr("height", "{}mm".format(f(bounds.height)))
    box = "{} {} {} {}".format(f(min_x), f(min_y), f(w), f(h))
    xw.attr("boardBox", box)
    xw.attr("viewBox", box)
    xw.attr("version", "1.1")
    xw.attr("eda-version", EDA_VERSION)
    xw.attr("mark-points", marks)
    xw.attr("xmlns:inkscape", "http://www.inkscape.org/namespaces/inkscape")
    xw.attr("xmlns:sodipodi", "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd")
    xw.attr("xmlns:xlink", "http://www.w3.org/1999/xlink")
    xw.attr("xmlns", "http://www.w3.org/2000/svg")
    xw.attr("xmlns:svg", "http://www.w3.org/2000/svg")

    m = CLIP_MARGIN
    xw.start("defs")
    xw.start("clipPath")
    xw.attr("id", "clipPath0")
    xw.start("path")
    xw.attr("d", _rect_d(max_x - m, max_y - m, min_x + m, max_y - m, min_x + m, min_y + m, max_x - m, min_y + m))
    xw.attr("id", "outline0")
    xw.attr("stroke", "none")
    xw.attr("style", "fill-opacity:1;fill-rule:nonzero;fill:block;")
    xw.end()
    xw.end()
    xw.end()

    e = EXPAND
    xw.start("defs")
    xw.start("clipPath")
    xw.attr("id", "clipPath1")
    xw.attr("clip-path", "url(#clipPath0)")
    xw.start("path")
    xw.attr("d", _rect_d(max_x + e, min_y - e, max_x + e, max_y + e, min_x - e, max_y + e, min_x - e, min_y - e)
            + "".join(mask_paths))
    xw.attr("id", "solder1")
    xw.attr("stroke", "none")
    xw.attr("style", "fill-opacity:1;fill-rule:evenodd;clip-rule:evenodd;fill:block;")
    xw.end()
    xw.end()
    xw.end()

    xw.start("g")
    xw.attr("clip-path", "url(#clipPath1)")
    if bottom:
        center_x = min_x + w / 2.0
        xw.attr("transform", "scale(-1 1) translate({} 0)".format(f(-2.0 * center_x)))
    else:
        xw.attr("transform", "scale(1 1) translate(0 0)")

    xw.start("path")
    xw.attr("d", _rect_d(min_x - e, max_y + e, min_x - e, min_y - e, max_x + e, min_y - e, max_x + e, max_y + e))
    xw.attr("fill", "#FFFFFF")
    xw.attr("stroke", "none")
    xw.attr("stroke-width", "0")
    xw.attr("id", "background")
    xw.end()

    xw.start("image")
    xw.attr("width", str(image.width))
    xw.attr("height", str(image.height))
    xw.attr("preserveAspectRatio", "none")
    xw.attr("xlink:href", image.data_uri)
    sx, sy = w / image.width, h / image.height
    if bottom:
        xw.attr("transform", "matrix({} 0 0 {} {} {})".format(f(-sx), f(sy), f(max_x), f(min_y)))
    else:
        xw.attr("transform", "matrix({} 0 0 {} {} {})".format(f(sx), f(sy), f(min_x), f(min_y)))
    xw.end()
    return xw.document()


def build_top_svg(bounds, image, mask_paths, inset_mm=MARK_INSET_MM):
    return _silkscreen_svg(bounds, image, mask_paths, False, inset_mm)


def build_bottom_svg(bounds, image, mask_paths, inset_mm=MARK_INSET_MM):
    """Image is given as seen when looking at the bottom face; the group mirrors it."""
    return _silkscreen_svg(bounds, image, mask_paths, True, inset_mm)


def build_board_outline_svg(bounds, profile="default"):
    """`default` uses the same Y-inverted frame as the silkscreen SVGs;
    `transjlc` keeps TransJLC's non-inverted origin (min_x, min_y)."""
    w, h = mil10(bounds.width), mil10(bounds.height)
    ox = mil10(bounds.min_x)
    oy = mil10(bounds.min_y) if profile == "transjlc" else -mil10(bounds.max_y)
    xw = _XmlWriter()
    xw.start("svg")
    xw.attr("width", "{}mm".format(f(bounds.width)))
    xw.attr("height", "{}mm".format(f(bounds.height)))
    xw.attr("viewBox", "{} {} {} {}".format(f(ox), f(oy), f(w), f(h)))
    xw.attr("version", "1.1")
    xw.attr("xmlns", "http://www.w3.org/2000/svg")
    xw.attr("xmlns:svg", "http://www.w3.org/2000/svg")
    xw.start("rect")
    xw.attr("x", f(ox))
    xw.attr("y", f(oy))
    xw.attr("width", f(w))
    xw.attr("height", f(h))
    xw.attr("fill", "none")
    xw.attr("stroke", "#00AA00")
    xw.attr("stroke-width", "1")
    xw.end()
    return xw.document()
