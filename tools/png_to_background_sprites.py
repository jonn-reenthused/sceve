#!/usr/bin/env python3
"""Generate SCV 16x16 background-sprite assets and C fragment data from a PNG."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency: Pillow. Install with: pip install Pillow"
    ) from exc


DISPLAY_START_Y = 0x1C
TILE_SIZE = 16
MAX_PATTERNS = 64
DEFAULT_MAX_SPRITES = 64
SHEET_COLUMNS = 8

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


class BackgroundSpriteError(RuntimeError):
    pass


@dataclass(frozen=True)
class SpriteEntry:
    pos_y: int
    color: int
    pos_x: int
    pattern: int


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a PNG region into deduped SCV 16x16 background-sprite patterns "
            "plus a generated C fragment."
        )
    )
    parser.add_argument("input", help="Path to source PNG")
    parser.add_argument(
        "--crop",
        nargs=4,
        type=int,
        metavar=("X", "Y", "WIDTH", "HEIGHT"),
        help="Optional crop rectangle in source pixels",
    )
    parser.add_argument(
        "--output-asset",
        required=True,
        help="Path to the generated deduped monochrome spritesheet PNG",
    )
    parser.add_argument(
        "--output-c",
        required=True,
        help="Path to the generated C fragment",
    )
    parser.add_argument(
        "--asset-path-literal",
        required=True,
        help="Path literal to embed in #pragma scv_asset, usually relative to the C file",
    )
    parser.add_argument(
        "--asset-name",
        required=True,
        help="Asset name to use in the generated #pragma scv_asset",
    )
    parser.add_argument(
        "--symbol-prefix",
        required=True,
        help="Prefix for generated C symbols and helper functions",
    )
    parser.add_argument(
        "--max-sprites",
        type=int,
        default=DEFAULT_MAX_SPRITES,
        help="Maximum allowed screen entries to emit (default: 64)",
    )
    return parser.parse_args()


def _source_pixel_to_color(rgba: Sequence[int]) -> int | None:
    if rgba[3] < 128:
        return None
    rgb = (rgba[0], rgba[1], rgba[2])
    if rgb == (0, 0, 0):
        return None
    # Reduced source art can contain antialias colors (green/gray). Collapse
    # everything except obvious yellow highlights to cyan for stable output.
    if rgba[0] >= 192 and rgba[1] >= 192 and rgba[2] <= 96:
        return 12
    return 6


def _encode_color_pattern(tile: Image.Image, target_color: int) -> bytes:
    rgba = tile.convert("RGBA")
    pixels = rgba.load()
    out = bytearray()

    for y in range(0, TILE_SIZE, 2):
        for block in range(4):
            value = 0
            base_x = block * 4
            for index in range(4):
                x = base_x + index
                top_color = _source_pixel_to_color(pixels[x, y])
                bottom_color = _source_pixel_to_color(pixels[x, y + 1])
                if top_color == target_color:
                    value |= 1 << (7 - index)
                if bottom_color == target_color:
                    value |= 1 << (3 - index)
            out.append(value)

    return bytes(out)


def _tile_to_layers(tile: Image.Image) -> List[Tuple[bytes, int]]:
    rgba = tile.convert("RGBA")
    pixels = rgba.load()
    color_counts: Dict[int, int] = {}
    for y in range(TILE_SIZE):
        for x in range(TILE_SIZE):
            color = _source_pixel_to_color(pixels[x, y])
            if color is None:
                continue
            color_counts[color] = color_counts.get(color, 0) + 1

    if not color_counts:
        return []

    layers: List[Tuple[bytes, int]] = []
    ordered_colors = sorted(color_counts, key=lambda code: (-color_counts[code], code))
    for color in ordered_colors:
        pattern = _encode_color_pattern(tile, color)
        if any(pattern):
            layers.append((pattern, color))

    return layers


def _render_pattern_sheet(patterns: List[bytes], output_path: Path) -> None:
    rows = (len(patterns) + SHEET_COLUMNS - 1) // SHEET_COLUMNS
    sheet = Image.new("RGBA", (SHEET_COLUMNS * TILE_SIZE, rows * TILE_SIZE), (0, 0, 0, 0))

    for pattern_index, pattern in enumerate(patterns):
        frame = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
        frame_pixels = frame.load()
        cursor = 0
        for y in range(0, TILE_SIZE, 2):
            for block in range(4):
                value = pattern[cursor]
                cursor += 1
                base_x = block * 4
                for index in range(4):
                    if value & (1 << (7 - index)):
                        frame_pixels[base_x + index, y] = (0, 0, 0, 255)
                    if value & (1 << (3 - index)):
                        frame_pixels[base_x + index, y + 1] = (0, 0, 0, 255)

        left = (pattern_index % SHEET_COLUMNS) * TILE_SIZE
        top = (pattern_index // SHEET_COLUMNS) * TILE_SIZE
        sheet.paste(frame, (left, top))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)


def _format_const_array(name: str, values: List[int]) -> str:
    lines = [f"const int {name}[] = {{"]
    for start in range(0, len(values), 8):
        chunk = values[start : start + 8]
        rendered = ", ".join(str(value) for value in chunk)
        suffix = "," if start + 8 < len(values) else ""
        lines.append(f"    {rendered}{suffix}")
    lines.append("};")
    return "\n".join(lines)


def _generate_c_fragment(
    *,
    asset_name: str,
    asset_path_literal: str,
    symbol_prefix: str,
    entries: List[SpriteEntry],
    pattern_count: int,
    max_sprites: int,
) -> str:
    xs = [entry.pos_x for entry in entries]
    ys = [entry.pos_y for entry in entries]
    patterns = [entry.pattern for entry in entries]
    colors = [entry.color for entry in entries]

    lines = [
        f'#pragma scv_asset spritesheet {asset_name} "{asset_path_literal}" 16 16',
        "",
        f"const int {symbol_prefix}_sprite_count = {len(entries)};",
        f"const int {symbol_prefix}_sprite_limit = {max_sprites};",
        f"const int {symbol_prefix}_pattern_count = {pattern_count};",
        _format_const_array(f"{symbol_prefix}_x", xs),
        "",
        _format_const_array(f"{symbol_prefix}_y", ys),
        "",
        _format_const_array(f"{symbol_prefix}_pattern", patterns),
        "",
        _format_const_array(f"{symbol_prefix}_color", colors),
        "",
        f"void {symbol_prefix}_load_tiles(void) {{",
    ]
    for pattern_index in range(pattern_count):
        lines.append(f"    scv_asset_{asset_name}_{pattern_index}_load({pattern_index});")
    lines.extend(
        [
            "}",
            "",
            f"void {symbol_prefix}_draw_screen(void) {{",
            "    int i;",
            "    i = 0;",
            f"    while (i < {symbol_prefix}_sprite_count) {{",
            f"        scv_set_hw_sprite(i, {symbol_prefix}_x[i], {symbol_prefix}_y[i], {symbol_prefix}_pattern[i], {symbol_prefix}_color[i]);",
            "        i = i + 1;",
            "    }",
            f"    while (i < {symbol_prefix}_sprite_limit) {{",
            "        scv_hide_hw_sprite(i);",
            "        i = i + 1;",
            "    }",
            "}",
        ]
    )
    return "\n".join(lines) + "\n"


def _load_source_image(path: Path, crop: Tuple[int, int, int, int] | None) -> Image.Image:
    if not path.exists():
        raise BackgroundSpriteError(f"Input PNG not found: {path}")
    image = Image.open(path).convert("RGBA")
    if crop is not None:
        crop_x, crop_y, crop_width, crop_height = crop
        image = image.crop((crop_x, crop_y, crop_x + crop_width, crop_y + crop_height))
    width, height = image.size
    if width % TILE_SIZE != 0 or height % TILE_SIZE != 0:
        raise BackgroundSpriteError(
            f"Image size {width}x{height} must be divisible by {TILE_SIZE}x{TILE_SIZE}"
        )
    return image


def build_background_sprite_data(
    image: Image.Image,
    *,
    max_sprites: int,
) -> Tuple[List[bytes], List[SpriteEntry]]:
    pattern_to_index: Dict[bytes, int] = {}
    patterns: List[bytes] = []
    entries: List[SpriteEntry] = []
    width, height = image.size

    for top in range(0, height, TILE_SIZE):
        for left in range(0, width, TILE_SIZE):
            tile = image.crop((left, top, left + TILE_SIZE, top + TILE_SIZE))
            layers = _tile_to_layers(tile)
            if not layers:
                continue
            for pattern_bytes, color in layers:
                pattern_index = pattern_to_index.get(pattern_bytes)
                if pattern_index is None:
                    pattern_index = len(patterns)
                    if pattern_index >= MAX_PATTERNS:
                        raise BackgroundSpriteError(
                            f"Too many unique patterns: {pattern_index + 1} > {MAX_PATTERNS}"
                        )
                    pattern_to_index[pattern_bytes] = pattern_index
                    patterns.append(pattern_bytes)
                entries.append(
                    SpriteEntry(
                        pos_y=(top + DISPLAY_START_Y) & 0xFE,
                        color=color,
                        pos_x=(left + 20) & 0xFE,
                        pattern=pattern_index,
                    )
                )

    if len(entries) > max_sprites:
        raise BackgroundSpriteError(
            f"Too many sprite entries: {len(entries)} > {max_sprites}"
        )
    return patterns, entries


def main() -> int:
    args = _parse_args()
    crop = tuple(args.crop) if args.crop is not None else None

    try:
        image = _load_source_image(Path(args.input), crop)
        patterns, entries = build_background_sprite_data(image, max_sprites=args.max_sprites)
    except BackgroundSpriteError as exc:
        print(f"error: {exc}")
        return 2

    output_asset = Path(args.output_asset)
    output_c = Path(args.output_c)
    _render_pattern_sheet(patterns, output_asset)
    c_fragment = _generate_c_fragment(
        asset_name=args.asset_name,
        asset_path_literal=args.asset_path_literal,
        symbol_prefix=args.symbol_prefix,
        entries=entries,
        pattern_count=len(patterns),
        max_sprites=args.max_sprites,
    )
    output_c.parent.mkdir(parents=True, exist_ok=True)
    output_c.write_text(c_fragment, encoding="utf-8")

    print(f"patterns={len(patterns)} sprites={len(entries)}")
    print(f"wrote asset: {output_asset}")
    print(f"wrote c fragment: {output_c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())