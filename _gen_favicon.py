"""
Generate assets/favicon.ico with an Instagram Story gradient-ring aesthetic.
Pure Python — no external dependencies.
"""
import math
import struct
import zlib

SIZE = 32

# IG gradient colour stops (angle 0..1 around the ring, bottom→CCW)
# Official IG gradient: yellow → orange → red → pink → purple → blue
STOPS = [
    (0.00, 0xFC, 0xAF, 0x45),  # #FCAF45 yellow
    (0.18, 0xF7, 0x77, 0x37),  # #F77737 orange
    (0.32, 0xFD, 0x1D, 0x1D),  # #FD1D1D red
    (0.50, 0xE1, 0x30, 0x6C),  # #E1306C pink
    (0.66, 0xC1, 0x35, 0x84),  # #C13584 magenta
    (0.82, 0x83, 0x3A, 0xB4),  # #833AB4 purple
    (1.00, 0x40, 0x5D, 0xE6),  # #405DE6 blue
]


def lerp_stops(t: float) -> tuple[int, int, int]:
    for i in range(len(STOPS) - 1):
        t0, r0, g0, b0 = STOPS[i]
        t1, r1, g1, b1 = STOPS[i + 1]
        if t0 <= t <= t1:
            f = (t - t0) / (t1 - t0)
            return (
                round(r0 + (r1 - r0) * f),
                round(g0 + (g1 - g0) * f),
                round(b0 + (b1 - b0) * f),
            )
    return (STOPS[-1][1], STOPS[-1][2], STOPS[-1][3])


def aa_alpha(dist: float, inner: float, outer: float) -> float:
    """Smooth anti-aliased alpha for a ring boundary."""
    if dist < inner - 0.5:
        return 0.0  # inside
    if dist > outer + 0.5:
        return 0.0  # outside transparent
    if dist < inner + 0.5:
        return (dist - (inner - 0.5))  # inner edge fade-in
    if dist > outer - 0.5:
        return (outer + 0.5) - dist   # outer edge fade-out
    return 1.0


def make_pixels(size: int) -> list[list[tuple[int, int, int, int]]]:
    cx = cy = (size - 1) / 2.0
    outer_r = size / 2.0 - 0.8
    ring_w  = size / 7.0
    inner_r = outer_r - ring_w

    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            dx, dy = x - cx, y - cy
            dist = math.hypot(dx, dy)

            if dist > outer_r + 0.5:
                row.append((0, 0, 0, 0))
                continue

            # Interior fill (dark, like IG dark bg)
            if dist < inner_r - 0.5:
                row.append((18, 18, 18, 255))
                continue

            # Gradient ring
            # angle: 0 = bottom-left, increases CW to match IG rotation
            angle = (math.atan2(dy, -dx) / (2 * math.pi) + 0.5) % 1.0
            r, g, b = lerp_stops(angle)
            alpha_ring  = aa_alpha(dist, inner_r, outer_r)

            if dist < inner_r + 0.5:
                # Blend ring colour over dark interior at inner edge
                f = alpha_ring
                fr = round(r * f + 18 * (1 - f))
                fg = round(g * f + 18 * (1 - f))
                fb = round(b * f + 18 * (1 - f))
                row.append((fr, fg, fb, 255))
            else:
                a = round(alpha_ring * 255)
                row.append((r, g, b, a))

        rows.append(row)
    return rows


# ── PNG writer ────────────────────────────────────────────────────────────────

def _png_chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def make_png(rows: list[list[tuple[int, int, int, int]]]) -> bytes:
    h = len(rows)
    w = len(rows[0])

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)  # RGBA

    raw = bytearray()
    for row in rows:
        raw.append(0)  # filter type None
        for (r, g, b, a) in row:
            raw += bytes([r, g, b, a])

    idat = zlib.compress(bytes(raw), 9)

    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


# ── ICO writer (stores PNG directly — supported since Windows Vista) ──────────

def make_ico(png_bytes: bytes, size: int) -> bytes:
    # ICO header
    header = struct.pack("<HHH", 0, 1, 1)  # reserved, type=1(icon), count=1
    # Directory entry: w, h, colorcount, reserved, planes, bitcount, size, offset
    dir_entry = struct.pack("<BBBBHHII",
        size if size < 256 else 0,  # width  (0 = 256)
        size if size < 256 else 0,  # height (0 = 256)
        0, 0,   # color count, reserved
        1, 32,  # planes, bit count
        len(png_bytes),
        6 + 16,  # offset = sizeof(header) + sizeof(dir_entry)
    )
    return header + dir_entry + png_bytes


# ── main ──────────────────────────────────────────────────────────────────────

import os, pathlib

rows = make_pixels(SIZE)
png  = make_png(rows)
ico  = make_ico(png, SIZE)

out = pathlib.Path(__file__).parent / "assets" / "favicon.ico"
out.write_bytes(ico)
print(f"Written {out}  ({len(ico)} bytes, {SIZE}x{SIZE} RGBA)")
