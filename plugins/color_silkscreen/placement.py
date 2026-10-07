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
import re

from .board_view import side_geometry
from .errors import ColorSilkError  # noqa: F401  (re-exported for the editor)

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


def normalize_silk(silk):
    """{"enabled": bool, "color": "#RRGGBB"} -> same, validated; None when disabled."""
    if not silk or not silk.get("enabled"):
        return None
    color = str(silk.get("color") or "#000000").strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ColorSilkError("E_PLACEMENT", "Couleur de sérigraphie invalide : {} (format #RRGGBB).".format(color))
    return {"enabled": True, "color": color.upper()}


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


def normalize_offset(offset):
    """(dx, dy) printing correction in mm, view frame of the face; None/0 = no correction."""
    if not offset:
        return (0.0, 0.0)
    dx, dy = float(offset[0]), float(offset[1])
    if abs(dx) > 5 or abs(dy) > 5:
        raise ColorSilkError("E_PLACEMENT", "Correction d'impression trop grande ({:.2f}, {:.2f} mm, max 5 mm).".format(dx, dy))
    return (dx, dy)


def compose(view, side, placement, dpi=DPI, silk=None, offset=None, calibration=False):
    """Return an RGBA PIL image covering the outline box at `dpi`, clipped to the outline.

    `placement` may be None (no picture on this face). `silk` ({"enabled", "color"})
    paints the face's F/B.Silkscreen into the image in that colour, on top of the
    picture: with the colour process the conventional white silkscreen is not
    printed, so this is how texts and logos still appear on the board."""
    from PIL import Image, ImageChops, ImageDraw, ImageOps

    p = normalize(placement)
    silk = normalize_silk(silk)
    dx, dy = normalize_offset(offset)
    geo = side_geometry(view, side)
    scale = dpi / 25.4
    cw, ch = max(1, round(view["width"] * scale)), max(1, round(view["height"] * scale))
    canvas = Image.new("RGBA", (cw, ch), (255, 255, 255, 0))
    # The printing correction moves the artwork only; the outline clip stays where the board is.
    if p:
        _paste_image(canvas, dict(p, cx=p["cx"] + dx, cy=p["cy"] + dy), scale)
    if silk and geo["silk"]:
        rgb = tuple(int(silk["color"][i:i + 2], 16) for i in (1, 3, 5))
        draw = ImageDraw.Draw(canvas)
        for chain in geo["silk"]:
            if len(chain) >= 3:
                draw.polygon([((x + dx) * scale, (y + dy) * scale) for x, y in chain], fill=rgb + (255,))
    if calibration:
        _draw_calibration(canvas, geo, side, scale, dx, dy)

    mask = Image.new("L", (cw, ch), 0)
    draw = ImageDraw.Draw(mask)
    for outline in geo["outlines"]:
        draw.polygon([(x * scale, y * scale) for x, y in outline], fill=255)
    for hole in geo["holes"]:
        draw.polygon([(x * scale, y * scale) for x, y in hole], fill=0)
    canvas.putalpha(ImageChops.multiply(canvas.getchannel("A"), mask))
    return canvas


def _draw_calibration(canvas, geo, side, scale, dx, dy):
    """Registration test pattern: thin crosshairs and rings centred on every bare-copper
    pad of the face, 1 mm rulers along the edges, a face label and a +X arrow.
    In the JLCPCB Gerber Viewer an offset shows as crosshairs off the pad centres."""
    from PIL import ImageDraw, ImageFont
    draw = ImageDraw.Draw(canvas)
    lw = max(1, round(0.08 * scale))
    red, blue, black = (220, 0, 0, 255), (0, 70, 220, 255), (0, 0, 0, 255)

    def P(x, y):
        return ((x + dx) * scale, (y + dy) * scale)

    w, h = geo["width"], geo["height"]
    for i in range(int(w) + 1):  # rulers: 1 mm ticks, longer every 5 / 10 mm
        tick = 2.0 if i % 10 == 0 else (1.2 if i % 5 == 0 else 0.6)
        draw.line([P(i, 1.5), P(i, 1.5 + tick)], fill=black, width=lw)
        draw.line([P(i, h - 1.5), P(i, h - 1.5 - tick)], fill=black, width=lw)
    for j in range(int(h) + 1):
        tick = 2.0 if j % 10 == 0 else (1.2 if j % 5 == 0 else 0.6)
        draw.line([P(1.5, j), P(1.5 + tick, j)], fill=black, width=lw)
        draw.line([P(w - 1.5, j), P(w - 1.5 - tick, j)], fill=black, width=lw)
    for pad in geo["pads"]:
        r = max(pad["w"], pad["h"]) / 2
        cx, cy = pad["x"], pad["y"]
        arm = r + 1.0
        draw.line([P(cx - arm, cy), P(cx + arm, cy)], fill=red, width=lw)
        draw.line([P(cx, cy - arm), P(cx, cy + arm)], fill=red, width=lw)
        x0, y0 = P(cx - r - 0.3, cy - r - 0.3)
        x1, y1 = P(cx + r + 0.3, cy + r + 0.3)
        draw.ellipse([x0, y0, x1, y1], outline=blue, width=lw)
    try:
        font = ImageFont.load_default(size=round(3.0 * scale))
    except TypeError:  # Pillow < 10.1
        font = ImageFont.load_default()
    label = "TOP (vue de dessus)" if side == "top" else "BOTTOM (vue de dessous)"
    draw.text(P(w / 2 - 14, h / 2 - 2), label, fill=black, font=font)
    ax, ay = w / 2 - 6, h / 2 + 4  # +X arrow: shows whether the face is mirrored
    draw.line([P(ax, ay), P(ax + 12, ay)], fill=black, width=lw * 3)
    draw.polygon([P(ax + 12, ay - 1), P(ax + 14, ay), P(ax + 12, ay + 1)], fill=black)
    draw.text(P(ax + 15, ay - 1.8), "+X", fill=black, font=font)


def _paste_image(canvas, p, scale):
    from PIL import Image, ImageOps
    cw, ch = canvas.size
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


def save_placements(path, placements, view, silk=None):
    data = {"board_mm": [view["width"], view["height"]], "origin_mm": list(view["origin_mm"]),
            "frame": "mm, origine coin haut-gauche du contour, Y vers le bas ; dessous vu de dessous"}
    data.update({side: placements[side] for side in ("top", "bottom") if placements.get(side)})
    silk = {side: normalize_silk((silk or {}).get(side)) for side in ("top", "bottom")}
    if any(silk.values()):
        data["silk"] = {side: v for side, v in silk.items() if v}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def load_placements(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return {side: normalize(data.get(side)) for side in ("top", "bottom")}


def load_silk(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh).get("silk") or {}
    return {side: normalize_silk(data.get(side)) for side in ("top", "bottom")}


def preview_bytes(canvas, max_px=1024):
    """Small PNG of a composite (for UI/tests)."""
    im = canvas.copy()
    im.thumbnail((max_px, max_px))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()
