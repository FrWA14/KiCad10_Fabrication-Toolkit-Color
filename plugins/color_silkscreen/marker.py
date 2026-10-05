"""Plain-Gerber registration file `.FCBM` (port of TransJLC build_outline_mark_gerber).

Same format as TransJLC and Overprint (%FSLAX25Y25%, coordinates scaled 1e5),
even though 2 integer digits cannot strictly hold values >= 100 mm: parsers
read leading-zero-omitted integers as value / 1e5 regardless.
"""
import math


def _coord(v_mm):
    scaled = v_mm * 100000.0
    i = int(math.copysign(math.floor(abs(scaled) + 0.5), scaled))  # Rust f64::round
    return "{}{:07d}".format("+" if i >= 0 else "-", abs(i))


def build_outline_mark_gerber(bounds, marks):
    out = [
        "G04 Fabrication_ColorfulBoardOutlineMark*",
        "%FSLAX25Y25*%",
        "%MOMM*%",
        "%LPD*%",
        "%ADD10C,0.150*%",
        "D10*",
        "X{}Y{}D02*".format(_coord(bounds.min_x), _coord(bounds.min_y)),
    ]
    for x, y in [(bounds.max_x, bounds.min_y), (bounds.max_x, bounds.max_y),
                 (bounds.min_x, bounds.max_y), (bounds.min_x, bounds.min_y)]:
        out.append("X{}Y{}D01*".format(_coord(x), _coord(y)))
    out += ["%ADD11C,1.000*%", "D11*"]
    for x, y in marks:
        out.append("X{}Y{}D03*".format(_coord(x), _coord(y)))
    out.append("M02*")
    return "\n".join(out) + "\n"
