# C to l7801 Converter

This repository includes a starter converter at [tools/c_to_l7801.py](tools/c_to_l7801.py) that translates a restricted subset of C into l7801/l65 source (.l7801) intended for the l65 toolchain.

## Environment setup (recommended on macOS/Homebrew)

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install pycparser Pillow
```

## Run

```bash
./.venv/bin/python tools/c_to_l7801.py examples/sample_input.c -o examples/sample_output.l7801
```

## Run with syntax validation using l7801

```bash
./.venv/bin/python tools/c_to_l7801.py \
  examples/sample_input.c \
  -o examples/sample_output.l7801 \
  --validate-cmd /Users/jblanchard/Documents/Code/Retro/l65/bin/l7801
```

## Supported C subset

- Global scalar integer declarations, optionally with integer literal initializers
- Global `const` / `static const` scalars and arrays (emitted in ROM)
- `enum` declarations and enum constant use in expressions
- `struct` declarations, instances, and nested `.` field access
- Function definitions
- Local integer declarations
- Assignment with `=`
- `return`, `if/else`, `while`
- Arithmetic/logic binary ops: `+ - & | ^`
- Comparisons: `== != < > <= >=`
- Unary ops: `+ - !`
- Direct function calls
- Array reads from ROM const arrays (`arr[i]` and `*(arr + i)` subset)

## Calling convention used by converter

- Caller-evaluated arguments are written to per-callee RAM slots named `fn__arg_<param>` in declaration order.
- Callee reads parameter values directly from those same RAM slots.
- Return value is in register `a`.
- Calls with known function signatures are arity-checked during conversion.

## Important limitations

- No `switch`, `for`, or `do-while` yet
- No `->` field access yet (use `.` on struct instances)
- No general pointer model; pointer dereference support is limited to ROM const-array read patterns
- Writable `static` storage is rejected (mutable state must live in RAM globals/locals)

## PNG sprite import

The converter supports source-level PNG asset directives for 16x16 monochrome hardware sprites.

Single sprite:

```c
#pragma scv_asset sprite hero "assets/hero.png"
```

Sprite sheet:

```c
#pragma scv_asset spritesheet enemies "assets/enemies.png" 16 16
```

Each imported frame generates a callable loader function in the output:

- `scv_asset_hero_load(pattern_slot)`
- `scv_asset_enemies_0_load(pattern_slot)`
- `scv_asset_enemies_1_load(pattern_slot)`

Use the generated loader together with the hardware sprite helpers from [tools/scv_api.h](tools/scv_api.h):

```c
scv_asset_hero_load(0);
scv_set_hw_sprite(0, 48, 48, 0, 15);
```

Dedicated hardware sprite helpers are also available:

- `scv_set_hw_sprite_pos(id, x, y)`
- `scv_set_hw_sprite_pattern(id, pattern)`
- `scv_set_hw_sprite_color(id, color)`
- `scv_set_hw_sprite_frame(id, base_pattern, frame)`
- `scv_set_hw_sprite_anim(id, x, y, base_pattern, frame, color)`
- `scv_hide_hw_sprite(id)`

Imported PNGs are converted to 32-byte SCV hardware sprite patterns and copied into pattern memory at `0x2000 + (64 + pattern_slot) * 0x20`.

Converter-enforced pattern split:

- Background tile APIs (`scv_draw_tile`, `scv_draw_bg_tile`, `scv_draw_bg_tile_scrolled`) force tile IDs into 0-63.
- Hardware sprite APIs force sprite patterns into 64-127. Pass logical sprite pattern values in 0-63.
- Sprite asset loader functions place imported sprite patterns into sprite bank slots (64 + pattern_slot).

## Quick regression run

From `examples`:

```bash
sh ./regentest.sh
```

This currently rebuilds `game_demo`, `demo_input_sound`, `demo_bg_scroll`, and `demo_bg_sprite_combo`.

For standalone conversion or inspection, use:

```bash
./.venv/bin/python tools/png_to_scv.py assets/hero.png --name hero
./.venv/bin/python tools/png_to_scv.py assets/enemies.png --name enemies --sheet 16 16
```

## PNG tile map slicing

For larger background/source maps, use the tile slicer to:

- break a PNG into fixed-size tiles
- detect and reuse identical tiles
- emit a deduplicated tilesheet PNG
- emit a map file containing tile indices into that tilesheet

Example:

```bash
./.venv/bin/python tools/png_to_tiled_map.py assets/map.png --tile-size 8 8 --map-format both
```

Outputs:

- `<name>_tiles.png` -- unique tiles packed into a tilesheet
- `<name>_map.json` -- metadata plus indexed rows
- `<name>_map.csv` -- optional plain index grid

Useful options:

- `--name demo_map` to override the output file prefix
- `--output-dir build/maps` to redirect output files
- `--sheet-columns 16` to control the tilesheet layout
- `--max-tiles 64` to fail if the source image needs more than a target tile budget
- `--split-screen-width 32` to split into fixed, screen-boundary column chunks (for runtime streaming at screen crossings)
- `--split-max-tiles 64` to greedily split a wide map into multiple column segments, each with its own deduped tilesheet and indexed map under the tile limit

When `--split-max-tiles` is used, the tool also emits `<name>_manifest.json` describing each segment's source column range and output files.

`--split-screen-width` can be paired with `--max-tiles` to validate each screen chunk against a tile budget.
