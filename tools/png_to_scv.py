#!/usr/bin/env python3
"""Convert PNG images into SCV asset frame data.

The supported production path is 16x16 sprite/background-sprite patterns.
8x16 background-character output is retained only for regression probes around
the text/tile plane and should not be treated as a normal custom-background
rendering path.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency: Pillow. Install with: pip install Pillow"
    ) from exc


class PngAssetError(RuntimeError):
    pass


@dataclass
class ScvPngFrame:
    symbol_name: str
    loader_name: str
    bytes_out: List[int]


def _pixel_is_set(
    rgba: Sequence[int],
    threshold: int,
    *,
    dark_is_set: bool,
    opaque_is_set: bool = False,
    transparent_rgb: Optional[Tuple[int, int, int]] = None,
) -> bool:
    if rgba[3] == 0:
        return False
    if transparent_rgb is not None and (rgba[0], rgba[1], rgba[2]) == transparent_rgb:
        return False
    if opaque_is_set:
        return True
    luminance = (rgba[0] * 299 + rgba[1] * 587 + rgba[2] * 114) // 1000
    if dark_is_set:
        return luminance < threshold
    return luminance >= threshold


def _frame_to_bytes(
    image: Image.Image,
    *,
    threshold: int,
    dark_is_set: bool,
    opaque_is_set: bool = False,
    transparent_rgb: Optional[Tuple[int, int, int]] = None,
) -> List[int]:
    width, height = image.size
    if width != 16 or height != 16:
        raise PngAssetError(
            f"SCV hardware sprites must be 16x16 pixels, got {width}x{height}"
        )

    rgba = image.convert("RGBA")
    pixels = rgba.load()
    # SCV sprite bytes are packed as 4x2 pixel chunks in a single bitplane.
    # For each row pair (y, y+1), output 4 bytes spanning x blocks [0..3],[4..7],[8..11],[12..15].
    # In each byte: high nibble is row y (left->right), low nibble is row y+1.
    data: List[int] = []
    for y in range(0, 16, 2):
        for block in range(4):
            value = 0
            base_x = block * 4
            for i in range(4):
                x = base_x + i
                if _pixel_is_set(
                    pixels[x, y],
                    threshold,
                    dark_is_set=dark_is_set,
                    opaque_is_set=opaque_is_set,
                    transparent_rgb=transparent_rgb,
                ):
                    value |= 1 << (7 - i)
                if _pixel_is_set(
                    pixels[x, y + 1],
                    threshold,
                    dark_is_set=dark_is_set,
                    opaque_is_set=opaque_is_set,
                    transparent_rgb=transparent_rgb,
                ):
                    value |= 1 << (3 - i)
            data.append(value)
    return data


def _frame_to_bg_char_bytes(
    image: Image.Image,
    *,
    threshold: int,
    dark_is_set: bool,
    opaque_is_set: bool = False,
    transparent_rgb: Optional[Tuple[int, int, int]] = None,
) -> List[int]:
    width, height = image.size
    if width != 8 or height != 16:
        raise PngAssetError(
            f"SCV background character tiles must be 8x16 pixels, got {width}x{height}"
        )

    rgba = image.convert("RGBA")
    pixels = rgba.load()
    data: List[int] = []
    for y in range(16):
        value = 0
        for x in range(8):
            if _pixel_is_set(
                pixels[x, y],
                threshold,
                dark_is_set=dark_is_set,
                opaque_is_set=opaque_is_set,
                transparent_rgb=transparent_rgb,
            ):
                value |= 1 << (7 - x)
        data.append(value)
    return data


def _background_colorkey(image: Image.Image) -> Optional[Tuple[int, int, int]]:
    """Pick a transparent colorkey for fully opaque background art.

    If the source already has alpha holes, keep alpha-only transparency.
    Otherwise, treat the dominant RGB as backdrop and do not emit bits for it.
    """
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    width, height = rgba.size

    has_alpha_holes = False
    rgb_counts: dict[Tuple[int, int, int], int] = {}
    for y in range(height):
        for x in range(width):
            px = pixels[x, y]
            if px[3] < 128:
                has_alpha_holes = True
                continue
            rgb = (px[0], px[1], px[2])
            rgb_counts[rgb] = rgb_counts.get(rgb, 0) + 1

    if has_alpha_holes or not rgb_counts:
        return None

    return max(rgb_counts.items(), key=lambda item: item[1])[0]


def _asset_transparency_mode(
    image: Image.Image,
    *,
    kind: str,
) -> tuple[bool, Optional[Tuple[int, int, int]]]:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    width, height = rgba.size
    has_alpha_holes = False

    for y in range(height):
        for x in range(width):
            if pixels[x, y][3] < 128:
                has_alpha_holes = True
                break
        if has_alpha_holes:
            break

    if has_alpha_holes:
        return True, None

    if kind in {"background", "backgroundsheet"}:
        return True, _background_colorkey(image)

    return True, None


def load_png_asset_frames(
    path: Path,
    *,
    name: str,
    kind: str,
    frame_width: int,
    frame_height: int,
    threshold: int = 160,
) -> List[ScvPngFrame]:
    if not path.exists():
        raise PngAssetError(f"PNG asset not found: {path}")
    if kind in {"sprite", "spritesheet"}:
        if frame_width != 16 or frame_height != 16:
            raise PngAssetError(
                f"Only 16x16 sprite frames are currently supported, got {frame_width}x{frame_height}"
            )
    elif kind in {"background", "backgroundsheet"}:
        if (frame_width, frame_height) not in {(8, 16), (16, 16)}:
            raise PngAssetError(
                "Background assets must use 16x16 background-sprite tiles in normal use; "
                "8x16 is reserved for regression/probe experiments only; "
                f"got {frame_width}x{frame_height}"
            )

    image = Image.open(path)
    width, height = image.size

    if kind in {"sprite", "background"}:
        if width != frame_width or height != frame_height:
            raise PngAssetError(
                f"Asset {name} must be exactly {frame_width}x{frame_height} pixels, got {width}x{height}"
            )
        opaque_is_set, transparent_rgb = _asset_transparency_mode(image, kind=kind)
        if kind == "background" and frame_width == 8 and frame_height == 16:
            frame_bytes = _frame_to_bg_char_bytes(
                image,
                threshold=threshold,
                dark_is_set=True,
                opaque_is_set=opaque_is_set,
                transparent_rgb=transparent_rgb,
            )
        else:
            frame_bytes = _frame_to_bytes(
                image,
                threshold=threshold,
                dark_is_set=True,
                opaque_is_set=opaque_is_set,
                transparent_rgb=transparent_rgb,
            )
        return [
            ScvPngFrame(
                symbol_name=f"asset_{name}",
                loader_name=f"scv_asset_{name}_load",
                bytes_out=frame_bytes,
            )
        ]

    if width % frame_width != 0 or height % frame_height != 0:
        raise PngAssetError(
            f"Spritesheet {name} size {width}x{height} is not divisible by frame size {frame_width}x{frame_height}"
        )

    frames: List[ScvPngFrame] = []
    frame_index = 0
    for top in range(0, height, frame_height):
        for left in range(0, width, frame_width):
            crop = image.crop((left, top, left + frame_width, top + frame_height))
            opaque_is_set, transparent_rgb = _asset_transparency_mode(crop, kind=kind)
            if kind == "backgroundsheet" and frame_width == 8 and frame_height == 16:
                frame_bytes = _frame_to_bg_char_bytes(
                    crop,
                    threshold=threshold,
                    dark_is_set=True,
                    opaque_is_set=opaque_is_set,
                    transparent_rgb=transparent_rgb,
                )
            else:
                frame_bytes = _frame_to_bytes(
                    crop,
                    threshold=threshold,
                    dark_is_set=True,
                    opaque_is_set=opaque_is_set,
                    transparent_rgb=transparent_rgb,
                )
            frames.append(
                ScvPngFrame(
                    symbol_name=f"asset_{name}_{frame_index}",
                    loader_name=f"scv_asset_{name}_{frame_index}_load",
                    bytes_out=frame_bytes,
                )
            )
            frame_index += 1

    return frames


def _format_frame(frame: ScvPngFrame) -> str:
    lines = [f"@{frame.symbol_name}"]
    for offset in range(0, len(frame.bytes_out), 16):
        chunk = frame.bytes_out[offset : offset + 16]
        rendered = ", ".join(f"0x{value:02X}" for value in chunk)
        lines.append(f"    dc.b {rendered}")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert PNG into SCV sprite data")
    parser.add_argument("input", help="Path to source PNG")
    parser.add_argument("--name", required=True, help="Asset base name")
    parser.add_argument(
        "--sheet",
        nargs=2,
        metavar=("WIDTH", "HEIGHT"),
        help="Treat input as a spritesheet with 16x16 frames",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=160,
        help="Luminance threshold for set pixels (default: 160)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = Path(args.input)
    kind = "spritesheet" if args.sheet else "sprite"
    frame_width = int(args.sheet[0]) if args.sheet else 16
    frame_height = int(args.sheet[1]) if args.sheet else 16

    try:
        frames = load_png_asset_frames(
            path,
            name=args.name,
            kind=kind,
            frame_width=frame_width,
            frame_height=frame_height,
            threshold=args.threshold,
        )
    except PngAssetError as exc:
        print(f"error: {exc}")
        return 2

    print(f"-- asset {args.name} ({len(frames)} frame(s)) from {path}")
    for frame in frames:
        print(_format_frame(frame))
        print(f"-- loader: {frame.loader_name}(pattern_slot)")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())