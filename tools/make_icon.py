"""Draw Sidekick's icon and save it as scout/app/sidekick.ico (and a small sidekick.png).

Pure Python (no image library): each pixel is sampled 4x4 times for smooth edges. Run once
after changing the design: `python tools/make_icon.py`. The design is a gold scope ring with
four ticks and a teal center on the app's dark blue, matching the dashboard's colors.
"""

import math
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "scout" / "app"
TOP, BOTTOM = (0x1C, 0x2E, 0x4C), (0x0A, 0x11, 0x1C)
EDGE = (0x34, 0x4A, 0x70)
GOLD, TEAL = (0xD8, 0xB8, 0x6A), (0x2B, 0xC7, 0xB4)
SAMPLES = 4


def rounded_box(u: float, v: float, inset: float, radius: float) -> float:
    """Signed distance to a rounded square (negative inside)."""
    half = 0.5 - inset
    qx, qy = abs(u - 0.5) - half + radius, abs(v - 0.5) - half + radius
    outside = math.hypot(max(qx, 0.0), max(qy, 0.0))
    return outside + min(max(qx, qy), 0.0) - radius


def mark(u: float, v: float) -> tuple[int, int, int] | None:
    """The foreground color at (u, v), or None for background."""
    r = math.hypot(u - 0.5, v - 0.5)
    if r <= 0.095:
        return TEAL
    if abs(r - 0.265) <= 0.05:
        return GOLD
    dx, dy = abs(u - 0.5), abs(v - 0.5)
    along, across = max(dx, dy), min(dx, dy)
    if 0.335 <= along <= 0.44 and across <= 0.038:
        return GOLD
    return None


def pixel(x: int, y: int, size: int) -> tuple[int, int, int, int]:
    r = g = b = a = 0.0
    for sy in range(SAMPLES):
        for sx in range(SAMPLES):
            u = (x + (sx + 0.5) / SAMPLES) / size
            v = (y + (sy + 0.5) / SAMPLES) / size
            box = rounded_box(u, v, 0.02, 0.21)
            if box > 0:
                continue
            color = mark(u, v)
            if color is None:
                if box > -0.018:
                    color = EDGE
                else:
                    t = v
                    color = tuple(round(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3))
            r, g, b, a = r + color[0], g + color[1], b + color[2], a + 1
    n = SAMPLES * SAMPLES
    if a == 0:
        return 0, 0, 0, 0
    return round(r / a), round(g / a), round(b / a), round(255 * a / n)


def render(size: int) -> list[list[tuple[int, int, int, int]]]:
    return [[pixel(x, y, size) for x in range(size)] for y in range(size)]


def png(rows: list[list[tuple[int, int, int, int]]]) -> bytes:
    size = len(rows)
    raw = b"".join(b"\x00" + bytes(c for px in row for c in px) for row in rows)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))  # fmt: skip

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))  # fmt: skip


def bmp(rows: list[list[tuple[int, int, int, int]]]) -> bytes:
    """A 32-bit icon bitmap (bottom-up BGRA plus an empty AND mask) for the small sizes."""
    size = len(rows)
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    pixels = b"".join(bytes((p[2], p[1], p[0], p[3])) for row in reversed(rows) for p in row)
    mask = b"\x00" * (((size + 31) // 32) * 4 * size)
    return header + pixels + mask


def ico(images: dict[int, bytes]) -> bytes:
    entries, blobs = b"", b""
    offset = 6 + 16 * len(images)
    for size, data in images.items():
        side = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    return struct.pack("<HHH", 0, 1, len(images)) + entries + blobs


def main() -> None:
    images = {}
    for size in (16, 24, 32, 48, 64, 256):
        rows = render(size)
        images[size] = png(rows) if size >= 256 else bmp(rows)
        if size == 64:
            (OUT / "sidekick.png").write_bytes(png(rows))
    (OUT / "sidekick.ico").write_bytes(ico(images))
    print(f"Wrote {OUT / 'sidekick.ico'} and sidekick.png")


if __name__ == "__main__":
    main()
