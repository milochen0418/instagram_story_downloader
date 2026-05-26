"""
Generate assets/favicon.ico — MiStories branding.
Design: Instagram-style gradient ring, transparent centre, no letter.
The ring alone is the strongest IG Story visual symbol.
Pure Python — no external dependencies.
"""
import math
import struct
import zlib

SIZE = 32

# Official IG gradient: yellow → orange → red → pink → magenta → purple → blue
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


# Bold "M" glyph: 7 cols × 7 rows, rendered at 2× scale = 14×14 px, centred
M_BITMAP = [
    [1, 0, 0, 0, 0, 0, 1],
    [1, 1, 0, 0, 0, 1, 1],
    [1, 0, 1, 0, 1, 0, 1],
    [1, 0, 0, 1, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 1],
]
_M_SCALE = 2
_M_COLS  = len(M_BITMAP[0]) * _M_SCALE  # 14
_M_ROWS  = len(M_BITMAP)    * _M_SCALE  # 14


def is_m_pixel(x, y, size):
    x_off = (size - _M_COLS) // 2
    y_off = (size - _M_ROWS) // 2
    lx, ly = x - x_off, y - y_off
    if lx < 0 or lx >= _M_COLS or ly < 0 or ly >= _M_ROWS:
        return False
    return bool(M_BITMAP[ly // _M_SCALE][lx // _M_SCALE])


def aa_alpha(dist, lo, hi):
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

            # Fully outside → transparent
            if dist > outer_r + 0.5:
                row.append((0, 0, 0, 0))
                continue

            # Interior of the ring
            if dist < inner_r - 0.5:
                if is_m_pixel(x, y, size):
                    # M pixels: coloured with the IG gradient (angle from centre)
                    angle = (math.atan2(dy, -dx) / (2 * math.pi) + 0.5) % 1.0
                    r, g, b = lerp_stops(angle)
                    row.append((r, g, b, 255))
                else:
                    row.append((0, 0, 0, 0))  # transparent bg
                continue

            angle = (math.atan2(dy, -dx) / (2 * math.pi) + 0.5) % 1.0
            r, g, b = lerp_stops(angle)
            a = round(aa_alpha(dist, inner_r, outer_r) * 255)
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
