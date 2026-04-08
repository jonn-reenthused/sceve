#!/usr/bin/env python3
"""Generate the Uridium streaming demo source and per-screen pattern assets."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from PIL import Image

from png_to_background_sprites import build_background_sprite_data, _load_source_image, _render_pattern_sheet

SCREEN_WIDTH = 160
SCREEN_HEIGHT = 96
PATTERN_BANK_SIZE = 64
MAX_STREAM_SCREENS = 4
ROOT_DIR = Path(__file__).resolve().parent.parent
MAP_PATH = ROOT_DIR / "examples/assets/uridiummap.png"
ASSET_DIR = ROOT_DIR / "examples/assets"
OUTPUT_C = ROOT_DIR / "examples/demo_uridium_stream.c"


def fmt_array(name: str, values: List[int]) -> str:
    lines = [f"const int {name}[] = {{"]
    for start in range(0, len(values), 8):
        chunk = values[start : start + 8]
        suffix = "," if start + 8 < len(values) else ""
        lines.append(f"    {', '.join(str(v) for v in chunk)}{suffix}")
    lines.append("};")
    return "\n".join(lines)


def emit_screen_data(screen_index: int, entries, pattern_count: int) -> str:
    prefix = f"uridium_screen_{screen_index:02d}"
    xs = [entry.pos_x for entry in entries]
    ys = [entry.pos_y for entry in entries]
    patterns = [entry.pattern for entry in entries]
    colors = [entry.color for entry in entries]
    return "\n\n".join(
        [
            f"const int {prefix}_sprite_count = {len(entries)};",
            f"const int {prefix}_pattern_count = {pattern_count};",
            fmt_array(f"{prefix}_x", xs),
            fmt_array(f"{prefix}_y", ys),
            fmt_array(f"{prefix}_pattern", patterns),
            fmt_array(f"{prefix}_color", colors),
        ]
    )


def emit_load_screen(screen_index: int, pattern_count: int) -> str:
    prefix = f"uridium_s{screen_index:02d}"
    lines = [f"void load_screen_{screen_index:02d}(void) {{"]
    for pattern_index in range(pattern_count):
        lines.append(
            f"    scv_asset_{prefix}_{pattern_index}_load_raw(active_pattern_base + {pattern_index});"
        )
    lines.append("}")
    return "\n".join(lines)


def emit_draw_screen(screen_index: int) -> str:
    prefix = f"uridium_screen_{screen_index:02d}"
    lines = [
        f"void draw_screen_{screen_index:02d}(void) {{",
        "    int i;",
        "    i = 0;",
        f"    while (i < {prefix}_sprite_count) {{",
        f"        scv_set_hw_sprite_raw(active_sprite_base + i, {prefix}_x[i] + active_x_offset, {prefix}_y[i], {prefix}_pattern[i] + active_pattern_base, {prefix}_color[i]);",
        "        i = i + 1;",
        "    }",
        f"    draw_result = active_sprite_base + {prefix}_sprite_count;",
        "}",
    ]
    return "\n".join(lines)


def emit_dispatches(screen_count: int) -> str:
    load_lines = ["void load_screen_patterns(void) {"]
    draw_lines = ["void draw_screen(void) {"]
    for index in range(screen_count):
        cond = "if" if index == 0 else "else if"
        load_lines.append(f"    {cond} (dispatch_screen_id == {index}) {{")
        load_lines.append(f"        load_screen_{index:02d}();")
        load_lines.append("        return;")
        load_lines.append("    }")

        draw_lines.append(f"    {cond} (dispatch_screen_id == {index}) {{")
        draw_lines.append(f"        draw_screen_{index:02d}();")
        draw_lines.append("        return;")
        draw_lines.append("    }")
    load_lines.append("}")
    draw_lines.append("    draw_result = active_sprite_base;")
    draw_lines.append("}")
    return "\n\n".join(["\n".join(load_lines), "\n".join(draw_lines)])


def build_demo_source(screen_count: int, screen_data_blocks: Iterable[str], load_blocks: Iterable[str], draw_blocks: Iterable[str]) -> str:
    pragma_lines = [
        '#include "../tools/scv_api.h"',
        "",
    ]
    for index in range(screen_count):
        pragma_lines.append(
            f'#pragma scv_asset spritesheet uridium_s{index:02d} "assets/uridium_stream_s{index:02d}.png" 16 16'
        )
    pragma_lines.extend(
        [
            "",
            "int scv_pad1_state;",
            "int scv_pad2_state;",
            "int scv_collision_result;",
            "",
            f"const int uridium_screen_count = {screen_count};",
            f"const int uridium_pattern_bank_size = {PATTERN_BANK_SIZE};",
            "int current_screen;",
            "int next_screen;",
            "int current_pattern_base;",
            "int next_pattern_base;",
            "int scroll_x;",
            "int frame_div;",
            "int dispatch_screen_id;",
            "int active_pattern_base;",
            "int active_sprite_base;",
            "int active_x_offset;",
            "int draw_result;",
            "",
        ]
    )

    body = ["\n\n".join(pragma_lines)]
    body.extend(screen_data_blocks)
    body.extend(load_blocks)
    body.extend(draw_blocks)
    body.append(emit_dispatches(screen_count))
    body.append(
        """
void advance_pair(void) {
    int tmp;
    current_screen = next_screen;
    next_screen = next_screen + 1;
    if (next_screen >= uridium_screen_count) {
        next_screen = 0;
    }
    tmp = current_pattern_base;
    current_pattern_base = next_pattern_base;
    next_pattern_base = tmp;
    dispatch_screen_id = next_screen;
    active_pattern_base = next_pattern_base;
    load_screen_patterns();
}

void draw_pair(void) {
    int sprite_end;
    dispatch_screen_id = current_screen;
    active_sprite_base = 0;
    active_pattern_base = current_pattern_base;
    active_x_offset = scroll_x;
    draw_screen();
    sprite_end = draw_result;

    dispatch_screen_id = next_screen;
    active_sprite_base = sprite_end;
    active_pattern_base = next_pattern_base;
    active_x_offset = scroll_x + 160;
    draw_screen();
    sprite_end = draw_result;

    while (sprite_end < 128) {
        scv_hide_hw_sprite(sprite_end);
        sprite_end = sprite_end + 1;
    }
}

int main(void) {
    scv_set_hw_sprite_mode(1);
    current_screen = 0;
    next_screen = 1;
    current_pattern_base = 0;
    next_pattern_base = 64;
    scroll_x = 0;
    frame_div = 0;

    dispatch_screen_id = current_screen;
    active_pattern_base = current_pattern_base;
    load_screen_patterns();
    dispatch_screen_id = next_screen;
    active_pattern_base = next_pattern_base;
    load_screen_patterns();
    draw_pair();

    while (1) {
        scv_wait_vblank();
        frame_div = frame_div + 1;
        if (frame_div >= 2) {
            frame_div = 0;
            scroll_x = scroll_x - 4;
            if (scroll_x == 96) {
                scroll_x = 0;
                advance_pair();
            }
            draw_pair();
        }
    }
}
""".strip()
    )
    return "\n\n".join(body) + "\n"


def main() -> int:
    map_image = Image.open(MAP_PATH)
    if map_image.size[0] % SCREEN_WIDTH != 0 or map_image.size[1] != SCREEN_HEIGHT:
        raise SystemExit(
            f"Uridium map must be an exact multiple of {SCREEN_WIDTH}x{SCREEN_HEIGHT}, got {map_image.size}"
        )

    screen_count = map_image.size[0] // SCREEN_WIDTH
    if screen_count > MAX_STREAM_SCREENS:
        screen_count = MAX_STREAM_SCREENS
    screen_data_blocks = []
    load_blocks = []
    draw_blocks = []

    for index in range(screen_count):
        crop = _load_source_image(MAP_PATH, (index * SCREEN_WIDTH, 0, SCREEN_WIDTH, SCREEN_HEIGHT))
        patterns, entries = build_background_sprite_data(crop, max_sprites=64)
        if len(patterns) > PATTERN_BANK_SIZE:
            raise SystemExit(
                f"screen {index} needs {len(patterns)} patterns, exceeds bank size {PATTERN_BANK_SIZE}"
            )
        asset_path = ASSET_DIR / f"uridium_stream_s{index:02d}.png"
        _render_pattern_sheet(patterns, asset_path)
        screen_data_blocks.append(emit_screen_data(index, entries, len(patterns)))
        load_blocks.append(emit_load_screen(index, len(patterns)))
        draw_blocks.append(emit_draw_screen(index))

    OUTPUT_C.write_text(
        build_demo_source(screen_count, screen_data_blocks, load_blocks, draw_blocks),
        encoding="utf-8",
    )
    print(f"generated {screen_count} screens into {OUTPUT_C}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
