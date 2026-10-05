"""Plain-data snapshot of a board for the placement editor and the image compositor.

Frame ("board frame"): millimetres, origin at the top-left of the Edge.Cuts
polygon bounding box, Y down, seen from the TOP. That box is exactly the
Gerber outline bounds the colour SVG is fitted to.

The bottom face is shown and composed as seen from BELOW: x' = width - x.
Only `extract` needs pcbnew; everything else works on the returned dict.
"""
from .errors import ColorSilkError

SIDES = ("top", "bottom")


def extract(board):
    import pcbnew  # type: ignore

    polys = pcbnew.SHAPE_POLY_SET()
    ok = board.GetBoardPolygonOutlines(polys, False)
    if not ok or polys.OutlineCount() == 0:
        raise ColorSilkError("E_OUTLINE_MISSING", "Contour Edge.Cuts absent ou non fermé : impossible de placer l'image.")
    mm = pcbnew.ToMM

    def chain(line):
        return [(mm(line.CPoint(i).x), mm(line.CPoint(i).y)) for i in range(line.PointCount())]

    outlines, holes = [], []
    for i in range(polys.OutlineCount()):
        outlines.append(chain(polys.Outline(i)))
        for j in range(polys.HoleCount(i)):
            holes.append(chain(polys.Hole(i, j)))
    xs = [p[0] for o in outlines for p in o]
    ys = [p[1] for o in outlines for p in o]
    x0, y0 = min(xs), min(ys)
    width, height = max(xs) - x0, max(ys) - y0

    def local(p):
        return (round(p[0] - x0, 4), round(p[1] - y0, 4))

    pads = {"top": [], "bottom": []}
    for pad in board.GetPads():
        pos = local((mm(pad.GetX()), mm(pad.GetY())))
        bbox = pad.GetBoundingBox()
        size = (mm(bbox.GetWidth()), mm(bbox.GetHeight()))
        drill = mm(pad.GetDrillSize().x) if pad.HasHole() else 0.0
        try:
            round_shape = pad.GetShape(pcbnew.F_Cu) == pcbnew.PAD_SHAPE_CIRCLE
        except TypeError:  # older API without layer argument
            round_shape = pad.GetShape() == pcbnew.PAD_SHAPE_CIRCLE
        entry = {"x": pos[0], "y": pos[1], "w": round(size[0], 4), "h": round(size[1], 4),
                 "round": bool(round_shape), "drill": round(drill, 4)}
        if pad.IsOnLayer(pcbnew.F_Mask):
            pads["top"].append(entry)
        if pad.IsOnLayer(pcbnew.B_Mask):
            pads["bottom"].append(entry)

    footprints = {"top": [], "bottom": []}
    for fp in board.GetFootprints():
        bbox = fp.GetBoundingBox(False)
        a = local((mm(bbox.GetLeft()), mm(bbox.GetTop())))
        footprints["bottom" if fp.IsFlipped() else "top"].append(
            {"ref": fp.GetReference(), "x": a[0], "y": a[1],
             "w": round(mm(bbox.GetWidth()), 4), "h": round(mm(bbox.GetHeight()), 4)})

    return {
        "width": round(width, 4), "height": round(height, 4),
        "origin_mm": (round(x0, 4), round(y0, 4)),
        "outlines": [[local(p) for p in o] for o in outlines],
        "holes": [[local(p) for p in h] for h in holes],
        "pads": pads,
        "footprints": footprints,
    }


def view_x(view, side, x):
    return view["width"] - x if side == "bottom" else x


def side_geometry(view, side):
    """Outlines/holes/pads/footprints mapped to the side's view frame."""
    def pts(chain):
        return [(view_x(view, side, x), y) for x, y in chain]

    pads = [dict(p, x=view_x(view, side, p["x"])) for p in view["pads"][side]]
    fps = []
    for fp in view["footprints"][side]:
        x = view_x(view, side, fp["x"] + (fp["w"] if side == "bottom" else 0))
        fps.append(dict(fp, x=x))
    return {"outlines": [pts(o) for o in view["outlines"]], "holes": [pts(h) for h in view["holes"]],
            "pads": pads, "footprints": fps, "width": view["width"], "height": view["height"]}
