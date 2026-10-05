"""Rename and rewrite Gerbers the way an EasyEDA Pro export looks
(port of TransJLC patterns.rs / gerber.rs / converter.rs).

JLCPCB appears to decide colour eligibility from these EasyEDA traits
(file names, generator header, hash aperture); see Overprint's
gerberCompatibility.ts. The geometric content of each file is unchanged.
"""
import hashlib
import os
import random
import re
import shutil
from datetime import datetime

from .errors import ColorSilkError

NOTICE_NAME = "PCB下单必读.txt"
NOTICE_ASSET = os.path.join(os.path.dirname(__file__), "assets", "order_notice.txt")

DRILL_LAYERS = ("NPTH", "PTH", "PTH_VIA")

JLC_NAMES = {
    "NPTH": "Drill_NPTH_Through.DRL",
    "PTH": "Drill_PTH_Through.DRL",
    "PTH_VIA": "Drill_PTH_Through_Via.DRL",
    "B_SILK": "Gerber_BottomSilkscreenLayer.GBO",
    "B_MASK": "Gerber_BottomSolderMaskLayer.GBS",
    "B_PASTE": "Gerber_BottomPasteMaskLayer.GBP",
    "B_CU": "Gerber_BottomLayer.GBL",
    "F_SILK": "Gerber_TopSilkscreenLayer.GTO",
    "F_MASK": "Gerber_TopSolderMaskLayer.GTS",
    "F_PASTE": "Gerber_TopPasteMaskLayer.GTP",
    "F_CU": "Gerber_TopLayer.GTL",
    "OUTLINE": "Gerber_BoardOutlineLayer.GKO",
}

# Fabrication Toolkit always plots with Protel extensions; KiCad names are
# accepted too (kicad-cli default). Order matters: NPTH before PTH.
PATTERNS = [
    ("NPTH", r"(?i)npth\.drl$"),
    ("PTH", r"(?i)\.drl$"),
    ("F_CU", r"(?i)(\.gtl|-F_Cu\.gbr)$"),
    ("B_CU", r"(?i)(\.gbl|-B_Cu\.gbr)$"),
    ("F_MASK", r"(?i)(\.gts|-F_Mask\.gbr)$"),
    ("B_MASK", r"(?i)(\.gbs|-B_Mask\.gbr)$"),
    ("F_PASTE", r"(?i)(\.gtp|-F_Paste\.gbr)$"),
    ("B_PASTE", r"(?i)(\.gbp|-B_Paste\.gbr)$"),
    ("F_SILK", r"(?i)(\.gto|-F_Silkscreen\.gbr)$"),
    ("B_SILK", r"(?i)(\.gbo|-B_Silkscreen\.gbr)$"),
    ("OUTLINE", r"(?i)(\.gko|\.gm1|-Edge_Cuts\.gbr)$"),
    ("INNER", r"(?i)(?:\.g(\d+)|-In(\d+)_Cu\.gbr)$"),
]


def classify(filename):
    """Return (layer_key, jlc_name) or None for files to drop."""
    for key, pattern in PATTERNS:
        m = re.search(pattern, filename)
        if not m:
            continue
        if key == "INNER":
            n = int(m.group(1) or m.group(2))
            return "IN{}".format(n), "Gerber_InnerLayer{0}.G{0}".format(n)
        return key, JLC_NAMES[key]
    return None


# --------------------------------------------------------------------------- Gerber rewriting

def split_combined_fs_mo(content):
    content = re.sub(r"%\s*(FS[^*%]*)\*\s*(MO[^*%]*)\*\s*%", r"%\1*%\n%\2*%", content)
    return re.sub(r"%\s*(MO[^*%]*)\*\s*(FS[^*%]*)\*\s*%", r"%\1*%\n%\2*%", content)


def strip_deprecated_attribute_blocks(content):
    return re.sub(r"%(?:IR|IP|OF|MI|SF)[^%]*%\n?", "", content)


def normalize_aperture_decimals(content):
    return re.sub(r"(?m)^%ADD\d+[A-Z][^*]*\*%$",
                  lambda m: re.sub(r"([,X])\.(\d)", r"\g<1>0.\2", m.group(0)), content)


def add_gerber_header(content, now=None):
    now = now or datetime.now()
    header = "G04 EasyEDA Pro v2.2.42.2, {}*\nG04 Gerber Generator version 0.3*\n".format(
        now.strftime("%Y-%m-%d %H:%M:%S"))
    return header + content.replace("\r\n", "\n")


_APERTURE_SELECT = re.compile(r"^(\s*)(D\d{2,4}\*)")


def has_missing_g54_prefix(content):
    for line in content.splitlines():
        t = line.lstrip()
        if t.startswith("%ADD") or t.startswith("G54D"):
            continue
        if re.match(r"^(\s*)D\d{2,4}\*", line):
            return True
    return False


def add_missing_g54_prefix(content):
    out = []
    for line in content.split("\n"):
        t = line.lstrip()
        if t.startswith("%ADD") or t.startswith("G54D"):
            out.append(line)
            continue
        m = _APERTURE_SELECT.match(line)
        out.append("{}G54{}{}".format(m.group(1), m.group(2), line[m.end():]) if m else line)
    return "\n".join(out)


_AD_LINE = re.compile(r"(?m)^%ADD(\d{2,4})(\D[^\n]*)$")


def _hash_suffix(text):
    return int(hashlib.md5(text.encode("utf-8")).hexdigest()[-2:], 16) % 100


def add_hash_aperture(content, rng=random, max_size=30000000):
    """Append the EasyEDA fingerprint aperture (size encodes md5 of the file)."""
    if len(content) > max_size:
        return content
    if not _AD_LINE.search(content):
        return content
    used = set(int(n) for n in re.findall(r"(?m)(?:^[ \t]*|G54)D(\d{2,4})\*", content))
    cleaned = content
    for m in reversed(list(_AD_LINE.finditer(content))):
        if int(m.group(1)) in used:
            continue
        end = m.end() + (1 if content[m.end():m.end() + 1] == "\n" else 0)
        cleaned = cleaned[:m.start()] + cleaned[end:]

    matches = list(_AD_LINE.finditer(cleaned))
    if matches:
        target = max(int(m.group(1)) for m in matches) + 1
        insert = matches[-1].end()
        if cleaned[insert:insert + 1] == "\n":
            insert += 1
        else:
            cleaned = cleaned[:insert] + "\n" + cleaned[insert:]
            insert += 1
    else:
        if not cleaned.endswith("\n"):
            cleaned += "\n"
        target, insert = 10, len(cleaned)

    size = "0.{:02d}{:02d}".format(rng.randint(0, 99), _hash_suffix(cleaned))
    if size == "0.0000":
        size = "0.0100"
    return cleaned[:insert] + "%ADD{}C,{}*%\n".format(target, size) + cleaned[insert:]


def verify_hash_aperture(content):
    matches = list(_AD_LINE.finditer(content))
    if not matches:
        return True
    last = matches[-1]
    m = re.search(r"C,(\d+(?:\.\d+))\*%\r?$", last.group(0))
    if not m or "." not in m.group(1) or len(m.group(1).split(".")[1]) != 4:
        return True
    end = last.end() + (1 if content[last.end():last.end() + 1] == "\n" else 0)
    stripped = content[:last.start()] + content[end:]
    return "{:02d}".format(_hash_suffix(stripped)) == m.group(1).split(".")[1][-2:]


def normalize_excellon(content):
    return re.sub(r"(?m)^(T\d+C)\.(\d)", r"\g<1>0.\2", content)


# --------------------------------------------------------------------------- directory conversion

def convert_directory(gerber_dir, log=None, now=None, rng=random):
    """Rewrite `gerber_dir` in place into the EasyEDA layout.

    Returns {layer_key: absolute path}. Unmatched files (drill maps, job files)
    are removed, as TransJLC does for non-JLC inputs.
    """
    files = sorted(n for n in os.listdir(gerber_dir) if os.path.isfile(os.path.join(gerber_dir, n)))
    plan = {}
    dropped = []
    for name in files:
        c = classify(name)
        if c is None:
            dropped.append(name)
            continue
        key, jlc_name = c
        if key in plan:
            dropped.append(name)
            if log:
                log.warning("couche %s déjà fournie par %s ; %s ignoré", key, plan[key][0], name)
            continue
        plan[key] = (name, jlc_name)

    if "OUTLINE" not in plan:
        raise ColorSilkError("E_OUTLINE_MISSING", "Aucun Gerber de contour (Edge.Cuts) dans l'export.")

    contents = {}
    for key, (name, _) in plan.items():
        with open(os.path.join(gerber_dir, name), "r", encoding="utf-8", newline="") as fh:
            contents[key] = fh.read()

    needs_g54 = any(has_missing_g54_prefix(contents[k]) for k in plan if k not in DRILL_LAYERS)

    staging = gerber_dir + "_jlc"
    if os.path.exists(staging):
        shutil.rmtree(staging)
    os.makedirs(staging)
    result = {}
    try:
        for key, (name, jlc_name) in plan.items():
            text = contents[key]
            if key in DRILL_LAYERS:
                text = normalize_excellon(text)
            else:
                text = normalize_aperture_decimals(strip_deprecated_attribute_blocks(split_combined_fs_mo(text)))
                text = add_gerber_header(text, now)
                if needs_g54:
                    text = add_missing_g54_prefix(text)
                text = add_hash_aperture(text, rng)
            with open(os.path.join(staging, jlc_name), "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
            if log:
                log.info("%s -> %s", name, jlc_name)
            result[key] = jlc_name
        shutil.copyfile(NOTICE_ASSET, os.path.join(staging, NOTICE_NAME))
    except OSError as e:
        shutil.rmtree(staging, ignore_errors=True)
        raise ColorSilkError("E_ZIP", "Écriture des Gerbers convertis impossible : {}".format(e))

    for name in files:
        os.remove(os.path.join(gerber_dir, name))
    for name in os.listdir(staging):
        shutil.move(os.path.join(staging, name), os.path.join(gerber_dir, name))
    os.rmdir(staging)
    if log and dropped:
        log.info("fichiers non transmis : %s", ", ".join(dropped))
    return {k: os.path.join(gerber_dir, v) for k, v in result.items()}, dropped
