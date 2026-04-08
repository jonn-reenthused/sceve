#!/usr/bin/env python3
"""Convert PNG images into SCV 16x16 hardware sprite data."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

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


def _pixel_is_set(rgba: Sequence[int], threshold: int) -> bool:
    if rgba[3] < 128:
        return False
    luminance = (rgba[0] * 299 + rgba[1] * 587 + rgba[2] * 114) // 1000
    return luminance < threshold


def _frame_to_bytes(image: Image.Image, *, threshold: int) -> List[int]:
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
                if _pixel_is_set(pixels[x, y], threshold):
                    value |= 1 << (7 - i)
                if _pixel_is_set(pixels[x, y + 1], threshold):
                    value |= 1 << (3 - i)
            data.append(value)
    return data


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
    if frame_width != 16 or frame_height != 16:
        raise PngAssetError(
            f"Only 16x16 sprite frames are currently supported, got {frame_width}x{frame_height}"
        )

    image = Image.open(path)
    width, height = image.size

    if kind == "sprite":
        if width != 16 or height != 16:
            raise PngAssetError(
                f"Sprite asset {name} must be exactly 16x16 pixels, got {width}x{height}"
            )
        return [
            ScvPngFrame(
                symbol_name=f"asset_{name}",
                loader_name=f"scv_asset_{name}_load",
                bytes_out=_frame_to_bytes(image, threshold=threshold),
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
            frames.append(
                ScvPngFrame(
                    symbol_name=f"asset_{name}_{frame_index}",
                    loader_name=f"scv_asset_{name}_{frame_index}_load",
                    bytes_out=_frame_to_bytes(crop, threshold=threshold),
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