"""Generate the T1..T7 test boards and test images.

Must run with KiCad's Python (needs pcbnew):
    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tests/make_boards.py
"""
import os
import sys

import pcbnew  # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
BOARDS = os.path.join(HERE, "boards")
IMAGES = os.path.join(HERE, "img")

# Board placed away from the page origin, like a real KiCad design.
OX, OY = 100.0, 80.0


def mm(v):
    return pcbnew.FromMM(v)


def pt(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


def new_board(layers=2):
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(layers)
    return board


def edge_segment(board, a, b):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetLayer(pcbnew.Edge_Cuts)
    s.SetWidth(mm(0.05))
    s.SetStart(pt(*a))
    s.SetEnd(pt(*b))
    board.Add(s)


def edge_arc(board, start, mid, end):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_ARC)
    s.SetLayer(pcbnew.Edge_Cuts)
    s.SetWidth(mm(0.05))
    s.SetArcGeometry(pt(*start), pt(*mid), pt(*end))
    board.Add(s)


def rect_outline(board, w, h, x=OX, y=OY):
    corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    for i in range(4):
        edge_segment(board, corners[i], corners[(i + 1) % 4])


def rounded_outline(board, w, h, r, x=OX, y=OY):
    import math
    k = r * (1 - 1 / math.sqrt(2))
    edge_segment(board, (x + r, y), (x + w - r, y))
    edge_arc(board, (x + w - r, y), (x + w - k, y + k), (x + w, y + r))
    edge_segment(board, (x + w, y + r), (x + w, y + h - r))
    edge_arc(board, (x + w, y + h - r), (x + w - k, y + h - k), (x + w - r, y + h))
    edge_segment(board, (x + w - r, y + h), (x + r, y + h))
    edge_arc(board, (x + r, y + h), (x + k, y + h - k), (x, y + h - r))
    edge_segment(board, (x, y + h - r), (x, y + r))
    edge_arc(board, (x, y + r), (x + k, y + k), (x + r, y))


def copper_rect(board, layer, x, y, w, h):
    """Filled copper rectangle so every face carries copper (JLCPCB requirement)."""
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_RECT)
    s.SetLayer(layer)
    s.SetFilled(True)
    s.SetWidth(0)
    s.SetStart(pt(x, y))
    s.SetEnd(pt(x + w, y + h))
    board.Add(s)


def smd_pad_and_via(board, x, y):
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference("R1")
    fp.SetValue("TEST")
    fp.SetPosition(pt(x, y))
    board.Add(fp)
    pad = pcbnew.PAD(fp)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetSize(pt(2.0, 1.2))
    pad.SetLayerSet(pcbnew.PAD.SMDMask())
    pad.SetNumber("1")
    pad.SetPosition(pt(x, y))
    fp.Add(pad)

    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pt(x + 6, y))
    via.SetDrill(mm(0.4))
    via.SetWidth(mm(0.8))
    board.Add(via)

    # Through-hole pad: mask opening on both faces.
    tht = pcbnew.PAD(fp)
    tht.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    tht.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    tht.SetSize(pt(1.8, 1.8))
    tht.SetDrillSize(pt(1.0, 1.0))
    tht.SetLayerSet(pcbnew.PAD.PTHMask())
    tht.SetNumber("2")
    tht.SetPosition(pt(x + 12, y))
    fp.Add(tht)

    # Rounded-rectangle and oval SMD pads: exercise the RoundRect macro and O aperture.
    rr = pcbnew.PAD(fp)
    rr.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT)
    rr.SetRoundRectRadiusRatio(0.25)
    rr.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    rr.SetSize(pt(1.6, 1.0))
    rr.SetLayerSet(pcbnew.PAD.SMDMask())
    rr.SetNumber("3")
    rr.SetPosition(pt(x, y + 5))
    fp.Add(rr)
    ov = pcbnew.PAD(fp)
    ov.SetShape(pcbnew.PAD_SHAPE_OVAL)
    ov.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    ov.SetSize(pt(2.4, 1.2))
    ov.SetLayerSet(pcbnew.PAD.SMDMask())
    ov.SetNumber("4")
    ov.SetPosition(pt(x + 6, y + 5))
    fp.Add(ov)


def save(board, name):
    path = os.path.join(BOARDS, name + ".kicad_pcb")
    pcbnew.SaveBoard(path, board)
    print("wrote", path)


def make_boards():
    os.makedirs(BOARDS, exist_ok=True)

    b = new_board()
    rect_outline(b, 50, 30)
    copper_rect(b, pcbnew.F_Cu, OX + 2, OY + 2, 3, 3)
    copper_rect(b, pcbnew.B_Cu, OX + 2, OY + 2, 3, 3)
    save(b, "T1")

    b = new_board()
    rect_outline(b, 50, 30)
    smd_pad_and_via(b, OX + 10, OY + 15)
    copper_rect(b, pcbnew.B_Cu, OX + 2, OY + 2, 3, 3)
    save(b, "T2")

    b = new_board()
    rounded_outline(b, 50, 30, 4)
    copper_rect(b, pcbnew.F_Cu, OX + 5, OY + 5, 3, 3)
    copper_rect(b, pcbnew.B_Cu, OX + 5, OY + 5, 3, 3)
    save(b, "T3")

    b = new_board()
    rect_outline(b, 50, 30)
    copper_rect(b, pcbnew.F_Cu, OX + 2, OY + 2, 3, 3)
    copper_rect(b, pcbnew.B_Cu, OX + 2, OY + 2, 3, 3)
    b.GetDesignSettings().SetAuxOrigin(pt(OX + 7.5, OY + 30))  # bottom-left-ish, offset
    save(b, "T4")

    b = new_board(layers=4)
    rect_outline(b, 50, 30)
    smd_pad_and_via(b, OX + 10, OY + 15)
    for layer in (pcbnew.B_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu):
        copper_rect(b, layer, OX + 2, OY + 2, 3, 3)
    save(b, "T5")

    b = new_board()
    copper_rect(b, pcbnew.F_Cu, OX + 2, OY + 2, 3, 3)
    save(b, "T6")

    b = new_board()
    rect_outline(b, 50, 30)
    smd_pad_and_via(b, OX + 10, OY + 15)
    copper_rect(b, pcbnew.B_Cu, OX + 2, OY + 2, 3, 3)
    hole = pcbnew.FOOTPRINT(b)
    hole.SetReference("H1")
    hole.SetValue("MountingHole_Pad")
    hole.SetPosition(pt(OX + 42, OY + 8))
    hole.SetAttributes(pcbnew.FP_EXCLUDE_FROM_BOM)  # NOT excluded from position files
    b.Add(hole)
    ring = pcbnew.PAD(hole)
    ring.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    ring.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    ring.SetSize(pt(6.4, 6.4))
    ring.SetDrillSize(pt(3.2, 3.2))
    ring.SetLayerSet(pcbnew.PAD.PTHMask())
    ring.SetNumber("1")
    ring.SetPosition(pt(OX + 42, OY + 8))
    hole.Add(ring)
    save(b, "T8")

    b = new_board()
    rect_outline(b, 100, 100)
    smd_pad_and_via(b, OX + 20, OY + 50)
    copper_rect(b, pcbnew.B_Cu, OX + 2, OY + 2, 3, 3)
    save(b, "T7")


def make_images():
    from PIL import Image, ImageDraw

    os.makedirs(IMAGES, exist_ok=True)

    def gradient(w, h, mode="RGB"):
        img = Image.new(mode, (w, h))
        d = ImageDraw.Draw(img)
        for i in range(0, w, max(1, w // 64)):
            c = (255 * i // w, 128, 255 - 255 * i // w)
            d.rectangle([i, 0, i + w // 64, h], fill=c + ((255,) if mode == "RGBA" else ()))
        # Orientation marker: red square top-left, green bottom-right.
        d.rectangle([0, 0, w // 8, h // 8], fill=(255, 0, 0) + ((255,) if mode == "RGBA" else ()))
        d.rectangle([w - w // 8, h - h // 8, w, h], fill=(0, 200, 0) + ((255,) if mode == "RGBA" else ()))
        return img

    gradient(1200, 720).save(os.path.join(IMAGES, "logo.png"))
    rgba = gradient(1200, 720, "RGBA")
    ImageDraw.Draw(rgba).ellipse([400, 200, 800, 520], fill=(0, 0, 0, 0))
    rgba.save(os.path.join(IMAGES, "alpha.png"))
    gradient(1200, 720).save(os.path.join(IMAGES, "photo.jpg"), quality=90)
    gradient(8000, 8000).save(os.path.join(IMAGES, "huge.png"), optimize=False)
    gradient(16, 16).save(os.path.join(IMAGES, "tiny.png"))
    gradient(64, 64).save(os.path.join(IMAGES, "bad.bmp"))
    print("images in", IMAGES)


if __name__ == "__main__":
    make_boards()
    if "--no-images" not in sys.argv:
        make_images()
