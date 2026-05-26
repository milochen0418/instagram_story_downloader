"""
Generate assets/favicon.ico — MiStories branding.
Design: IG gradient ring + vector-rendered "M" (distance-field AA, smooth diagonals).
Pure Python — no external dependencies.
"""
import math
import struct
import zlib

SIZE = 32

# Official IG gradient: yellow -> orange -> red -> pink -> magenta -> purple -> blue
STOPS = [
    (0.00, 0xFC, 0xAF, 0x45),
    (0.18, 0xF7, 0x77, 0x37),
    (0.32, 0xFD, 0x1D, 0x1D),
    (0.50, 0xE1, 0x30, 0x6C),
    (0.66, 0xC1, 0x35, 0x84),
    (0.82, 0x83, 0x3A, 0xB4),
    (1.00, 0x40, 0x5D, 0xE6),
]


def lerp_stops(t):
    for i in range(len(STOPS) - 1):
        t0, r0, g0, b0 = STOPS[i]
        t1, r1, g1, b1 = STOPS[i + 1]
        if t0 <= t <= t1:
            f = (t - t0) / (t1 - t0)
            return round(r0+(r1-r0)*f), round(g0+(g1-g0)*f), round(b0+(b1-b0)*f)
    return STOPS[-1][1], STOPS[-1][2], STOPS[-1][3]


def seg_dist(px, py, ax, ay, bx, by):
    """Exact distance from point (px,py) to segment (ax,ay)-(bx,by)."""
    dx, dy = bx - ax, by - ay
    len2 = dx*dx + dy*dy
    if len2 < 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px-ax)*dx + (py-ay)*dy) / len2))
    return math.hypot(px - (ax + t*dx), py - (ay + t*dy))


def m_coverage(px, py, cx, cy, inner_r, stroke_w=2.1):
    """
    Anti-aliased coverage of pixel (px,py) for the vector M.
    M is 4 line segments; fades smoothly at stroke edges.
    """
    hw = inner_r * 0.60
    hh = inner_r * 0.63
    xl, xr = cx - hw, cx + hw
    yt, yb = cy - hh, cy + hh
    xm = cx
    ym = cy - hh * 0.08   # V-dip just above vertical centre

    segs = [
        (xl, yt, xl, yb),   # left vertical
        (xl, yt, xm, ym),   # left diagonal
        (xm, ym, xr, yt),   # right diagonal
        (xr, yt, xr, yb),   # right vertical
    ]
    d = min(seg_dist(px, py, *s) for s in segs)
    r = stroke_w / 2.0
    if d <= r - 0.5:
        return 1.0
    if d <= r + 0.5:
        return r + 0.5 - d
    return 0.0


def aa_ring(dist, lo, hi):
    if dist < lo - 0.5 or dist > hi + 0.5:
        return 0.0
    if dist < lo + 0.5:
        return dist - (lo - 0.5)
    if dist > hi - 0.5:
        return (hi + 0.5) - dist
    return 1.0


def make_pixels(size):
    cx = cy = (size - 1) / 2.0
    outer_r = size / 2.0 - 1.0
    ring_w  = size / 5.8
    inner_r = outer_r - ring_w

    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            dx, dy = x - cx, y - cy
            dist = math.hypot(dx, dy)
            angle = (math.atan2(dy, -dx) / (2 * math.pi) + 0.5) % 1.0
            r, g, b = lerp_stops(angle)

            if dist > outer_r + 0.5:
                row.append((0, 0, 0, 0))
            elif dist < inner_r - 0.5:
                cov = m_coverage(x, y, cx, cy, inner_r)
                row.append((r, g, b, round(cov * 255)))
            else:
                a = round(aa_ring(dist, inner_r, outer_r) * 255)
                row.append((r, g, b, a))
        rows.append(row)
    return rows


def _png_chunk(tag, data):
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def make_png(rows):
    h, w = len(rows), len(rows[0])
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    raw = bytearray()
    for row in rows:
        raw.append(0)
        for r, g, b, a in row:
            raw += bytes([r, g, b, a])
    idat = zlib.compress(bytes(raw), 9)
    return (b"\x89PNG\r\n\x1a\n"
            + _png_chunk(b"IHDR", ihdr)
            + _png_chunk(b"IDAT", idat)
            + _png_chunk(b"IEND", b""))


def make_ico(png_bytes, size):
    header    = struct.pack("<HHH", 0, 1, 1)
    dir_entry = struct.pack("<BBBBHHII",
        size if size < 256 else 0,
        size if size < 256 else 0,
        0, 0, 1, 32, len(png_bytes), 6 + 16)
    return header + dir_entry + png_bytes


import pathlib
rows = make_pixels(SIZE)
ico  = make_ico(make_png(rows), SIZE)
out  = pathlib.Path(__file__).parent / "assets" / "favicon.ico"
out.write_bytes(ico)
print(f"Written {out}  ({len(ico)} bytes, {SIZE}x{SIZE} RGBA)")
