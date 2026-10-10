"""Union of solder-mask openings for an even-odd clip path.

The colour SVG carves mask openings with fill-rule evenodd: two openings that
overlap cancel each other and the ink is printed over the copper. KiCad
produces such overlaps (stacked USB-C pads A1/B12, overlapping pads, mask
strokes). Openings are grouped by real intersection; identical shapes are
kept once and other groups are rebuilt as non-overlapping rectangles from an
exact-in-X horizontal scan (rows of `step` units).
"""
from .numfmt import f

UNIT = 0.254
STEP_MM = 0.01


def bbox(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def area(poly):
    return abs(sum(poly[i][0] * poly[i - 1][1] - poly[i - 1][0] * poly[i][1] for i in range(len(poly)))) / 2


def point_in_poly(x, y, poly):
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _segments_cross(a, b, c, d):
    def orient(p, q, r):
        v = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return (v > 1e-12) - (v < -1e-12)
    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    return o1 != o2 and o3 != o4


def intersects(a, b, box_a=None, box_b=None):
    ba, bb = box_a or bbox(a), box_b or bbox(b)
    if ba[2] < bb[0] or bb[2] < ba[0] or ba[3] < bb[1] or bb[3] < ba[1]:
        return False
    if point_in_poly(a[0][0], a[0][1], b) or point_in_poly(b[0][0], b[0][1], a):
        return True
    for i in range(len(a)):
        p, q = a[i - 1], a[i]
        for j in range(len(b)):
            if _segments_cross(p, q, b[j - 1], b[j]):
                return True
    return False


def _row_intervals(poly, y):
    xs = []
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i - 1], poly[i]
        if (y1 > y) != (y2 > y):
            xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
    xs.sort()
    return [(xs[k], xs[k + 1]) for k in range(0, len(xs) - 1, 2)]


def _merge(intervals):
    out = []
    for a, b in sorted(intervals):
        if out and a <= out[-1][1] + 1e-9:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def union_rectangles(polys, step):
    """Union of polygons as disjoint rectangles (x0, y0, x1, y1), quantised in Y by `step`."""
    y0 = min(bbox(p)[1] for p in polys)
    y1 = max(bbox(p)[3] for p in polys)
    rows = max(1, int((y1 - y0) / step + 0.999))
    h = (y1 - y0) / rows
    open_rects = {}   # (xa, xb) -> start y
    rects = []
    for r in range(rows + 1):
        if r < rows:
            yc = y0 + (r + 0.5) * h
            ivs = []
            for p in polys:
                ivs += _row_intervals(p, yc)
            current = {(round(a, 6), round(b, 6)) for a, b in _merge(ivs)}
        else:
            current = set()
        ytop = y0 + r * h
        for iv in list(open_rects):
            if iv not in current:
                rects.append((iv[0], open_rects.pop(iv), iv[1], ytop))
        for iv in current:
            if iv not in open_rects:
                open_rects[iv] = ytop
    return rects


def rect_path(x0, y0, x1, y1):
    return "M {a} {b} L {c} {b} {c} {d} {a} {d} Z ".format(a=f(x0), b=f(y0), c=f(x1), d=f(y1))


def merge_openings(items, step_mm=STEP_MM):
    """items: [(svg_path_d, polygon)] in SVG units. Returns (paths, polygons, stats)
    where no two returned shapes overlap."""
    n = len(items)
    boxes = [bbox(p) for _, p in items]
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    order = sorted(range(n), key=lambda i: boxes[i][0])
    for k, i in enumerate(order):  # sweep on X to keep pair tests local
        for j in order[k + 1:]:
            if boxes[j][0] > boxes[i][2]:
                break
            if find(i) != find(j) and intersects(items[i][1], items[j][1], boxes[i], boxes[j]):
                parent[find(i)] = find(j)

    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    paths, polys = [], []
    stats = {"groups_merged": 0, "duplicates_removed": 0, "contained_removed": 0}
    for members in groups.values():
        if len(members) == 1:
            d, p = items[members[0]]
            paths.append(d)
            polys.append(p)
            continue
        unique = {}
        for i in members:
            key = tuple((round(x, 4), round(y, 4)) for x, y in items[i][1])
            unique.setdefault(key, i)
        stats["duplicates_removed"] += len(members) - len(unique)
        if len(unique) == 1:
            d, p = items[next(iter(unique.values()))]
            paths.append(d)
            polys.append(p)
            continue
        container = _container(items, list(unique.values()))
        if container is not None:  # e.g. mounting-hole pad with its ring of vias, exposed pad + thermal vias
            stats["contained_removed"] += len(unique) - 1
            paths.append(items[container][0])
            polys.append(items[container][1])
            continue
        stats["groups_merged"] += 1
        for x0, y0, x1, y1 in union_rectangles([items[i][1] for i in unique.values()], step_mm / UNIT):
            paths.append(rect_path(x0, y0, x1, y1))
            polys.append([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
    return paths, polys, stats


def _container(items, members):
    """Index of the member whose polygon contains every vertex of the others, else None."""
    for i in sorted(members, key=lambda k: -area(items[k][1])):
        poly = items[i][1]
        if all(point_in_poly(x, y, poly) for j in members if j != i for x, y in items[j][1]):
            return i
    return None


def covered_points(points, polys):
    """Points (SVG units) that an even-odd clip would NOT open (inside an even number of shapes)."""
    boxes = [bbox(p) for p in polys]
    bad = []
    for x, y in points:
        n = sum(1 for p, b in zip(polys, boxes)
                if b[0] <= x <= b[2] and b[1] <= y <= b[3] and point_in_poly(x, y, p))
        if n % 2 == 0:
            bad.append((x, y))
    return bad
