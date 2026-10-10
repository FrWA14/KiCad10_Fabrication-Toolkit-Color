"""JLCPCB-style preview rebuilt from the files actually put in the ZIP.

Layers (RGBA, same size, board view of the face; bottom seen from below):
  board   white solder mask inside the outline
  image   colour print: the composite sent in .FCTS/.FCBS, clipped like JLCPCB
          (outline, solder-mask openings)
  silk    conventional silkscreen Gerber (black on a white board)
  copper  bare copper = copper Gerber inside the mask openings (gold)
  drills  every hole of the drill files
  outline Edge.Cuts

The colour files are encrypted for JLCPCB, so the image layer uses the
composite PNG written next to the ZIP (exactly what was encrypted).
"""
import io
import re
import zipfile

from . import mask
from .outline import parse_outline_bounds

COLORS = {
    "background": (40, 42, 46, 255),
    "board": (246, 246, 244, 255),
    "silk": (15, 15, 15, 255),
    "copper": (214, 172, 70, 255),
    "drills": (226, 229, 234, 255),
    "outline": (0, 150, 60, 255),
}
LAYERS = ("board", "image", "silk", "copper", "drills", "outline")
GERBERS = {
    "top": {"copper": "Gerber_TopLayer.GTL", "mask": "Gerber_TopSolderMaskLayer.GTS", "silk": "Gerber_TopSilkscreenLayer.GTO"},
    "bottom": {"copper": "Gerber_BottomLayer.GBL", "mask": "Gerber_BottomSolderMaskLayer.GBS",
               "silk": "Gerber_BottomSilkscreenLayer.GBO"},
}


def read_zip(path):
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist()}


def parse_excellon(text):
    """[(x, y, x2, y2, diameter)] in mm; x2/y2 differ from x/y for G85 slots."""
    tools, holes, tool = {}, [], None
    inch = "INCH" in text.upper().split("%")[0]
    k = 25.4 if inch else 1.0
    for line in text.splitlines():
        line = line.strip()
        m = re.fullmatch(r"T(\d+)C([\d.]+).*", line)
        if m:
            tools[int(m.group(1))] = float(m.group(2)) * k
            continue
        m = re.fullmatch(r"T(\d+)", line)
        if m:
            tool = tools.get(int(m.group(1)))
            continue
        m = re.fullmatch(r"X([-\d.]+)Y([-\d.]+)(?:G85X([-\d.]+)Y([-\d.]+))?", line)
        if m and tool:
            x, y = float(m.group(1)) * k, float(m.group(2)) * k
            x2 = float(m.group(3)) * k if m.group(3) else x
            y2 = float(m.group(4)) * k if m.group(4) else y
            holes.append((x, y, x2, y2, tool))
    return holes


class Frame:
    """Gerber mm -> pixel of the face view."""

    def __init__(self, bounds, side, px_per_mm):
        self.b, self.side, self.k = bounds, side, px_per_mm
        self.size = (max(1, round(bounds.width * px_per_mm)), max(1, round(bounds.height * px_per_mm)))

    def __call__(self, x, y):
        vx = (self.b.max_x - x) if self.side == "bottom" else (x - self.b.min_x)
        return vx * self.k, (self.b.max_y - y) * self.k


def _fill(draw, frame, polys, colour):
    for poly in polys:
        if len(poly) >= 3:
            draw.polygon([frame(x, y) for x, y in poly], fill=colour)


def render_layers(files, side, composite=None, px_per_mm=16):
    """files: {name: bytes} from the ZIP. composite: path/PIL image of the colour print of that face."""
    from PIL import Image, ImageChops, ImageDraw

    def text(name):
        data = files.get(name)
        return data.decode("utf-8", "replace") if data else ""

    gko = text("Gerber_BoardOutlineLayer.GKO")
    bounds = parse_outline_bounds(gko)
    frame = Frame(bounds, side, px_per_mm)
    size = frame.size

    def new(mode="L"):
        return Image.new(mode, size, 0)

    # board: inside of the outline = not reachable from the image border
    edge = new()
    _fill(ImageDraw.Draw(edge), frame, mask.polygons_mm(gko), 255)
    outside = edge.copy()
    pad = Image.new("L", (size[0] + 2, size[1] + 2), 0)
    pad.paste(outside, (1, 1))
    ImageDraw.floodfill(pad, (0, 0), 128)
    board = pad.crop((1, 1, size[0] + 1, size[1] + 1)).point(lambda v: 0 if v == 128 else 255)

    names = GERBERS[side]
    openings = new()
    _fill(ImageDraw.Draw(openings), frame, mask.polygons_mm(text(names["mask"])), 255)
    holes = new()
    hd = ImageDraw.Draw(holes)
    for name in ("Drill_PTH_Through.DRL", "Drill_NPTH_Through.DRL", "Drill_PTH_Through_Via.DRL"):
        for x, y, x2, y2, d in parse_excellon(text(name)):
            r = d / 2 * px_per_mm
            for cx, cy in ({frame(x, y), frame(x2, y2)}):
                hd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
            if (x, y) != (x2, y2):
                hd.line([frame(x, y), frame(x2, y2)], fill=255, width=max(1, round(d * px_per_mm)))
    copper = new()
    _fill(ImageDraw.Draw(copper), frame, mask.polygons_mm(text(names["copper"])), 255)
    silk = new()
    _fill(ImageDraw.Draw(silk), frame, mask.polygons_mm(text(names["silk"])), 255)

    def solid(colour, alpha):
        layer = Image.new("RGBA", size, colour)
        layer.putalpha(alpha)
        return layer

    not_open = ImageChops.invert(openings)
    layers = {
        "board": solid(COLORS["board"], board),
        "silk": solid(COLORS["silk"], ImageChops.multiply(ImageChops.multiply(silk, not_open), board)),
        "copper": solid(COLORS["copper"], ImageChops.multiply(ImageChops.multiply(copper, openings), board)),
        "drills": solid(COLORS["drills"], holes),
        "outline": solid(COLORS["outline"], edge),
        "image": Image.new("RGBA", size, (0, 0, 0, 0)),
    }
    if composite is not None:
        img = Image.open(composite) if isinstance(composite, str) else composite
        img = img.convert("RGBA").resize(size, Image.Resampling.LANCZOS)
        clip = ImageChops.multiply(ImageChops.multiply(img.getchannel("A"), board), not_open)
        img.putalpha(clip)
        layers["image"] = img
    return layers, bounds


def compose(layers, visible=LAYERS):
    from PIL import Image
    size = layers["board"].size
    out = Image.new("RGBA", size, COLORS["background"])
    for name in LAYERS:
        if name in visible:
            out.alpha_composite(layers[name])
    return out


def render_zip(zip_path, composites, out_dir=None, px_per_mm=16):
    """Render both faces; returns {side: PIL image}. Saves preview_<side>.png in out_dir."""
    import os
    files = read_zip(zip_path)
    result = {}
    for side in ("top", "bottom"):
        layers, _ = render_layers(files, side, composites.get(side), px_per_mm)
        img = compose(layers)
        result[side] = img
        if out_dir:
            img.convert("RGB").save(os.path.join(out_dir, "preview_{}.png".format(side)))
    return result


def to_png_bytes(img):
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()
