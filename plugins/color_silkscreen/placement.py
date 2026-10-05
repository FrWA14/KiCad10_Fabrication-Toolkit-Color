"""Image placement on a board face, and the board-sized composite sent to JLCPCB.

A placement lives in the side's view frame (see board_view): millimetres,
origin at the outline's top-left, Y down, bottom face seen from below.

    {"image": "C:/.../logo.png", "cx": 38.0, "cy": 30.0, "w": 40.0, "h": 24.0, "rot": 0}

`compose` renders the image at 1200 DPI on a canvas covering the outline's
bounding box, then makes every pixel outside the closed Edge.Cuts outline (or
inside a cut-out) transparent. The result has the board's exact aspect ratio,
so the colour pipeline maps it 1:1 onto the Gerber outline.
"""
import io
import json
import os

from .board_view import side_geometry
from .errors import ColorSilkError

DPI = 1200
MAX_PNG_BYTES = 3 * 1024 * 1024  # larger composites are written as JPEG (white = no ink anyway)


def normalize(p):
    if not p or not p.get("image"):
        return None
    out = {"image": p["image"], "cx": float(p["cx"]), "cy": float(p["cy"]),
           "w": float(p["w"]), "h": float(p["h"]), "rot": int(p.get("rot", 0)) % 360}
    if out["rot"] not in (0, 90, 180, 270):
        raise ColorSilkError("E_PLACEMENT", "Rotation {} non supportée (0/90/180/270).".format(out["rot"]))
    if out["w"] <= 0 or out["h"] <= 0:
        raise ColorSilkError("E_PLACEMENT", "Taille d'image nulle ou négative.")
    return out


def rotated_size(px_w, px_h, rot):
    return (px_h, px_w) if rot in (90, 270) else (px_w, px_h)


def fit(view, image_px, rot=0, mode="contain", margin_mm=0.0):
    """Centred placement that fits ('contain') or covers ('cover') the outline box."""
    iw, ih = rotated_size(image_px[0], image_px[1], rot)
    bw, bh = view["width"] - 2 * margin_mm, view["height"] - 2 * margin_mm
    k = (min if mode == "contain" else max)(bw / iw, bh / ih)
    return {"cx": view["width"] / 2, "cy": view["height"] / 2, "w": iw * k, "h": ih * k, "rot": rot}


def effective_dpi(placement, image_px):
    iw, ih = rotated_size(image_px[0], image_px[1], placement["rot"])
    return min(iw / (placement["w"] / 25.4), ih / (placement["h"] / 25.4))


def _open(path):
    from PIL import Image
    if not os.path.isfile(path):
        raise ColorSilkError("E_IMAGE_MISSING", "Image introuvable : {}".format(path))
    try:
        img = Image.open(path)
        img.load()
    except Exception as e:
        raise ColorSilkError("E_IMAGE_FORMAT", "Image illisible ({}) : {}".format(os.path.basename(path), e))
    if (img.format or "").upper() not in ("PNG", "JPEG", "MPO"):
        raise ColorSilkError("E_IMAGE_FORMAT", "'{}' n'est ni un PNG ni un JPG.".format(os.path.basename(path)))
    return img


def compose(view, side, placement, dpi=DPI):
    """Return an RGBA PIL image covering the outline box at `dpi`, clipped to the outline."""
    from PIL import Image, ImageChops, ImageDraw, ImageOps

    p = normalize(placement)
    geo = side_geometry(view, side)
    scale = dpi / 25.4
    cw, ch = max(1, round(view["width"] * scale)), max(1, round(view["height"] * scale))
    canvas = Image.new("RGBA", (cw, ch), (255, 255, 255, 0))

    src = _open(p["image"])
    src = ImageOps.exif_transpose(src).convert("RGBA")
    if p["rot"]:
        src = src.transpose({90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180,
                             270: Image.Transpose.ROTATE_90}[p["rot"]])  # rot = clockwise degrees
    pw, ph = p["w"] * scale, p["h"] * scale
    left, top = (p["cx"] - p["w"] / 2) * scale, (p["cy"] - p["h"] / 2) * scale
    ix0, iy0 = max(0, int(left)), max(0, int(top))
    ix1, iy1 = min(cw, int(round(left + pw))), min(ch, int(round(top + ph)))
    if ix1 > ix0 and iy1 > iy0:
        sx, sy = src.width / pw, src.height / ph
        box = (min(max((ix0 - left) * sx, 0.0), src.width), min(max((iy0 - top) * sy, 0.0), src.height),
               min(max((ix1 - left) * sx, 0.0), src.width), min(max((iy1 - top) * sy, 0.0), src.height))
        part = src.resize((ix1 - ix0, iy1 - iy0), Image.Resampling.LANCZOS, box=box)
        canvas.paste(part, (ix0, iy0))

    mask = Image.new("L", (cw, ch), 0)
    draw = ImageDraw.Draw(mask)
    for outline in geo["outlines"]:
        draw.polygon([(x * scale, y * scale) for x, y in outline], fill=255)
    for hole in geo["holes"]:
        draw.polygon([(x * scale, y * scale) for x, y in hole], fill=0)
    canvas.putalpha(ImageChops.multiply(canvas.getchannel("A"), mask))
    return canvas


def save_composite(canvas, out_dir, side):
    """Write the clipped composite: PNG when small enough, else JPEG on white.
    Returns (pipeline_path, preview_png_path)."""
    from PIL import Image
    os.makedirs(out_dir, exist_ok=True)
    png = os.path.join(out_dir, "color_{}_composite.png".format(side))
    canvas.save(png, optimize=False, compress_level=6)
    if os.path.getsize(png) <= MAX_PNG_BYTES:
        return png, png
    flat = Image.new("RGB", canvas.size, (255, 255, 255))
    flat.paste(canvas, mask=canvas.getchannel("A"))
    jpg = os.path.join(out_dir, "color_{}_composite.jpg".format(side))
    flat.save(jpg, quality=95, subsampling=0)
    return jpg, png


def save_placements(path, placements, view):
    data = {"board_mm": [view["width"], view["height"]], "origin_mm": list(view["origin_mm"]),
            "frame": "mm, origine coin haut-gauche du contour, Y vers le bas ; dessous vu de dessous"}
    data.update({side: placements[side] for side in ("top", "bottom") if placements.get(side)})
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def load_placements(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return {side: normalize(data.get(side)) for side in ("top", "bottom")}


def preview_bytes(canvas, max_px=1024):
    """Small PNG of a composite (for UI/tests)."""
    im = canvas.copy()
    im.thumbnail((max_px, max_px))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()
