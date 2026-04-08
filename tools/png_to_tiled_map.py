#!/usr/bin/env python3
"""Slice a PNG map into tiles, deduplicate them, and emit a tilesheet plus map indices."""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency: Pillow. Install with: pip install Pillow"
    ) from exc


class TileMapError(RuntimeError):
    pass


@dataclass
class TileMapResult:
    map_width: int
    map_height: int
    tile_width: int
    tile_height: int
    unique_tiles: List[Image.Image]
    tilemap_rows: List[List[int]]
    duplicate_tiles: int


@dataclass
class TileMapSegment:
    index: int
    start_col: int
    end_col: int
    result: TileMapResult


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Slice a PNG map into fixed-size tiles, reuse identical tiles, and emit "
            "a tilesheet PNG plus an indexed map file"
        )
    )
    parser.add_argument("input", help="Path to source map PNG")
    parser.add_argument(
        "--tile-size",
        nargs=2,
        type=int,
        metavar=("WIDTH", "HEIGHT"),
        default=(8, 8),
        help="Tile width and height in pixels (default: 8 8)",
    )
    parser.add_argument(
        "--name",
        help="Base output name. Defaults to the input file stem.",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory for emitted files. Defaults to the input file directory.",
    )
    parser.add_argument(
        "--sheet-columns",
        type=int,
        default=8,
        help="Number of columns in the emitted tilesheet PNG (default: 8)",
    )
    parser.add_argument(
        "--map-format",
        choices=("json", "csv", "both"),
        default="json",
        help="Indexed map output format (default: json)",
    )
    parser.add_argument(
        "--max-tiles",
        type=int,
        help="Optional hard limit for unique tiles; fail if exceeded.",
    )
    parser.add_argument(
        "--split-max-tiles",
        type=int,
        help=(
            "Greedily split the map into horizontal column segments so each segment "
            "stays at or below this unique tile limit. Emits one tilesheet/map pair per segment."
        ),
    )
    parser.add_argument(
        "--split-screen-width",
        type=int,
        help=(
            "Split into fixed-width horizontal segments (in map tiles), e.g. 32 for one "
            "screen. Optional --max-tiles validates each screen-sized segment."
        ),
    )
    return parser.parse_args()


def _validate_image_size(
    image: Image.Image,
    *,
    tile_width: int,
    tile_height: int,
) -> Tuple[int, int]:
    width, height = image.size
    if tile_width <= 0 or tile_height <= 0:
        raise TileMapError("Tile size must be positive")
    if width % tile_width != 0 or height % tile_height != 0:
        raise TileMapError(
            f"Image size {width}x{height} is not divisible by tile size {tile_width}x{tile_height}"
        )
    return width // tile_width, height // tile_height


def slice_tilemap(
    path: Path,
    *,
    tile_width: int,
    tile_height: int,
    max_tiles: int | None,
) -> TileMapResult:
    if not path.exists():
        raise TileMapError(f"Input PNG not found: {path}")

    image = Image.open(path).convert("RGBA")
    map_width, map_height = _validate_image_size(
        image,
        tile_width=tile_width,
        tile_height=tile_height,
    )

    unique_tiles: List[Image.Image] = []
    tile_to_index: Dict[bytes, int] = {}
    tilemap_rows: List[List[int]] = []
    duplicate_tiles = 0

    for tile_y in range(map_height):
        row_indices: List[int] = []
        top = tile_y * tile_height
        for tile_x in range(map_width):
            left = tile_x * tile_width
            tile = image.crop((left, top, left + tile_width, top + tile_height))
            tile_bytes = tile.tobytes()
            tile_index = tile_to_index.get(tile_bytes)
            if tile_index is None:
                tile_index = len(unique_tiles)
                unique_tiles.append(tile)
                tile_to_index[tile_bytes] = tile_index
                if max_tiles is not None and len(unique_tiles) > max_tiles:
                    raise TileMapError(
                        f"Unique tile count exceeded limit: {len(unique_tiles)} > {max_tiles}"
                    )
            else:
                duplicate_tiles += 1
            row_indices.append(tile_index)
        tilemap_rows.append(row_indices)

    return TileMapResult(
        map_width=map_width,
        map_height=map_height,
        tile_width=tile_width,
        tile_height=tile_height,
        unique_tiles=unique_tiles,
        tilemap_rows=tilemap_rows,
        duplicate_tiles=duplicate_tiles,
    )


def _load_tile_grid(
    path: Path,
    *,
    tile_width: int,
    tile_height: int,
) -> Tuple[List[List[Image.Image]], int, int]:
    if not path.exists():
        raise TileMapError(f"Input PNG not found: {path}")

    image = Image.open(path).convert("RGBA")
    map_width, map_height = _validate_image_size(
        image,
        tile_width=tile_width,
        tile_height=tile_height,
    )

    grid: List[List[Image.Image]] = []
    for tile_y in range(map_height):
        row: List[Image.Image] = []
        top = tile_y * tile_height
        for tile_x in range(map_width):
            left = tile_x * tile_width
            row.append(image.crop((left, top, left + tile_width, top + tile_height)))
        grid.append(row)
    return grid, map_width, map_height


def _dedupe_tile_rows(
    tile_rows: Sequence[Sequence[Image.Image]],
    *,
    tile_width: int,
    tile_height: int,
    max_tiles: int | None,
) -> TileMapResult:
    unique_tiles: List[Image.Image] = []
    tile_to_index: Dict[bytes, int] = {}
    tilemap_rows: List[List[int]] = []
    duplicate_tiles = 0

    for tile_row in tile_rows:
        row_indices: List[int] = []
        for tile in tile_row:
            tile_bytes = tile.tobytes()
            tile_index = tile_to_index.get(tile_bytes)
            if tile_index is None:
                tile_index = len(unique_tiles)
                unique_tiles.append(tile)
                tile_to_index[tile_bytes] = tile_index
                if max_tiles is not None and len(unique_tiles) > max_tiles:
                    raise TileMapError(
                        f"Unique tile count exceeded limit: {len(unique_tiles)} > {max_tiles}"
                    )
            else:
                duplicate_tiles += 1
            row_indices.append(tile_index)
        tilemap_rows.append(row_indices)

    map_height = len(tilemap_rows)
    map_width = len(tilemap_rows[0]) if tilemap_rows else 0
    return TileMapResult(
        map_width=map_width,
        map_height=map_height,
        tile_width=tile_width,
        tile_height=tile_height,
        unique_tiles=unique_tiles,
        tilemap_rows=tilemap_rows,
        duplicate_tiles=duplicate_tiles,
    )


def split_tilemap_by_columns(
    path: Path,
    *,
    tile_width: int,
    tile_height: int,
    max_tiles: int,
) -> List[TileMapSegment]:
    if max_tiles <= 0:
        raise TileMapError("split-max-tiles must be positive")

    tile_grid, map_width, _map_height = _load_tile_grid(
        path,
        tile_width=tile_width,
        tile_height=tile_height,
    )

    segments: List[TileMapSegment] = []
    start_col = 0
    segment_index = 0

    while start_col < map_width:
        end_col = start_col
        best_result: TileMapResult | None = None

        while end_col < map_width:
            candidate_rows = [row[start_col : end_col + 1] for row in tile_grid]
            try:
                candidate_result = _dedupe_tile_rows(
                    candidate_rows,
                    tile_width=tile_width,
                    tile_height=tile_height,
                    max_tiles=max_tiles,
                )
            except TileMapError:
                if best_result is None:
                    raise TileMapError(
                        f"Column {start_col} alone exceeds the unique tile limit of {max_tiles}"
                    )
                break

            best_result = candidate_result
            end_col += 1

        if best_result is None:
            raise TileMapError(
                f"Unable to build a segment starting at column {start_col}"
            )

        segment_end_col = start_col + best_result.map_width - 1
        segments.append(
            TileMapSegment(
                index=segment_index,
                start_col=start_col,
                end_col=segment_end_col,
                result=best_result,
            )
        )
        segment_index += 1
        start_col = segment_end_col + 1

    return segments


def split_tilemap_by_fixed_columns(
    path: Path,
    *,
    tile_width: int,
    tile_height: int,
    segment_width: int,
    max_tiles: int | None,
) -> List[TileMapSegment]:
    if segment_width <= 0:
        raise TileMapError("split-screen-width must be positive")

    tile_grid, map_width, _map_height = _load_tile_grid(
        path,
        tile_width=tile_width,
        tile_height=tile_height,
    )

    segments: List[TileMapSegment] = []
    segment_index = 0
    start_col = 0
    while start_col < map_width:
        end_col = min(start_col + segment_width, map_width) - 1
        candidate_rows = [row[start_col : end_col + 1] for row in tile_grid]
        try:
            result = _dedupe_tile_rows(
                candidate_rows,
                tile_width=tile_width,
                tile_height=tile_height,
                max_tiles=max_tiles,
            )
        except TileMapError as exc:
            raise TileMapError(
                f"Screen segment cols {start_col}-{end_col} failed: {exc}"
            ) from exc

        segments.append(
            TileMapSegment(
                index=segment_index,
                start_col=start_col,
                end_col=end_col,
                result=result,
            )
        )
        segment_index += 1
        start_col = end_col + 1

    return segments


def _build_tilesheet(
    tiles: List[Image.Image],
    *,
    tile_width: int,
    tile_height: int,
    sheet_columns: int,
) -> Image.Image:
    if sheet_columns <= 0:
        raise TileMapError("sheet-columns must be positive")
    if not tiles:
        raise TileMapError("No tiles were generated")

    columns = min(sheet_columns, len(tiles))
    rows = math.ceil(len(tiles) / columns)
    sheet = Image.new("RGBA", (columns * tile_width, rows * tile_height), (0, 0, 0, 0))

    for index, tile in enumerate(tiles):
        dest_x = (index % columns) * tile_width
        dest_y = (index // columns) * tile_height
        sheet.paste(tile, (dest_x, dest_y))

    return sheet


def _write_json_map(path: Path, result: TileMapResult, tilesheet_name: str) -> None:
    payload = {
        "tile_width": result.tile_width,
        "tile_height": result.tile_height,
        "map_width": result.map_width,
        "map_height": result.map_height,
        "unique_tile_count": len(result.unique_tiles),
        "duplicate_tile_count": result.duplicate_tiles,
        "tilesheet": tilesheet_name,
        "rows": result.tilemap_rows,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_csv_map(path: Path, result: TileMapResult) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        for row in result.tilemap_rows:
            writer.writerow(row)


def _write_segment_manifest(
    path: Path,
    *,
    source_image: Path,
    tile_width: int,
    tile_height: int,
    segments: Sequence[TileMapSegment],
    base_name: str,
    map_format: str,
) -> None:
    payload = {
        "source_image": str(source_image),
        "tile_width": tile_width,
        "tile_height": tile_height,
        "segment_count": len(segments),
        "segments": [],
    }
    for segment in segments:
        entry = {
            "index": segment.index,
            "start_col": segment.start_col,
            "end_col": segment.end_col,
            "map_width": segment.result.map_width,
            "map_height": segment.result.map_height,
            "unique_tile_count": len(segment.result.unique_tiles),
            "duplicate_tile_count": segment.result.duplicate_tiles,
            "tilesheet": f"{base_name}_part{segment.index:02d}_tiles.png",
        }
        if map_format in ("json", "both"):
            entry["map_json"] = f"{base_name}_part{segment.index:02d}_map.json"
        if map_format in ("csv", "both"):
            entry["map_csv"] = f"{base_name}_part{segment.index:02d}_map.csv"
        payload["segments"].append(entry)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = _parse_args()
    input_path = Path(args.input)
    tile_width, tile_height = args.tile_size
    output_dir = Path(args.output_dir) if args.output_dir else input_path.parent
    base_name = args.name if args.name else input_path.stem

    try:
        output_dir.mkdir(parents=True, exist_ok=True)

        if args.split_screen_width is not None and args.split_max_tiles is not None:
            raise TileMapError(
                "Use either --split-screen-width or --split-max-tiles, not both"
            )

        if args.split_screen_width is not None:
            segments = split_tilemap_by_fixed_columns(
                input_path,
                tile_width=tile_width,
                tile_height=tile_height,
                segment_width=args.split_screen_width,
                max_tiles=args.max_tiles,
            )
            manifest_path = output_dir / f"{base_name}_manifest.json"

            for segment in segments:
                part_name = f"{base_name}_part{segment.index:02d}"
                tilesheet = _build_tilesheet(
                    segment.result.unique_tiles,
                    tile_width=segment.result.tile_width,
                    tile_height=segment.result.tile_height,
                    sheet_columns=args.sheet_columns,
                )
                tilesheet_path = output_dir / f"{part_name}_tiles.png"
                tilesheet.save(tilesheet_path)

                if args.map_format in ("json", "both"):
                    json_path = output_dir / f"{part_name}_map.json"
                    _write_json_map(json_path, segment.result, tilesheet_path.name)

                if args.map_format in ("csv", "both"):
                    csv_path = output_dir / f"{part_name}_map.csv"
                    _write_csv_map(csv_path, segment.result)

            _write_segment_manifest(
                manifest_path,
                source_image=input_path,
                tile_width=tile_width,
                tile_height=tile_height,
                segments=segments,
                base_name=base_name,
                map_format=args.map_format,
            )
        elif args.split_max_tiles is not None:
            segments = split_tilemap_by_columns(
                input_path,
                tile_width=tile_width,
                tile_height=tile_height,
                max_tiles=args.split_max_tiles,
            )
            manifest_path = output_dir / f"{base_name}_manifest.json"

            for segment in segments:
                part_name = f"{base_name}_part{segment.index:02d}"
                tilesheet = _build_tilesheet(
                    segment.result.unique_tiles,
                    tile_width=segment.result.tile_width,
                    tile_height=segment.result.tile_height,
                    sheet_columns=args.sheet_columns,
                )
                tilesheet_path = output_dir / f"{part_name}_tiles.png"
                tilesheet.save(tilesheet_path)

                if args.map_format in ("json", "both"):
                    json_path = output_dir / f"{part_name}_map.json"
                    _write_json_map(json_path, segment.result, tilesheet_path.name)

                if args.map_format in ("csv", "both"):
                    csv_path = output_dir / f"{part_name}_map.csv"
                    _write_csv_map(csv_path, segment.result)

            _write_segment_manifest(
                manifest_path,
                source_image=input_path,
                tile_width=tile_width,
                tile_height=tile_height,
                segments=segments,
                base_name=base_name,
                map_format=args.map_format,
            )
        else:
            result = slice_tilemap(
                input_path,
                tile_width=tile_width,
                tile_height=tile_height,
                max_tiles=args.max_tiles,
            )

            tilesheet = _build_tilesheet(
                result.unique_tiles,
                tile_width=result.tile_width,
                tile_height=result.tile_height,
                sheet_columns=args.sheet_columns,
            )
            tilesheet_path = output_dir / f"{base_name}_tiles.png"
            tilesheet.save(tilesheet_path)

            if args.map_format in ("json", "both"):
                json_path = output_dir / f"{base_name}_map.json"
                _write_json_map(json_path, result, tilesheet_path.name)

            if args.map_format in ("csv", "both"):
                csv_path = output_dir / f"{base_name}_map.csv"
                _write_csv_map(csv_path, result)
    except TileMapError as exc:
        print(f"error: {exc}")
        return 2

    print(f"input: {input_path}")
    print(f"tile size: {tile_width}x{tile_height}")
    if args.split_screen_width is not None:
        print(f"split screen width: {args.split_screen_width} tiles")
        if args.max_tiles is not None:
            print(f"max tiles per screen: {args.max_tiles}")
        print(f"segments: {len(segments)}")
        for segment in segments:
            total_tiles = segment.result.map_width * segment.result.map_height
            print(
                f"segment {segment.index:02d}: cols {segment.start_col}-{segment.end_col}, "
                f"size {segment.result.map_width}x{segment.result.map_height}, total {total_tiles}, "
                f"unique {len(segment.result.unique_tiles)}, reused {segment.result.duplicate_tiles}"
            )
            print(f"tilesheet: {output_dir / f'{base_name}_part{segment.index:02d}_tiles.png'}")
            if args.map_format in ("json", "both"):
                print(f"map json: {output_dir / f'{base_name}_part{segment.index:02d}_map.json'}")
            if args.map_format in ("csv", "both"):
                print(f"map csv: {output_dir / f'{base_name}_part{segment.index:02d}_map.csv'}")
        print(f"manifest: {output_dir / f'{base_name}_manifest.json'}")
    elif args.split_max_tiles is not None:
        print(f"split max tiles: {args.split_max_tiles}")
        print(f"segments: {len(segments)}")
        for segment in segments:
            total_tiles = segment.result.map_width * segment.result.map_height
            print(
                f"segment {segment.index:02d}: cols {segment.start_col}-{segment.end_col}, "
                f"size {segment.result.map_width}x{segment.result.map_height}, total {total_tiles}, "
                f"unique {len(segment.result.unique_tiles)}, reused {segment.result.duplicate_tiles}"
            )
            print(f"tilesheet: {output_dir / f'{base_name}_part{segment.index:02d}_tiles.png'}")
            if args.map_format in ("json", "both"):
                print(f"map json: {output_dir / f'{base_name}_part{segment.index:02d}_map.json'}")
            if args.map_format in ("csv", "both"):
                print(f"map csv: {output_dir / f'{base_name}_part{segment.index:02d}_map.csv'}")
        print(f"manifest: {output_dir / f'{base_name}_manifest.json'}")
    else:
        total_tiles = result.map_width * result.map_height
        print(f"map size: {result.map_width}x{result.map_height} tiles")
        print(f"total tiles: {total_tiles}")
        print(f"unique tiles: {len(result.unique_tiles)}")
        print(f"reused tiles: {result.duplicate_tiles}")
        print(f"tilesheet: {output_dir / f'{base_name}_tiles.png'}")
        if args.map_format in ("json", "both"):
            print(f"map json: {output_dir / f'{base_name}_map.json'}")
        if args.map_format in ("csv", "both"):
            print(f"map csv: {output_dir / f'{base_name}_map.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())