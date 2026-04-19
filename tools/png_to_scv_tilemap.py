#!/usr/bin/env python3
"""Import a PNG image as SCV 16x16 background-sprite tiles.

Slices the image into fixed-size tiles, discards entirely transparent tiles,
deduplicates identical encoded patterns, and emits:
  - <name>_tilemap.c  : scv_load_bg_array-compatible pattern bytes + reconstruction
                        tilemap and per-cell colour arrays
  - <name>_tilesheet.png : monochrome preview of unique encoded patterns (optional)

Usage example:
  python tools/png_to_scv_tilemap.py resources/level1.png --name level1
  python tools/png_to_scv_tilemap.py map.png --dark-is-set --max-patterns 64
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency: Pillow. Install with: pip install Pillow"
    ) from exc

# Value used in tilemap/colors arrays to signal "transparent — skip this cell."
TRANSPARENT_INDEX = 255

# Default tile size matches SCV hardware sprite dimensions.
DEFAULT_TILE_SIZE = 16

# SCV hardware palette: index -> (R, G, B)
SCV_PALETTE: Dict[int, Tuple[int, int, int]] = {
    0: (0, 0, 155),
    1: (0, 0, 0),
    2: (0, 0, 255),
    3: (161, 0, 255),
    4: (0, 255, 0),
    5: (160, 255, 157),
    6: (0, 255, 255),
    7: (0, 161, 0),
    8: (255, 0, 0),
    9: (255, 161, 0),
    10: (255, 0, 255),
    11: (255, 160, 159),
    12: (255, 255, 0),
    13: (163, 160, 0),
    14: (161, 160, 157),
    15: (255, 255, 255),
}


class TileImportError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Tile analysis helpers
# ---------------------------------------------------------------------------


def _pixel_is_set(
    rgba: Tuple[int, int, int, int],
    threshold: int,
    *,
    dark_is_set: bool,
    opaque_is_set: bool,
) -> bool:
    """Return True if this pixel should be encoded as a set bit."""
    if rgba[3] < 128:
        return False
    if opaque_is_set:
        return True
    luminance = (rgba[0] * 299 + rgba[1] * 587 + rgba[2] * 114) // 1000
    return luminance < threshold if dark_is_set else luminance >= threshold


def _encode_tile(
    tile: Image.Image,
    *,
    tile_size: int,
    threshold: int,
    dark_is_set: bool,
    opaque_is_set: bool,
) -> bytes:
    """Encode a tile_size x tile_size RGBA tile to SCV 1-bit pattern bytes.

    SCV packing: for each row-pair (y, y+1), emit 4 bytes covering
    x-blocks [0..3], [4..7], [8..11], [12..15].
    High nibble = row y, low nibble = row y+1 (MSB = leftmost pixel).
    Total: (tile_size // 2) * 4 bytes.
    """
    rgba = tile.convert("RGBA")
    pixels = rgba.load()
    data = bytearray()
    for y in range(0, tile_size, 2):
        for block in range(tile_size // 4):
            value = 0
            base_x = block * 4
            for i in range(4):
                x = base_x + i
                if _pixel_is_set(
                    pixels[x, y],
                    threshold,
                    dark_is_set=dark_is_set,
                    opaque_is_set=opaque_is_set,
                ):
                    value |= 1 << (7 - i)
                if _pixel_is_set(
                    pixels[x, y + 1],
                    threshold,
                    dark_is_set=dark_is_set,
                    opaque_is_set=opaque_is_set,
                ):
                    value |= 1 << (3 - i)
            data.append(value)
    return bytes(data)


def _infer_dark_is_set(image: Image.Image, *, threshold: int) -> bool:
    """Infer whether dark or light pixels should be treated as set bits.

    For mostly dark-on-transparent art (for example red logos), this picks
    dark mode; for mostly bright art, it picks light mode.
    """
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    width, height = rgba.size
    dark_count = 0
    light_count = 0
    for y in range(height):
        for x in range(width):
            px = pixels[x, y]
            if px[3] < 128:
                continue
            luminance = (px[0] * 299 + px[1] * 587 + px[2] * 114) // 1000
            if luminance < threshold:
                dark_count += 1
            else:
                light_count += 1
    return dark_count > light_count


def _has_transparent_pixels(image: Image.Image) -> bool:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    width, height = rgba.size
    for y in range(height):
        for x in range(width):
            if pixels[x, y][3] < 128:
                return True
    return False


def _is_fully_transparent(tile: Image.Image, *, tile_size: int) -> bool:
    """Return True if every pixel in the tile has alpha < 128."""
    rgba = tile.convert("RGBA")
    pixels = rgba.load()
    for y in range(tile_size):
        for x in range(tile_size):
            if pixels[x, y][3] >= 128:
                return False
    return True


def _dominant_scv_color(tile: Image.Image, *, tile_size: int) -> int:
    """Return SCV palette index closest to average encoded/visible foreground colour."""
    rgba = tile.convert("RGBA")
    pixels = rgba.load()
    r_sum = g_sum = b_sum = count = 0
    for y in range(tile_size):
        for x in range(tile_size):
            px = pixels[x, y]
            if px[3] >= 128:
                r_sum += px[0]
                g_sum += px[1]
                b_sum += px[2]
                count += 1
    if count == 0:
        return 15  # white fallback
    avg_r = r_sum // count
    avg_g = g_sum // count
    avg_b = b_sum // count
    best_idx = 15
    best_dist: float = float("inf")
    for idx, (pr, pg, pb) in SCV_PALETTE.items():
        dist = (avg_r - pr) ** 2 + (avg_g - pg) ** 2 + (avg_b - pb) ** 2
        if dist < best_dist:
            best_dist = dist
            best_idx = idx
    return best_idx


def _dominant_scv_color_for_mask(
    tile: Image.Image,
    *,
    tile_size: int,
    threshold: int,
    dark_is_set: bool,
    opaque_is_set: bool,
) -> int:
    rgba = tile.convert("RGBA")
    pixels = rgba.load()
    r_sum = g_sum = b_sum = count = 0
    for y in range(tile_size):
        for x in range(tile_size):
            px = pixels[x, y]
            if not _pixel_is_set(
                px,
                threshold,
                dark_is_set=dark_is_set,
                opaque_is_set=opaque_is_set,
            ):
                continue
            r_sum += px[0]
            g_sum += px[1]
            b_sum += px[2]
            count += 1
    if count == 0:
        return _dominant_scv_color(tile, tile_size=tile_size)

    avg_r = r_sum // count
    avg_g = g_sum // count
    avg_b = b_sum // count

    best_idx = 15
    best_dist: float = float("inf")
    for idx, (pr, pg, pb) in SCV_PALETTE.items():
        dist = (avg_r - pr) ** 2 + (avg_g - pg) ** 2 + (avg_b - pb) ** 2
        if dist < best_dist:
            best_dist = dist
            best_idx = idx
    return best_idx


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------


def process_tilemap(
    path: Path,
    *,
    tile_size: int,
    threshold: int,
    dark_is_set: Optional[bool],
    opaque_is_set: Optional[bool],
    max_patterns: Optional[int],
) -> Tuple[List[bytes], List[int], List[int], int, int, int, int, str]:
    """Slice, encode, deduplicate, and map a PNG image.

    Returns:
        patterns        Unique encoded tiles, each ``(tile_size//2)*4`` bytes.
        tilemap_flat    Flat map_h*map_w list of pattern indices;
                        TRANSPARENT_INDEX means the cell is empty/skip.
        colors_flat     Flat map_h*map_w list of SCV colour attributes (0-15);
                        TRANSPARENT_INDEX for empty cells.
        map_width
        map_height
        n_transparent   Tiles discarded as fully transparent (or all-zero).
        n_duplicates    Tiles whose encoded form already existed.
        mask_mode       One of "opaque", "dark", "light".
    """
    if not path.exists():
        raise TileImportError(f"Input PNG not found: {path}")

    image = Image.open(path).convert("RGBA")
    width, height = image.size

    if opaque_is_set is None:
        # If caller explicitly chose dark/light luminance masking, keep that
        # choice and do not override with alpha-only opaque mode.
        if dark_is_set is None:
            # For transparency-authored art, alpha is usually the best foreground mask.
            opaque_is_set = _has_transparent_pixels(image)
        else:
            opaque_is_set = False

    if dark_is_set is None:
        dark_is_set = _infer_dark_is_set(image, threshold=threshold)

    if tile_size <= 0:
        raise TileImportError("tile-size must be positive")
    if width % tile_size != 0 or height % tile_size != 0:
        raise TileImportError(
            f"Image size {width}x{height} is not divisible by "
            f"tile size {tile_size}x{tile_size}"
        )

    map_w = width // tile_size
    map_h = height // tile_size

    patterns: List[bytes] = []
    encoded_to_index: Dict[bytes, int] = {}
    tilemap_flat: List[int] = []
    colors_flat: List[int] = []
    n_transparent = 0
    n_duplicates = 0

    for row in range(map_h):
        for col in range(map_w):
            tile = image.crop((
                col * tile_size,
                row * tile_size,
                (col + 1) * tile_size,
                (row + 1) * tile_size,
            ))

            # Discard fully transparent tiles.
            if _is_fully_transparent(tile, tile_size=tile_size):
                tilemap_flat.append(TRANSPARENT_INDEX)
                colors_flat.append(TRANSPARENT_INDEX)
                n_transparent += 1
                continue

            encoded = _encode_tile(
                tile,
                tile_size=tile_size,
                threshold=threshold,
                dark_is_set=dark_is_set,
                opaque_is_set=opaque_is_set,
            )

            # Also discard tiles that encode to all zeros (invisible).
            if not any(encoded):
                tilemap_flat.append(TRANSPARENT_INDEX)
                colors_flat.append(TRANSPARENT_INDEX)
                n_transparent += 1
                continue

            idx = encoded_to_index.get(encoded)
            if idx is None:
                idx = len(patterns)
                if max_patterns is not None and idx >= max_patterns:
                    raise TileImportError(
                        f"Unique pattern count exceeded limit of {max_patterns} "
                        f"at tile col={col} row={row}"
                    )
                patterns.append(encoded)
                encoded_to_index[encoded] = idx
            else:
                n_duplicates += 1

            color = _dominant_scv_color_for_mask(
                tile,
                tile_size=tile_size,
                threshold=threshold,
                dark_is_set=dark_is_set,
                opaque_is_set=opaque_is_set,
            )
            tilemap_flat.append(idx)
            colors_flat.append(color)

    if opaque_is_set:
        mask_mode = "opaque"
    else:
        mask_mode = "dark" if dark_is_set else "light"

    return (
        patterns,
        tilemap_flat,
        colors_flat,
        map_w,
        map_h,
        n_transparent,
        n_duplicates,
        mask_mode,
    )


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _render_tilesheet(
    patterns: List[bytes],
    output_path: Path,
    *,
    tile_size: int,
    sheet_columns: int = 8,
) -> None:
    """Write a monochrome tilesheet PNG showing all unique encoded patterns."""
    count = len(patterns)
    rows = max(1, math.ceil(count / sheet_columns))
    sheet = Image.new(
        "RGBA",
        (sheet_columns * tile_size, rows * tile_size),
        (0, 0, 0, 0),
    )
    bytes_per_tile = (tile_size // 2) * 4
    for pi, pattern in enumerate(patterns):
        frame = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
        fp = frame.load()
        cursor = 0
        for y in range(0, tile_size, 2):
            for block in range(tile_size // 4):
                if cursor >= bytes_per_tile:
                    break
                value = pattern[cursor]
                cursor += 1
                base_x = block * 4
                for i in range(4):
                    if value & (1 << (7 - i)):
                        fp[base_x + i, y] = (255, 255, 255, 255)
                    if value & (1 << (3 - i)):
                        fp[base_x + i, y + 1] = (255, 255, 255, 255)
        left = (pi % sheet_columns) * tile_size
        top = (pi // sheet_columns) * tile_size
        sheet.paste(frame, (left, top))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)


def _format_byte_array(name: str, values: List[int], *, cols: int = 16) -> str:
    """Format a C ``const unsigned char`` array."""
    lines = [f"const unsigned char {name}[] = {{"]
    for start in range(0, len(values), cols):
        chunk = values[start : start + cols]
        rendered = ", ".join(f"0x{v:02X}" for v in chunk)
        suffix = "," if start + cols < len(values) else ""
        lines.append(f"    {rendered}{suffix}")
    lines.append("};")
    return "\n".join(lines)


def _format_int_rows(rows: List[List[int]]) -> str:
    return "\n".join(
        "    " + ", ".join(str(v) for v in row) + ","
        for row in rows
    )


def _write_c_output(
    path: Path,
    *,
    name: str,
    patterns: List[bytes],
    tilemap_flat: List[int],
    colors_flat: List[int],
    map_w: int,
    map_h: int,
    source_image: Path,
) -> None:
    pattern_bytes = [b for pat in patterns for b in pat]
    tilemap_rows = [tilemap_flat[r * map_w : (r + 1) * map_w] for r in range(map_h)]
    colors_rows = [colors_flat[r * map_w : (r + 1) * map_w] for r in range(map_h)]

    lines = [
        "/* Auto-generated by tools/png_to_scv_tilemap.py */",
        f"/* Source image: {source_image} */",
        f"/* {map_w}x{map_h} tiles, {len(patterns)} unique patterns */",
        f"/* {TRANSPARENT_INDEX} in tilemap/colors = fully transparent, skip this cell */",
        "",
        "/* Load into background pattern bank 0..63 with: */",
        f"/*   scv_load_bg_pattern_array(0, {name}_patterns, {name}_pattern_count); */",
        f"/* Draw with: {name}_draw_map(base_sprite_id, offset_x, offset_y); */",
        "",
        _format_byte_array(f"{name}_patterns", pattern_bytes),
        "",
        f"const int {name}_pattern_count = {len(patterns)};",
        f"const int {name}_map_width = {map_w};",
        f"const int {name}_map_height = {map_h};",
        "",
        f"/* Pattern index per cell; {TRANSPARENT_INDEX} = skip */",
        f"const int {name}_tilemap[] = {{",
        _format_int_rows(tilemap_rows),
        "};",
        "",
        f"/* SCV colour attribute (0-15) per cell; {TRANSPARENT_INDEX} = skip */",
        f"const int {name}_colors[] = {{",
        _format_int_rows(colors_rows),
        "};",
        "",
        f"void {name}_draw_map(int base_sprite_id, int offset_x, int offset_y) {{",
        "    int draw_x;",
        "    int draw_y;",
        "    int draw_id;",
        "    int draw_idx;",
        "    int draw_pat;",
        "    int draw_col;",
        "",
        "    draw_id = base_sprite_id;",
        "    draw_y = 0;",
        f"    while (draw_y < {name}_map_height) {{",
        "        draw_x = 0;",
        f"        while (draw_x < {name}_map_width) {{",
        f"            draw_idx = (draw_y * {name}_map_width) + draw_x;",
        f"            draw_pat = {name}_tilemap[draw_idx];",
        f"            draw_col = {name}_colors[draw_idx];",
        "            if (draw_pat != 255) {",
        "                scv_set_hw_sprite_raw(",
        "                    draw_id,",
        "                    offset_x + (draw_x * 16),",
        "                    offset_y + (draw_y * 16),",
        "                    draw_pat,",
        "                    draw_col",
        "                );",
        "                draw_id = draw_id + 1;",
        "            }",
        "            draw_x = draw_x + 1;",
        "        }",
        "        draw_y = draw_y + 1;",
        "    }",
        "",
        "    while (draw_id < 64) {",
        "        scv_hide_hw_sprite(draw_id);",
        "        draw_id = draw_id + 1;",
        "    }",
        "}",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Import a PNG image as SCV 16x16 background-sprite tiles: "
            "slice, deduplicate, discard transparent tiles, and emit "
            "scv_load_bg_pattern_array-compatible C data with a reconstruction tilemap."
        )
    )
    parser.add_argument(
        "input",
        help="Path to source PNG (dimensions must be divisible by tile size)",
    )
    parser.add_argument(
        "--tile-size",
        type=int,
        default=DEFAULT_TILE_SIZE,
        metavar="N",
        help=f"Square tile size in pixels (default: {DEFAULT_TILE_SIZE})",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=128,
        metavar="N",
        help="Luminance threshold for 1-bit encoding, 0-255 (default: 128)",
    )
    parser.add_argument(
        "--dark-is-set",
        action="store_true",
        help="Treat dark pixels as set bits",
    )
    parser.add_argument(
        "--light-is-set",
        action="store_true",
        help="Treat light pixels as set bits",
    )
    parser.add_argument(
        "--opaque-is-set",
        action="store_true",
        help="Treat every opaque pixel as set bit (recommended for alpha-authored art)",
    )
    parser.add_argument(
        "--name",
        help="Base C symbol name and output file stem (default: input file stem)",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory for emitted files (default: same directory as input)",
    )
    parser.add_argument(
        "--max-patterns",
        type=int,
        metavar="N",
        help="Hard limit on unique patterns; fail if exceeded",
    )
    parser.add_argument(
        "--no-tilesheet",
        action="store_true",
        help="Skip emitting the tilesheet preview PNG",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    input_path = Path(args.input)
    name = args.name or input_path.stem
    output_dir = Path(args.output_dir) if args.output_dir else input_path.parent

    selected_count = int(args.dark_is_set) + int(args.light_is_set) + int(args.opaque_is_set)
    if selected_count > 1:
        print("error: --dark-is-set, --light-is-set, and --opaque-is-set are mutually exclusive")
        return 2

    selected_dark_is_set: Optional[bool] = None
    selected_opaque_is_set: Optional[bool] = None
    if args.dark_is_set:
        selected_dark_is_set = True
    elif args.light_is_set:
        selected_dark_is_set = False
    elif args.opaque_is_set:
        selected_opaque_is_set = True

    try:
        (
            patterns,
            tilemap_flat,
            colors_flat,
            map_w,
            map_h,
            n_transparent,
            n_duplicates,
            mask_mode,
        ) = (
            process_tilemap(
                input_path,
                tile_size=args.tile_size,
                threshold=args.threshold,
                dark_is_set=selected_dark_is_set,
                opaque_is_set=selected_opaque_is_set,
                max_patterns=args.max_patterns,
            )
        )
    except TileImportError as exc:
        print(f"error: {exc}")
        return 2

    c_path = output_dir / f"{name}_tilemap.c"
    _write_c_output(
        c_path,
        name=name,
        patterns=patterns,
        tilemap_flat=tilemap_flat,
        colors_flat=colors_flat,
        map_w=map_w,
        map_h=map_h,
        source_image=input_path,
    )

    total_tiles = map_w * map_h
    print(
        f"tiles={total_tiles}  unique_patterns={len(patterns)}  "
        f"transparent_skipped={n_transparent}  duplicates_reused={n_duplicates}"
    )
    print(f"mask_mode={mask_mode}")
    print(f"wrote: {c_path}")

    if not args.no_tilesheet:
        sheet_path = output_dir / f"{name}_tilesheet.png"
        _render_tilesheet(patterns, sheet_path, tile_size=args.tile_size)
        print(f"wrote: {sheet_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
