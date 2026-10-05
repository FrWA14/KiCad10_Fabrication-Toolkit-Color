"""Board outline bounds from the Edge.Cuts Gerber (port of TransJLC parse_outline_bounds)."""
from . import gerber
from .errors import ColorSilkError


class BoardBounds:
    """Outline bounding box in Gerber millimetres (Y up)."""

    def __init__(self, min_x, min_y, max_x, max_y):
        self.min_x, self.min_y, self.max_x, self.max_y = min_x, min_y, max_x, max_y

    @property
    def width(self):
        return self.max_x - self.min_x

    @property
    def height(self):
        return self.max_y - self.min_y

    def as_list(self):
        return [round(v, 6) for v in (self.min_x, self.min_y, self.max_x, self.max_y)]

    def __repr__(self):
        return "BoardBounds({})".format(self.as_list())


def parse_outline_bounds(text, include_arc_extrema=True):
    """`include_arc_extrema=False` reproduces TransJLC (arc endpoints only)."""
    if not text or not text.strip():
        raise ColorSilkError("E_OUTLINE_MISSING", "Le Gerber du contour (Edge.Cuts) est vide.")
    doc = gerber.parse(text, "E_OUTLINE_PARSE")
    points = list(doc.points)
    if include_arc_extrema:
        for start, end, cx, cy, cw in doc.arcs:
            points.extend(gerber.arc_extrema(start, end, cx, cy, cw))
    if not points:
        raise ColorSilkError("E_OUTLINE_MISSING",
                             "Aucun tracé dans le Gerber du contour : la couche Edge.Cuts est vide.")
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    bounds = BoardBounds(min(xs), min(ys), max(xs), max(ys))
    if bounds.width <= 0 or bounds.height <= 0:
        raise ColorSilkError("E_OUTLINE_PARSE",
                             "Contour dégénéré ({:.3f} x {:.3f} mm).".format(bounds.width, bounds.height))
    return bounds
