"""Chibi manga illustration for the bottom face of the FrWA RP2350 board (76.11 x 76.1 mm).

Writes art/rp2350_chibi.svg (the artwork, drawn as seen from BELOW the board)
and art/rp2350_chibi_mockup.svg (artwork + outline + bare-copper openings, to
preview what JLCPCB will print). Units are millimetres.

Layout comes from RP2350.kicad_pcb, mirrored for the bottom view:
  - 4 M3 mounting holes (gold pads, r = 3.5) at (10.06, 10.05) ... (66.06, 66.05)
  - IDC header pins: two columns each side, x = 8.55/11.1 and 65.0/67.6, y = 20.48..56.04
  - USB-C shell pins near the top centre, 1x3 headers at (22.6-27.7, 3.9) and (23.2-28.3, 55.5)
"""
import math
import os
import random

W, H = 76.11, 76.1
CX = W / 2
HERE = os.path.dirname(os.path.abspath(__file__))

HOLES = [(10.06, 10.05), (66.06, 10.05), (10.06, 66.05), (66.06, 66.05)]
PIN_COLUMNS = [8.55, 11.09, 65.06, 67.6]
PIN_ROWS = [20.48 + 2.54 * i for i in range(15)]
SMALL_HEADERS = [([22.66, 25.2, 27.74], 3.86), ([23.26, 25.8, 28.34], 55.46)]
# RP2350 exposed-pad thermal vias, bottom view (bare copper through the art)
U1_VIAS = [(x, y) for x in (37.25, 38.10, 38.95) for y in (34.11, 34.96, 35.81)]
USB_PINS = [(33.78, 2.38), (35.21, 2.38), (40.99, 2.38), (42.42, 2.38), (33.78, 6.56), (42.42, 6.56)]

OUTLINE = "M14 0 H62.1 C64 0 64.1 0.8 64.1 0.84 L75.3 12.06 C76 12.8 76.1 13.4 76.1 14.05 V62.05 " \
          "C76.1 63 75.6 63.7 75.1 64.3 L64.06 75.3 C63.4 75.9 62.8 76.1 62.06 76.1 H14.06 C13.2 76.1 " \
          "12.6 75.8 12.07 75.3 L0.8 64.05 C0.3 63.5 0.05 62.8 0.05 62.05 V14.05 C0.05 13.2 0.4 12.5 " \
          "0.98 11.9 L12.03 0.84 C12.6 0.3 13.3 0.05 14.06 0.05 Z"

# Palette: PCB teal + gold (ENIG) + ice white (FrWA snowflake) + navy
NAVY, NAVY2 = "#0b1a2e", "#14284a"
TEAL, TEAL_D, TEAL_L = "#22b8a0", "#127a6c", "#9af7e3"
GOLD, GOLD_L = "#e2b84f", "#ffe39a"
CYAN = "#5ff3ff"
SKIN, SKIN_S = "#ffe2cf", "#f4b9a2"
LINE = "#2a1a1f"


def star(x, y, r, color, opacity=1.0, thin=0.22):
    k = r * thin
    return ('<path d="M{x} {a} Q{b} {c} {d} {y} Q{b} {e} {x} {f} Q{g} {e} {h} {y} Q{g} {c} {x} {a} Z" '
            'fill="{col}" opacity="{o}"/>').format(x=x, y=y, a=y - r, f=y + r, d=x + r, h=x - r,
                                                   b=x + k, g=x - k, c=y - k, e=y + k, col=color, o=opacity)


def snowflake(x, y, r, color, width=0.3, opacity=1.0):
    out = []
    for i in range(6):
        a = math.radians(60 * i - 90)
        ex, ey = x + r * math.cos(a), y + r * math.sin(a)
        out.append('<line x1="{:.3f}" y1="{:.3f}" x2="{:.3f}" y2="{:.3f}"/>'.format(x, y, ex, ey))
        for t, s in ((0.55, 0.35), (0.8, 0.22)):
            bx, by = x + r * t * math.cos(a), y + r * t * math.sin(a)
            for da in (-50, 50):
                b = math.radians(60 * i - 90 + da)
                out.append('<line x1="{:.3f}" y1="{:.3f}" x2="{:.3f}" y2="{:.3f}"/>'.format(
                    bx, by, bx + r * s * math.cos(b), by + r * s * math.sin(b)))
    return '<g stroke="{}" stroke-width="{}" stroke-linecap="round" opacity="{}">{}</g>'.format(
        color, width, opacity, "".join(out))


def traces(seed=7):
    """PCB-style traces (0/45/90 degree segments) radiating from the chip."""
    rnd = random.Random(seed)
    out = []
    cx, cy = CX, 19
    for i in range(34):
        ang = 2 * math.pi * i / 34 + rnd.uniform(-0.05, 0.05)
        x, y = cx + 9.5 * math.cos(ang), cy + 9.5 * math.sin(ang)
        pts = [(x, y)]
        heading = round(math.degrees(ang) / 45) * 45
        for _ in range(rnd.randint(2, 4)):
            step = rnd.uniform(5, 13)
            x += step * math.cos(math.radians(heading))
            y += step * math.sin(math.radians(heading))
            x, y = min(max(x, 3.5), W - 3.5), min(max(y, 3.5), H - 3.5)
            pts.append((x, y))
            heading += rnd.choice((-45, 45))
        d = "M" + " L".join("{:.2f} {:.2f}".format(px, py) for px, py in pts)
        color = GOLD if i % 3 else CYAN
        out.append('<path d="{}" stroke="{}" stroke-width="{}" fill="none" stroke-linejoin="round" '
                   'opacity="0.5"/>'.format(d, color, 0.32 if i % 3 else 0.22))
        ex, ey = pts[-1]
        out.append('<circle cx="{:.2f}" cy="{:.2f}" r="0.55" fill="{}" stroke="{}" stroke-width="0.2" '
                   'opacity="0.75" fill-opacity="0.15"/>'.format(ex, ey, NAVY, color))
    return "\n".join(out)


def octagon(inset):
    c = 14 + inset * 0.4  # chamfer length follows the board's ~14 mm corners
    a, b = inset, W - inset
    t, u = inset, H - inset
    return "M{0} {1} H{2} L{3} {4} V{5} L{2} {6} H{0} L{7} {5} V{4} Z".format(
        a + c - inset, t, b - c + inset, b, t + c - inset, u - c + inset, u, a)


def chip(cx, cy, size, angle):
    s = size / 2
    pins = []
    n, pitch = 20, size * 0.82 / 20
    for i in range(n):
        o = -size * 0.41 + pitch * (i + 0.5)
        for (x, y, w, h) in ((cx + o - 0.16, cy - s - 1.1, 0.32, 1.3), (cx + o - 0.16, cy + s - 0.2, 0.32, 1.3),
                             (cx - s - 1.1, cy + o - 0.16, 1.3, 0.32), (cx + s - 0.2, cy + o - 0.16, 1.3, 0.32)):
            pins.append('<rect x="{:.3f}" y="{:.3f}" width="{}" height="{}" fill="url(#pin)"/>'.format(x, y, w, h))
    return """
<g transform="rotate({a} {cx} {cy})">
  {pins}
  <rect x="{x0}" y="{y0}" width="{sz}" height="{sz}" rx="0.7" fill="url(#chipbody)" stroke="#4a4f5a" stroke-width="0.25"/>
  <rect x="{x1}" y="{y1}" width="{sz2}" height="{sz2}" rx="0.4" fill="none" stroke="#2c3038" stroke-width="0.2"/>
  <circle cx="{p1x}" cy="{p1y}" r="0.7" fill="#2c3038"/>
  <text x="{cx}" y="{ty}" text-anchor="middle" font-family="Consolas, 'Courier New', monospace" font-weight="700"
        font-size="2.25" fill="#d6dbe3" letter-spacing="0.08">RP2350</text>
  <text x="{cx}" y="{ty2}" text-anchor="middle" font-family="Consolas, monospace" font-size="1.05" fill="#8a919c">QFN-80 · 150 MHz</text>
  <path d="M{gx0} {gy0} L{gx1} {gy0}" stroke="{cyan}" stroke-width="0.25" opacity="0.8"/>
  <path d="M{x0} {y0} h{sz}" stroke="#ffffff" stroke-width="0.3" opacity="0.35"/>
</g>""".format(a=angle, cx=cx, cy=cy, pins="\n  ".join(pins), x0=cx - s, y0=cy - s, sz=size,
               x1=cx - s + 1, y1=cy - s + 1, sz2=size - 2, p1x=cx - s + 2, p1y=cy - s + 2,
               ty=cy + 0.9, ty2=cy + 2.9, gx0=cx - 3.2, gx1=cx + 3.2, gy0=cy - 2.4, cyan=CYAN)


def rotate(px, py, cx, cy, deg):
    a = math.radians(deg)
    dx, dy = px - cx, py - cy
    return cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a)


def artwork():
    chip_c, chip_size, chip_angle = (CX, 18.6), 12.6, -6
    s = chip_size / 2
    hand_l = rotate(chip_c[0] - s + 0.9, chip_c[1] + s + 0.3, chip_c[0], chip_c[1], chip_angle)
    hand_r = rotate(chip_c[0] + s - 0.9, chip_c[1] + s + 0.3, chip_c[0], chip_c[1], chip_angle)

    parts = []
    add = parts.append
    add("""<defs>
  <radialGradient id="bg" cx="0.5" cy="0.36" r="0.75">
    <stop offset="0" stop-color="#1f7f73"/><stop offset="0.45" stop-color="#123f52"/><stop offset="1" stop-color="{navy}"/>
  </radialGradient>
  <radialGradient id="glow" cx="0.5" cy="0.5" r="0.5">
    <stop offset="0" stop-color="{cyan}" stop-opacity="0.85"/><stop offset="0.45" stop-color="{cyan}" stop-opacity="0.28"/>
    <stop offset="1" stop-color="{cyan}" stop-opacity="0"/>
  </radialGradient>
  <linearGradient id="beam" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#ffffff" stop-opacity="0.9"/><stop offset="0.6" stop-color="{cyan}" stop-opacity="0.35"/>
    <stop offset="1" stop-color="{cyan}" stop-opacity="0"/>
  </linearGradient>
  <linearGradient id="chipbody" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#2a2e36"/><stop offset="1" stop-color="#121418"/>
  </linearGradient>
  <linearGradient id="pin" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{goldl}"/><stop offset="1" stop-color="#b98a2a"/>
  </linearGradient>
  <linearGradient id="hair" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{teall}"/><stop offset="0.35" stop-color="{teal}"/><stop offset="1" stop-color="{teald}"/>
  </linearGradient>
  <linearGradient id="iris" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#063f3c"/><stop offset="0.55" stop-color="#0f8f82"/><stop offset="1" stop-color="#6ff7dc"/>
  </linearGradient>
  <linearGradient id="hoodie" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#2a3f6e"/><stop offset="1" stop-color="{navy2}"/>
  </linearGradient>
  <linearGradient id="skirt" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{teal}"/><stop offset="1" stop-color="{teald}"/>
  </linearGradient>
  <filter id="soft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="0.6"/></filter>
</defs>""".format(navy=NAVY, navy2=NAVY2, cyan=CYAN, goldl=GOLD_L, teal=TEAL, teald=TEAL_D, teall=TEAL_L))

    # Background, traces, octagonal frame echoing the board outline
    add('<rect width="{}" height="{}" fill="url(#bg)"/>'.format(W, H))
    add(traces())
    add('<path d="{}" fill="none" stroke="{}" stroke-width="0.5" opacity="0.9"/>'.format(octagon(1.8), GOLD))
    add('<path d="{}" fill="none" stroke="{}" stroke-width="0.18" stroke-dasharray="1.2 0.6" opacity="0.7"/>'.format(
        octagon(2.9), CYAN))

    # Mounting holes: snowflake sigils around the gold pads (FrWA snowflake)
    for x, y in HOLES:
        add('<circle cx="{}" cy="{}" r="4.6" fill="none" stroke="{}" stroke-width="0.35"/>'.format(x, y, GOLD))
        add('<circle cx="{}" cy="{}" r="5.5" fill="none" stroke="{}" stroke-width="0.18" stroke-dasharray="0.5 0.5"/>'.format(
            x, y, CYAN))
        for k in range(12):
            a = math.radians(30 * k)
            add('<circle cx="{:.3f}" cy="{:.3f}" r="0.22" fill="{}"/>'.format(x + 5.05 * math.cos(a), y + 5.05 * math.sin(a), GOLD_L))

    # Header pin columns become glowing "power conduits"
    for x0 in (7.0, 63.5):
        add('<rect x="{}" y="18.6" width="5.6" height="39.3" rx="2.8" fill="{}" opacity="0.55" stroke="{}" '
            'stroke-width="0.3"/>'.format(x0, NAVY, CYAN))
        add('<line x1="{0}" y1="20" x2="{0}" y2="56.5" stroke="{1}" stroke-width="0.25" opacity="0.6"/>'.format(x0 + 2.8, CYAN))

    # USB-C at the top feeds a beam down to the chip
    add('<path d="M34.3 0 L41.8 0 L47.5 19 L28.6 19 Z" fill="url(#beam)"/>')
    add('<circle cx="{}" cy="{}" r="15" fill="url(#glow)"/>'.format(chip_c[0], chip_c[1]))

    # Sparkles
    for (x, y, r, c, o) in ((24.5, 9.5, 1.6, "#ffffff", 0.95), (52.5, 11.5, 1.2, GOLD_L, 0.9), (50, 27.5, 0.9, "#ffffff", 0.8),
                            (22.5, 27, 1.0, CYAN, 0.9), (55.5, 34, 0.7, "#ffffff", 0.7), (20, 40, 0.6, GOLD_L, 0.8),
                            (56.5, 48, 1.1, CYAN, 0.8), (18.5, 52, 0.8, "#ffffff", 0.7), (28.5, 4.5, 0.6, "#ffffff", 0.8)):
        add(star(x, y, r, c, o))

    # ---- character: back hair
    add('<path d="M27.2 40.5 C25.4 30.5 31 27.2 38 27.2 C45 27.2 50.6 30.5 48.9 40.5 C49.4 48 51.5 54.5 49.6 60.5 '
        'C48.6 62.2 46.8 62.4 45.6 61.6 C46.4 57.5 46.2 53 45 49 L31.1 49 C29.9 53 29.7 57.5 30.5 61.6 '
        'C29.3 62.4 27.5 62.2 26.5 60.5 C24.6 54.5 26.7 48 27.2 40.5 Z" fill="url(#hair)" stroke="#0d4f47" stroke-width="0.3"/>')

    # body: legs, skirt, hoodie
    for x in (34.2, 39.6):
        add('<rect x="{}" y="66" width="2.3" height="5.6" rx="0.6" fill="{}" stroke="{}" stroke-width="0.2"/>'.format(x, SKIN, LINE))
        add('<path d="M{0} 70.6 h2.9 c0.9 0 1.3 0.9 1.3 1.7 v0.6 c0 0.6 -0.4 0.9 -1 0.9 h-3.4 c-0.5 0 -0.8 -0.4 -0.8 -0.9 v-1.6 '
            'c0 -0.4 0.4 -0.7 1 -0.7 Z" fill="{1}" stroke="{2}" stroke-width="0.2"/>'.format(x - 0.25, NAVY2, LINE))
        add('<rect x="{}" y="70.4" width="2.5" height="0.5" fill="{}"/>'.format(x - 0.1, GOLD))
    add('<path d="M31.2 61.5 L44.9 61.5 L47.6 67.6 C43 69 33.1 69 28.5 67.6 Z" fill="url(#skirt)" stroke="{}" stroke-width="0.25"/>'.format(LINE))
    for x in (32.5, 35.3, 38.05, 40.8, 43.6):
        add('<line x1="{0}" y1="61.8" x2="{1}" y2="68.2" stroke="{2}" stroke-width="0.2" opacity="0.7"/>'.format(
            x, CX + (x - CX) * 1.35, TEAL_D))
    add('<path d="M28.6 67.6 C33.1 69 43 69 47.6 67.6" fill="none" stroke="{}" stroke-width="0.35"/>'.format(GOLD))
    add('<rect x="36.4" y="47.6" width="3.3" height="4.2" fill="{}" stroke="{}" stroke-width="0.2"/>'.format(SKIN_S, LINE))
    add('<path d="M32.4 51.6 C33.4 50.6 42.7 50.6 43.7 51.6 L45.4 62.2 C45.4 63 30.7 63 30.7 62.2 Z" fill="url(#hoodie)" '
        'stroke="{}" stroke-width="0.25"/>'.format(LINE))
    add('<path d="M34.6 51 C36 53.4 40.1 53.4 41.5 51" fill="none" stroke="{}" stroke-width="0.45"/>'.format(GOLD))
    add('<line x1="38.05" y1="52.9" x2="38.05" y2="62.5" stroke="{}" stroke-width="0.3"/>'.format(GOLD))
    add(snowflake(41.4, 56.2, 1.3, "#e9fbff", 0.22))  # chest emblem
    for x in (36.6, 39.5):
        add('<line x1="{0}" y1="52.8" x2="{1}" y2="56.4" stroke="#e9fbff" stroke-width="0.2"/>'.format(x, x - 0.3 if x < 38 else x + 0.3))

    # arms raised to the chip (sleeves, rolled cuffs, forearms)
    for (sx, ex, ey, hand) in ((33.4, 25.4, 40.0, hand_l), (42.7, 50.7, 40.0, hand_r)):
        add('<path d="M{} 52.6 Q{} 48 {} {}" fill="none" stroke="{}" stroke-width="3.3" stroke-linecap="round"/>'.format(
            sx, (sx + ex) / 2 - (1.5 if sx < 38 else -1.5), ex, ey, LINE))
        add('<path d="M{} 52.6 Q{} 48 {} {}" fill="none" stroke="#2a3f6e" stroke-width="2.8" stroke-linecap="round"/>'.format(
            sx, (sx + ex) / 2 - (1.5 if sx < 38 else -1.5), ex, ey))
        add('<line x1="{}" y1="{}" x2="{:.2f}" y2="{:.2f}" stroke="{}" stroke-width="2.25" stroke-linecap="round"/>'.format(
            ex, ey, hand[0], hand[1] + 1.2, LINE))
        add('<line x1="{}" y1="{}" x2="{:.2f}" y2="{:.2f}" stroke="{}" stroke-width="1.8" stroke-linecap="round"/>'.format(
            ex, ey, hand[0], hand[1] + 1.2, SKIN))
        dx, dy = hand[0] - ex, hand[1] + 1.2 - ey
        n = math.hypot(dx, dy)
        add('<line x1="{:.2f}" y1="{:.2f}" x2="{:.2f}" y2="{:.2f}" stroke="{}" stroke-width="2.9" stroke-linecap="butt"/>'.format(
            ex - dx / n * 0.2, ey - dy / n * 0.2, ex + dx / n * 0.8, ey + dy / n * 0.8, GOLD))

    # the chip, then the fingers gripping its lower corners
    add(chip(chip_c[0], chip_c[1], chip_size, chip_angle))
    for hx, hy in (hand_l, hand_r):
        add('<ellipse cx="{:.2f}" cy="{:.2f}" rx="1.45" ry="1.25" fill="{}" stroke="{}" stroke-width="0.22"/>'.format(
            hx, hy + 0.5, SKIN, LINE))
        for k in (-0.7, 0, 0.7):
            add('<line x1="{:.2f}" y1="{:.2f}" x2="{:.2f}" y2="{:.2f}" stroke="{}" stroke-width="0.14" opacity="0.6"/>'.format(
                hx + k, hy - 0.4, hx + k * 0.9, hy + 0.3, LINE))

    # head: face, eyes, mouth, blush
    add('<path d="M30.4 40.2 C30.4 32.4 45.7 32.4 45.7 40.2 C45.7 45.2 42.3 48.9 38.05 49.5 C33.8 48.9 30.4 45.2 30.4 40.2 Z" '
        'fill="{}" stroke="{}" stroke-width="0.3"/>'.format(SKIN, LINE))
    for (ex, flip) in ((34.6, 1), (41.5, -1)):
        add('<ellipse cx="{}" cy="43.1" rx="2.4" ry="3.0" fill="#ffffff" stroke="{}" stroke-width="0.18"/>'.format(ex, LINE))
        add('<ellipse cx="{}" cy="43.5" rx="2.0" ry="2.65" fill="url(#iris)"/>'.format(ex))
        add('<ellipse cx="{}" cy="43.5" rx="0.85" ry="1.15" fill="#042523"/>'.format(ex))
        add('<circle cx="{}" cy="42.2" r="0.72" fill="#ffffff"/>'.format(ex - 0.65 * flip))
        add('<circle cx="{}" cy="44.6" r="0.36" fill="#ffffff" opacity="0.9"/>'.format(ex + 0.7 * flip))
        add('<path d="M{} 40.9 Q{} 39.2 {} 40.7" fill="none" stroke="{}" stroke-width="0.45" stroke-linecap="round"/>'.format(
            ex - 2.5, ex, ex + 2.5, LINE))
        add('<path d="M{} 40.8 q{} -0.2 {} -1.0" fill="none" stroke="{}" stroke-width="0.35" stroke-linecap="round"/>'.format(
            ex - 2.4 * flip, -0.5 * flip, -0.9 * flip, LINE))
        add('<path d="M{} 45.9 Q{} 46.5 {} 45.9" fill="none" stroke="{}" stroke-width="0.18" opacity="0.6"/>'.format(
            ex - 1.3, ex, ex + 1.3, LINE))
        add('<ellipse cx="{}" cy="46.3" rx="1.35" ry="0.6" fill="#ff8fa3" opacity="0.55"/>'.format(ex - 1.9 * flip))
        for k in (-0.5, 0, 0.5):
            add('<line x1="{:.2f}" y1="45.95" x2="{:.2f}" y2="46.65" stroke="#e86a82" stroke-width="0.12" opacity="0.8"/>'.format(
                ex - 1.9 * flip + k + 0.15, ex - 1.9 * flip + k - 0.15))
    add('<line x1="38.05" y1="45.2" x2="38.25" y2="45.5" stroke="{}" stroke-width="0.18" stroke-linecap="round"/>'.format(SKIN_S))
    add('<path d="M36.85 46.5 Q38.05 48.6 39.25 46.5 Z" fill="#b8323f" stroke="{}" stroke-width="0.2" stroke-linejoin="round"/>'.format(LINE))
    add('<path d="M37.45 47.5 Q38.05 47.15 38.65 47.5 Q38.05 48.05 37.45 47.5 Z" fill="#ff8b8b"/>')

    # front hair (bangs + side locks + ahoge) and snowflake hairclip
    add('<path d="M29.6 41.8 C28.6 32 33.6 28.6 38.05 28.6 C42.5 28.6 47.5 32 46.5 41.8 L45.5 38.4 L44.7 40.9 '
        'L43.2 36.4 L41.8 39.0 L40.1 35.4 L38.05 38.4 L36.0 35.4 L34.3 39.0 L32.9 36.4 L31.4 40.9 L30.6 38.4 Z" '
        'fill="url(#hair)" stroke="#0d4f47" stroke-width="0.3" stroke-linejoin="round"/>')
    add('<path d="M29.7 40 C29 45 29.6 49 31.3 52.5 C30.3 48.5 30.9 45 31.5 42.5 Z" fill="url(#hair)" stroke="#0d4f47" stroke-width="0.25"/>')
    add('<path d="M46.4 40 C47.1 45 46.5 49 44.8 52.5 C45.8 48.5 45.2 45 44.6 42.5 Z" fill="url(#hair)" stroke="#0d4f47" stroke-width="0.25"/>')
    add('<path d="M33.5 31.2 C35.5 29.8 38.5 29.6 40.5 30.2" fill="none" stroke="{}" stroke-width="0.55" stroke-linecap="round" opacity="0.8"/>'.format(TEAL_L))
    add('<path d="M38.4 28.7 C37.6 26.9 38.4 25.7 40.1 25.9 C38.9 26.5 38.7 27.6 39.1 28.7 Z" fill="{}" stroke="#0d4f47" stroke-width="0.2"/>'.format(TEAL))
    # mini-chip hair clip whose 3x3 "balls" are the RP2350 thermal vias
    add('<rect x="36.05" y="32.9" width="4.1" height="4.1" rx="0.6" fill="{}" stroke="{}" stroke-width="0.35"/>'.format(NAVY, GOLD))
    for x, y in U1_VIAS:
        add('<circle cx="{}" cy="{}" r="0.32" fill="{}"/>'.format(x, y, GOLD_L))
    add('<circle cx="44.4" cy="33.4" r="1.9" fill="#ffffff" opacity="0.25" filter="url(#soft)"/>')
    add(snowflake(44.4, 33.4, 1.7, "#f2fdff", 0.32))
    add('<circle cx="44.4" cy="33.4" r="0.35" fill="{}"/>'.format(CYAN))
    return "\n".join(parts)


def svg(body, extra=""):
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" width="{w}mm" height="{h}mm" '
            'viewBox="0 0 {w} {h}">\n{body}\n{extra}\n</svg>\n').format(w=W, h=H, body=body, extra=extra)


def mockup_overlay():
    """Milled outline + bare copper (no ink) as JLCPCB would leave it."""
    out = ['<path d="M0 0 H{w} V{h} H0 Z {o}" fill="#3b3f46" fill-rule="evenodd"/>'.format(w=W, h=H, o=OUTLINE)]
    gold = 'fill="#d8b04a" stroke="#a37b22" stroke-width="0.12"'
    for x, y in HOLES:
        out.append('<circle cx="{}" cy="{}" r="3.5" {}/><circle cx="{}" cy="{}" r="1.6" fill="#3b3f46"/>'.format(x, y, gold, x, y))
    for x in PIN_COLUMNS:
        for y in PIN_ROWS:
            out.append('<circle cx="{}" cy="{:.2f}" r="0.85" {}/><circle cx="{}" cy="{:.2f}" r="0.5" fill="#22252a"/>'.format(
                x, y, gold, x, y))
    for xs, y in SMALL_HEADERS:
        for x in xs:
            out.append('<circle cx="{}" cy="{}" r="0.85" {}/><circle cx="{}" cy="{}" r="0.5" fill="#22252a"/>'.format(x, y, gold, x, y))
    for x, y in U1_VIAS:
        out.append('<circle cx="{}" cy="{}" r="0.21" {}/>'.format(x, y, gold))
    for x, y in USB_PINS:
        out.append('<ellipse cx="{}" cy="{}" rx="0.45" ry="0.9" {}/>'.format(x, y, gold))
    out.append('<path d="{}" fill="none" stroke="#c9ced6" stroke-width="0.25"/>'.format(OUTLINE))
    return "\n".join(out)


if __name__ == "__main__":
    body = artwork()
    with open(os.path.join(HERE, "rp2350_chibi.svg"), "w", encoding="utf-8") as fh:
        fh.write(svg(body))
    with open(os.path.join(HERE, "rp2350_chibi_mockup.svg"), "w", encoding="utf-8") as fh:
        fh.write(svg(body, mockup_overlay()))
    print("ok")
