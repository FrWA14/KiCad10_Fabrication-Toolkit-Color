"""Load and validate the user's image, then embed it as a base64 data URI."""
import base64
import io
import os

from .errors import ColorSilkError

MIN_PIXELS = 32           # below this on either axis: E_IMAGE_TOO_SMALL
LOW_DPI = 150             # below this: warning
PRINTER_DPI = 1200        # JLCPCB UV printer resolution
MAX_AXIS = 8192           # per-image limit observed by Overprint
MAX_PIXELS = 40000000
ASPECT_TOLERANCE = 0.02


class SilkscreenImage:
    def __init__(self, width, height, data_uri, fmt, source_bytes):
        self.width, self.height = width, height
        self.data_uri = data_uri
        self.format = fmt
        self.bytes = source_bytes


def _sniff(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    return None


def load_image(path, board_w_mm, board_h_mm, warnings, fit="stretch", profile="default"):
    if not path or not os.path.isfile(path):
        raise ColorSilkError("E_IMAGE_MISSING", "Image introuvable : {}".format(path))
    with open(path, "rb") as fh:
        data = fh.read()
    fmt = _sniff(data)
    if fmt is None:
        raise ColorSilkError("E_IMAGE_FORMAT",
                             "'{}' n'est ni un PNG ni un JPG.".format(os.path.basename(path)))
    try:
        from PIL import Image, ImageOps
    except ImportError:
        Image = None

    if Image is None:
        width, height = _dimensions_without_pil(data, fmt)
        _check_size(width, height, path)
        warnings.append({"code": "W_NO_PILLOW", "message": "Pillow absent : image utilisée telle quelle."})
    else:
        try:
            img = Image.open(io.BytesIO(data))
            img.load()
        except Exception as e:
            raise ColorSilkError("E_IMAGE_FORMAT", "Image illisible ({}) : {}".format(os.path.basename(path), e))
        width, height = img.size
        _check_size(width, height, path)
        data, width, height = _prepare(img, data, fmt, board_w_mm, board_h_mm, warnings, fit, ImageOps)

    dpi = min(width / (board_w_mm / 25.4), height / (board_h_mm / 25.4))
    if dpi < LOW_DPI:
        warnings.append({"code": "W_IMAGE_LOW_DPI",
                         "message": "Résolution effective {:.0f} DPI (< {}) : impression floue probable ; "
                                    "viser {} DPI, soit {}x{} px.".format(
                                        dpi, LOW_DPI, PRINTER_DPI,
                                        round(board_w_mm / 25.4 * PRINTER_DPI), round(board_h_mm / 25.4 * PRINTER_DPI))})

    if profile == "transjlc":
        mime = "image/" + (os.path.splitext(path)[1].lstrip(".").lower() or "png")
    else:
        mime = "image/" + fmt
    uri = "data:{};base64,{}".format(mime, base64.b64encode(data).decode("ascii"))
    return SilkscreenImage(width, height, uri, fmt, data)


def _check_size(width, height, path):
    if width < MIN_PIXELS or height < MIN_PIXELS:
        raise ColorSilkError("E_IMAGE_TOO_SMALL", "{} ne fait que {}x{} px (minimum {} px par côté).".format(
            os.path.basename(path), width, height, MIN_PIXELS))


def _prepare(img, data, fmt, board_w_mm, board_h_mm, warnings, fit, ImageOps):
    """Return (bytes, width, height), re-encoding only when something must change."""
    changed = False

    if fmt == "jpeg":
        orientation = img.getexif().get(0x0112, 1) if hasattr(img, "getexif") else 1
        if orientation != 1:
            img = ImageOps.exif_transpose(img)
            changed = True
            warnings.append({"code": "W_IMAGE_EXIF", "message": "Orientation EXIF appliquée."})
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
            changed = True

    board_ratio = board_w_mm / board_h_mm
    ratio = img.size[0] / img.size[1]
    if abs(ratio / board_ratio - 1) > ASPECT_TOLERANCE:
        if fit == "contain":
            img = _pad_to_ratio(img, board_ratio, fmt)
            changed = True
            warnings.append({"code": "W_IMAGE_PADDED",
                             "message": "Image complétée par des marges pour respecter les proportions de la carte."})
        else:
            warnings.append({"code": "W_IMAGE_ASPECT",
                             "message": "Proportions image {:.3f} ≠ carte {:.3f} : l'image sera déformée "
                                        "(option fit=contain pour ajouter des marges).".format(ratio, board_ratio)})

    w, h = img.size
    target_w = round(board_w_mm / 25.4 * PRINTER_DPI)
    target_h = round(board_h_mm / 25.4 * PRINTER_DPI)
    scale = min(1.0, target_w / w, target_h / h, MAX_AXIS / max(w, h), (MAX_PIXELS / (w * h)) ** 0.5)
    if scale < 1.0:
        new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
        resample = getattr(getattr(img, "Resampling", img), "LANCZOS", 1)
        img = img.resize(new_size, resample)
        changed = True
        warnings.append({"code": "W_IMAGE_RESAMPLED",
                         "message": "Image réduite de {}x{} à {}x{} px (plafond {} DPI / limites JLCPCB).".format(
                             w, h, new_size[0], new_size[1], PRINTER_DPI)})

    if not changed:
        return data, img.size[0], img.size[1]
    out = io.BytesIO()
    if fmt == "png":
        img.save(out, "PNG", optimize=True)
    else:
        img.save(out, "JPEG", quality=95, subsampling=0)
    return out.getvalue(), img.size[0], img.size[1]


def _pad_to_ratio(img, ratio, fmt):
    from PIL import Image
    w, h = img.size
    if w / h < ratio:
        new = (round(h * ratio), h)
    else:
        new = (w, round(w / ratio))
    if fmt == "png":
        canvas = Image.new("RGBA", new, (255, 255, 255, 0))
        src = img.convert("RGBA")
    else:
        canvas = Image.new("RGB", new, (255, 255, 255))
        src = img.convert("RGB")
    canvas.paste(src, ((new[0] - w) // 2, (new[1] - h) // 2))
    return canvas


def _dimensions_without_pil(data, fmt):
    if fmt == "png":
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    i = 2
    while i < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        length = int.from_bytes(data[i + 2:i + 4], "big")
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            return int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")
        i += 2 + length
    raise ColorSilkError("E_IMAGE_FORMAT", "JPG sans dimensions lisibles.")
