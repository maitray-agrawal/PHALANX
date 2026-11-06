"""Generates complete favicon set and PWA icons for PHALANX.

Uses Python standard library (struct, zlib) to write RFC-compliant PNG and ICO files.
"""

import struct
import zlib
from pathlib import Path


def create_png(width: int, height: int) -> bytes:
    header = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    ihdr_chunk = b"IHDR" + ihdr
    ihdr_crc = struct.pack(">I", zlib.crc32(ihdr_chunk) & 0xFFFFFFFF)
    ihdr_full = struct.pack(">I", len(ihdr)) + ihdr_chunk + ihdr_crc

    # Generate image pixel grid with Phalanx Shield design
    # Navy: #002C6C (0, 44, 108), Gold: #FFC439 (255, 196, 57), Light Blue: #0070BA (0, 112, 186)
    rows = []
    cx = width / 2.0
    cy = height / 2.0
    r_corner = width * 0.18

    for y in range(height):
        row_bytes = bytearray(b"\x00")  # filter byte
        for x in range(width):
            # Check rounded rectangle boundary
            dx = max(abs(x - cx) - (cx - r_corner), 0)
            dy = max(abs(y - cy) - (cy - r_corner), 0)
            dist_corner = (dx * dx + dy * dy) ** 0.5
            if dist_corner > r_corner:
                # Transparent outside rounded rect
                row_bytes.extend((0, 0, 0, 0))
                continue

            # Normalized coordinate -1.0 to 1.0
            nx = (x - cx) / (width * 0.42)
            ny = (y - cy) / (height * 0.42)

            # Shield shape formula:
            # Top edge at ny = -0.7 to ny = 0.0 with width tapering to tip at ny = 0.85
            in_shield = False
            is_right_half = nx > 0
            is_core_node = (nx * nx + (ny + 0.1) * (ny + 0.1)) < 0.04

            if -0.75 <= ny <= 0.85:
                # width limit at this ny
                max_x = 0.8 - (ny + 0.75) * 0.1 if ny < 0.0 else 0.72 * (1.0 - (ny / 0.85) ** 1.8)

                if abs(nx) <= max_x:
                    in_shield = True

            if in_shield:
                if is_core_node:
                    # Navy center bindu node
                    row_bytes.extend((0, 44, 108, 255))
                elif is_right_half:
                    # Blue accent right side
                    row_bytes.extend((0, 112, 186, 255))
                else:
                    # Gold primary left side
                    row_bytes.extend((255, 196, 57, 255))
            else:
                # Navy background container
                row_bytes.extend((0, 44, 108, 255))

        rows.append(bytes(row_bytes))

    raw_data = b"".join(rows)
    compressed = zlib.compress(raw_data, level=9)
    idat_chunk = b"IDAT" + compressed
    idat_crc = struct.pack(">I", zlib.crc32(idat_chunk) & 0xFFFFFFFF)
    idat_full = struct.pack(">I", len(compressed)) + idat_chunk + idat_crc

    iend_chunk = b"IEND"
    iend_crc = struct.pack(">I", zlib.crc32(iend_chunk) & 0xFFFFFFFF)
    iend_full = struct.pack(">I", 0) + iend_chunk + iend_crc

    return header + ihdr_full + idat_full + iend_full


def create_ico(png_data: bytes) -> bytes:
    # Minimal ICO header wrapping PNG payload
    # 6 bytes header + 16 bytes directory entry + png data
    ico_header = struct.pack("<HHH", 0, 1, 1)  # reserved, type (1=ico), count (1)
    # Entry: width, height, colors (0), reserved (0), planes (1), bpp (32), size, offset
    w = 32
    h = 32
    size = len(png_data)
    offset = 6 + 16
    entry = struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, size, offset)
    return ico_header + entry + png_data


def main():
    public_dir = Path("web/public")
    public_dir.mkdir(parents=True, exist_ok=True)

    # 1. Favicon SVG
    svg_content = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">\n'
        "  <defs>\n"
        '    <linearGradient id="phalanxGrad" x1="0%" y1="0%" x2="100%" y2="100%">\n'
        '      <stop offset="0%" stop-color="#FFC439"/>\n'
        '      <stop offset="100%" stop-color="#E0A800"/>\n'
        "    </linearGradient>\n"
        "  </defs>\n"
        '  <rect width="64" height="64" rx="14" fill="#002C6C"/>\n'
        '  <path d="M32 10 L48 16 V32 C48 42 41 50 32 54 C23 50 16 42 16 32 V16 Z" '
        'fill="url(#phalanxGrad)" stroke="#FFFFFF" stroke-width="2"/>\n'
        '  <path d="M32 18 V46 C37.5 43 42 37 42 30 V21 Z" fill="#0070BA" opacity="0.3"/>\n'
        '  <circle cx="32" cy="30" r="4" fill="#002C6C"/>\n'
        "</svg>"
    )
    (public_dir / "favicon.svg").write_text(svg_content, encoding="utf-8")
    print("Wrote web/public/favicon.svg")
    print("Wrote web/public/favicon.svg")

    # 2. PNG Icons
    png_32 = create_png(32, 32)
    png_180 = create_png(180, 180)
    png_192 = create_png(192, 192)
    png_512 = create_png(512, 512)

    (public_dir / "apple-touch-icon.png").write_bytes(png_180)
    (public_dir / "icon-192.png").write_bytes(png_192)
    (public_dir / "icon-512.png").write_bytes(png_512)
    print("Wrote apple-touch-icon.png, icon-192.png, icon-512.png")

    # 3. Favicon ICO
    ico_bytes = create_ico(png_32)
    (public_dir / "favicon.ico").write_bytes(ico_bytes)
    print("Wrote web/public/favicon.ico")


if __name__ == "__main__":
    main()
