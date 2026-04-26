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

By default, `--ram-base` is `auto`:

- If the source uses `scv_set_sprite`, `scv_move_sprite`, or `scv_hide_sprite`, the converter keeps `0xFF80-0xFF9F` reserved for the software-sprite shadow table and allocates user RAM from `0xFFA0`.
- Otherwise it reclaims that 32-byte region automatically and allocates from `0xFF80`.

You can still force a specific base with `--ram-base 0xFFA0` or `--ram-base 0xFF80`.

## Run with syntax validation using l7801

```bash
./.venv/bin/python tools/c_to_l7801.py \
  examples/sample_input.c \
  -o examples/sample_output.l7801 \
  --validate-cmd /Users/jblanchard/Documents/Code/Retro/l65/bin/l7801
```

## Run with in-repo assembler validation (and byte-compare)

```bash
./.venv/bin/python tools/c_to_l7801.py \
  examples/sample_input.c \
  -o examples/sample_output.l7801 \
  --validate-backend asm7801 \
  --validate-compare-bin examples/sample_output.bin
```

Notes:

- `--validate-backend asm7801` assembles the generated `.l7801` via `tools/asm7801.py`.
- If `--validate-compare-bin` is omitted, the converter auto-uses `<output>.bin` when that file exists.
- `--validate-backend l7801` keeps the existing dump-based external validation flow.

## Cartridge metadata pragmas

The converter now accepts a first banking-oriented metadata layer. This does not
emit bank-switched code yet, but it lets you annotate intended cartridge layout
and bank placement so the converter can validate it and emit a JSON sidecar.

Supported pragmas:

```c
#pragma scv_cart_profile banked64
#pragma scv_bank 1
void load_level_assets(void) { ... }

#pragma scv_bank_data(1) level2_map
const unsigned char level2_map[] = { ... };
```

Supported profiles:

- `flat32`
- `flat32_ram4k`
- `flat32_ram4k_battery`
- `banked64`
- `banked128`
- `split32_8`
- `split32_32`

Behavior:

- `#pragma scv_cart_profile ...` selects the cartridge profile for validation.
- `#pragma scv_bank N` assigns bank `N` to the next function definition.
- `#pragma scv_bank_data(N) name` assigns bank `N` to the named ROM array.
- When any banking metadata is present, the converter writes `<output>.cart.json`
  by default, or the path given by `--cart-metadata-output`.
- `--emit-cart-package` assembles the generated `.l7801` with `tools/asm7801.py`
  and writes a package directory containing `bank0_runtime.bin`, any packed
  auxiliary `bankN_payload.bin` files, and `manifest.json`.
- For cart profiles that map cleanly to MAME's built-in SCV boards, package
  emission also writes a runnable softlist bundle under `<package>/mame/`.
  Cart-RAM examples must be launched through that softlist path because MAME
  does not expose SCV cartridge RAM for loose `.bin` images.
- `--cart-package-dir` overrides the default package directory path.

Current limitation:

- The emitted `.l7801` is still flat-ROM code. The sidecar is planning metadata
  for later bank-aware codegen and packaging, not a mapper implementation.
- Package emission currently materializes explicit non-zero-bank ROM arrays only.
  Functions assigned to non-zero banks are reported in the manifest as
  unpackaged until bank-aware code placement and trampolines exist.
- Package emission now enforces "bank 0 only" executable code. If a non-zero-bank
  function participates in the user-function call graph, package emission fails
  rather than emitting a misleading package.
- MAME's SCV driver only enables cartridge RAM via softlist entries, and only
  for the built-in `rom32k_ram` and `rom128k_ram` PCB types. A loose
  `mame scv -cart demo.bin` load will never expose cartridge RAM, even when the
  generated `.cart.json` sidecar contains correct RAM metadata.

Working launch pattern for the packaged examples:

```bash
./.venv/bin/python tools/c_to_l7801.py \
  examples/demo_cart_ram.c \
  -o examples/demo_cart_ram.l7801 \
  --emit-cart-package \
  --cart-package-dir examples/demo_cart_ram

mame \
  -hashpath 'examples/demo_cart_ram/mame/hash;hash' \
  -rompath 'examples/demo_cart_ram/mame;/Users/jblanchard/Library/Application Support/mame/roms' \
  scv -cart demo_cart_ram
```

On macOS, MAME path lists use `;` separators, not `:`.

Current emitted-call behavior:

- Functions annotated with `#pragma scv_bank N` now emit a wrapper at `fn_<name>`
  plus a separate body label.
- The wrapper calls the compiler-recognized hooks
  `scv_cart_select_bank(N)` and `scv_cart_restore_bank()` around the body call.
- The metadata sidecar now distinguishes:
  - `trampolines`: generated wrapper/body pairs for banked functions
  - `trampoline_call_edges`: bank-0 to bank-N calls that are conceptually
    routed via a wrapper
  - `illegal_banked_call_edges`: calls originating from non-zero-bank code,
    which are not yet placeable by the current packager
- Cart hook emission is now profile-tagged. For example, `banked64` uses the
  `banked64-shadow-v1` backend, which masks the selected bank into range and
  records it in profile-specific shadow state. This is an explicit development
  backend for the future mapper ABI, not a verified hardware port write yet.

Cartridge RAM support:

- `flat32_ram4k` models a fixed 4K cartridge RAM window at `0xE000-0xEFFF`
  for gameplay working RAM.
- `flat32_ram4k_battery` models the same 4K window but tags the metadata as
  battery-backed save RAM.
- Current cartridge RAM helpers are:
  - `scv_cart_ram_clear()`
  - `scv_cart_ram_read(offset_hi, offset_lo)`
  - `scv_cart_ram_write(offset_hi, offset_lo, value)`
  - `scv_cart_ram_read16_lo(offset_hi, offset_lo)`
  - `scv_cart_ram_read16_hi(offset_hi, offset_lo)`
  - `scv_cart_ram_write16(offset_hi, offset_lo, value_lo, value_hi)`
  - `scv_cart_ram_fill(offset_hi, offset_lo, byte_count, value)`
  - `scv_cart_ram_copy_to(offset_hi, offset_lo, src_array, byte_count)`
  - `scv_cart_ram_copy_from(offset_hi, offset_lo, dst_array, byte_count)`
- These APIs address the configured cart RAM window by offset from its base,
  not by absolute CPU address. For example `(0x00, 0x20)` means `base+0x0020`.
- `read16`/`write16` use little-endian layout: low byte first, then high byte.
- `copy_to` accepts ROM or RAM source arrays. `copy_from` requires a RAM
  destination array.
- For small persistent records, the current practical pattern is to copy fixed-
  size byte arrays to/from cart RAM. Arbitrary struct-instance copy is not yet
  exposed as a dedicated API because the converter does not guarantee every
  struct instance is stored as one contiguous RAM block.
- `byte_count` is 8-bit, so use `scv_cart_ram_clear()` when you need to erase
  the full 4K window.

Cart RAM data pragma:

- You can bind a named global declaration directly to cart RAM with:

```c
#pragma scv_cart_profile flat32_ram4k_battery
#pragma scv_cart_ram_data(0x00, 0x20) save_bytes
unsigned char save_bytes[16];

#pragma scv_cart_ram_data(0x00, 0x40) save_flag
unsigned char save_flag;
```

- The pragma offset is relative to the configured cart-RAM window base.
- v1 is intentionally narrow: it supports only global non-const byte scalars
  and 1D byte arrays.
- It does not support locals, extern declarations, const data, structs, or
  multi-dimensional arrays.
- Accesses are lowered through `scv_cart_ram_read()` / `scv_cart_ram_write()`;
  these declarations do not get normal internal-RAM addresses.

## Supported C subset

- Global scalar integer declarations, optionally with integer literal initializers
- Global `const` / `static const` scalars and arrays (emitted in ROM)
- `enum` declarations and enum constant use in expressions
- `struct` declarations, instances, and nested `.` field access
- Function definitions
- Local integer declarations
- Assignment with `=`
- `return`, `if/else`, `while`, `break`
- Arithmetic/logic binary ops: `+ - * / % & | ^ << >> && ||`
- Comparisons: `== != < > <= >=`
- Unary ops: `+ - !`
- Direct function calls
- Array reads from ROM const arrays (`arr[i]` and `*(arr + i)` subset)

## Calling convention used by converter

- Caller-evaluated arguments are written to RAM slots named `fn__arg_<param>` in declaration order.
- Callee reads parameter values directly from those same RAM slots.
- Function-scoped RAM (user-defined params, locals, local arrays/struct fields, arithmetic temps) is placed in statically overlaid frames so unrelated functions can reuse the same bytes.
- Return value is in register `a`.
- Calls with known function signatures are arity-checked during conversion.

## Important limitations

- No `switch`, `for`, or `do-while` yet
- Recursive user-defined call cycles are not supported by the current static frame allocator
- No `->` field access yet (use `.` on struct instances)
- No general pointer model; pointer dereference support is limited to ROM const-array read patterns
- Writable `static` storage is rejected (mutable state must live in RAM globals/locals)
- `/`, `%`, `/=`, and `%=` are lowered with 8-bit unsigned repeated-subtraction semantics

## PNG sprite import

The converter supports source-level PNG asset directives for 16x16 monochrome hardware sprites and 16x16 background-sprite patterns.

Single sprite:

```c
#pragma scv_asset sprite hero "assets/hero.png"
```

Sprite sheet:

```c
#pragma scv_asset spritesheet enemies "assets/enemies.png" 16 16
```

Background-sprite bank (pattern slots 0-63, rendered with `scv_set_hw_sprite_raw(...)`):

```c
#pragma scv_asset background bgtile "assets/bgtile.png"
#pragma scv_asset backgroundsheet bgtiles "assets/bgtiles.png" 16 16
```

Each imported frame generates a callable loader function in the output:

- `scv_asset_hero_load(pattern_slot)`
- `scv_asset_enemies_0_load(pattern_slot)`
- `scv_asset_enemies_1_load(pattern_slot)`

For background/backgroundsheet assets, the same generated loader naming is used,
but loaders target background-sprite pattern bank `0..63`. Display those patterns
with `scv_set_hw_sprite_raw(...)`, not with `scv_draw_tile(...)` or `scv_draw_bg_tile(...)`.

There is also probe-only 8x16 support used by the regression examples around the
text/tile plane. Keep that as a diagnostics path, not as a production background API.

For pre-packed 16x16 background-sprite pattern bytes stored in a C array, use:

- `scv_load_bg_pattern_array(pattern_slot, src_array, pattern_count)`

This copies `pattern_count * 32` bytes from `src_array` into VRAM at
`0x2000 + pattern_slot * 32`, starting at `pattern_slot` (0-63).

`scv_load_bg_sprite_array(...)` remains supported as an older alias.

For raw/probe-oriented 8x16 uploads into the old character-pattern address range, use:

- `scv_load_bg_array(pattern_slot, src_array, pattern_count)`

This copies `pattern_count * 16` bytes from `src_array` into VRAM at
`0x2000 + pattern_slot * 16`, starting at `pattern_slot` (0-63).

Current status: MAME's SCV video implementation shows that text mode renders
from a fixed `charrom` and that the non-text alternatives are semigraphics or
block graphics. That matches the latest regressions: `scv_draw_tile(...)` /
`scv_draw_bg_tile(...)` always show the built-in glyph set, even after direct
VRAM probes against `0x2200` and `0x2A00`. In other words, `scv_load_bg_array`
uploads bytes to VRAM, but the text/background tile APIs do not currently use
that VRAM as a custom character generator path.

For direct experiments against candidate VRAM regions, use:

- `scv_vram_copy(addr_hi, addr_lo, src_array, byte_count)`

This copies raw bytes to an arbitrary VRAM address and is intended as a debug
helper for source-bank probes rather than as a general gameplay API.

Working background-sprite example:

```c
scv_asset_bgtiles_0_load(0);
scv_asset_bgtiles_1_load(1);
scv_set_hw_sprite_raw(0, 28, 30, 0, 15);
scv_set_hw_sprite_raw(1, 44, 30, 1, 15);
```

Raw array example:

```c
scv_load_bg_pattern_array(0, bg_patterns, bg_pattern_count);
```

Probe example:

```c
const unsigned char bg_patterns[32] = {
  /* 2 patterns * 16 bytes */
};

scv_load_bg_array(0, bg_patterns, 2);
```

Do not treat `scv_load_bg_array(...)` as a visible custom tile loader for
`scv_draw_bg_tile(...)`:

```c
scv_load_bg_array(0, bg_patterns, 2);
scv_draw_bg_tile(0, 0, 0);
scv_draw_bg_tile(0, 1, 1);
```

See [examples/demo_bg_array_loader.c](../examples/demo_bg_array_loader.c), [examples/demo_bg_png_tiles.c](../examples/demo_bg_png_tiles.c), and [examples/demo_crabscv_migration.c](../examples/demo_crabscv_migration.c) for the supported 16x16 background-sprite path.
See [examples/demo_bg_tile_array_loader.c](../examples/demo_bg_tile_array_loader.c), [examples/demo_bg_tile_png_loader.c](../examples/demo_bg_tile_png_loader.c), and [examples/demo_bg_vram_probe.c](../examples/demo_bg_vram_probe.c) for the regression probes that established the text/tile limitation.

For sprite assets, use the generated loader together with the hardware sprite helpers from [tools/scv_api.h](tools/scv_api.h):

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

For BIOS helper wrapper usage examples (clear VRAM/sprites + 16-bit helper calls), see [examples/demo_bios_wrappers.c](../examples/demo_bios_wrappers.c).

## Reusable music sequencing helper

For frame-based melody sequencing, include the shared helper source:

```c
#include "../tools/scv_music_seq.c"
```

The converter currently inlines user `#include` files when they end in `.c`.
See [examples/demo_music_sequencer.c](../examples/demo_music_sequencer.c) for a complete melody + beat-track usage example.

Imported regular sprite PNGs are converted to 32-byte SCV hardware sprite patterns and copied into pattern memory at `0x2000 + (64 + pattern_slot) * 0x20`.
Imported background/backgroundsheet PNGs use the same 32-byte 16x16 packing but target bank `0..63` for `scv_set_hw_sprite_raw(...)`.

Converter-enforced pattern split:

- Background tile APIs (`scv_draw_tile`, `scv_draw_bg_tile`, `scv_draw_bg_tile_scrolled`) force tile IDs into 0-63 and write the tilemap for the built-in fixed glyph set.
- Hardware sprite APIs force sprite patterns into 64-127. Pass logical sprite pattern values in 0-63.
- Background asset loader functions place imported 16x16 patterns into bank `0..63` for `scv_set_hw_sprite_raw(...)`.
- Sprite asset loader functions place imported sprite patterns into sprite bank slots `(64 + pattern_slot)`.

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
- `<name>_map.c` -- optional C `const int` layout array (with `--emit-c-layout`)

Useful options:

- `--name demo_map` to override the output file prefix
- `--output-dir build/maps` to redirect output files
- `--sheet-columns 16` to control the tilesheet layout
- `--max-tiles 64` to fail if the source image needs more than a target tile budget
- `--emit-c-layout` to emit a C layout source file for direct runtime use
- `--c-symbol crab_bg_layout` to control generated C symbol names
- `--split-screen-width 32` to split into fixed, screen-boundary column chunks (for runtime streaming at screen crossings)
- `--split-max-tiles 64` to greedily split a wide map into multiple column segments, each with its own deduped tilesheet and indexed map under the tile limit

When `--split-max-tiles` is used, the tool also emits `<name>_manifest.json` describing each segment's source column range and output files.

`--split-screen-width` can be paired with `--max-tiles` to validate each screen chunk against a tile budget.

One-command CrabSCV-style migration (full background PNG -> tilesheet + C layout):

```bash
python3 tools/png_to_tiled_map.py \
  /Users/jblanchard/Documents/Code/Retro/Epoch/SCV/CrabSCV/Graphics/Source/Background.png \
  --tile-size 16 16 \
  --name crab_bg \
  --output-dir examples/assets \
  --sheet-columns 8 \
  --map-format both \
  --emit-c-layout \
  --c-symbol crab_bg_layout
```

This emits:
- `examples/assets/crab_bg_tiles.png`
- `examples/assets/crab_bg_map.json`
- `examples/assets/crab_bg_map.csv`
- `examples/assets/crab_bg_map.c`

Use the generated map C file directly in a demo:

```c
#include "../tools/scv_api.h"
#pragma scv_asset backgroundsheet crab_bg_tiles "assets/crab_bg_tiles.png" 16 16
#include "assets/crab_bg_map.c"

/* ... load tile patterns ... */
tile = crab_bg_layout_map[(map_y * crab_bg_layout_map_width) + map_x];
scv_set_hw_sprite_raw(id, x, y, tile, 15);
```

Exact CrabSCV parity workflow (sparse `.scn` + byte-exact `.spr`):

```bash
python3 - <<'PY'
from pathlib import Path
from PIL import Image

spr_path = Path('/Users/jblanchard/Documents/Code/Retro/Epoch/SCV/CrabSCV/Graphics/Background.spr')
scn_path = Path('/Users/jblanchard/Documents/Code/Retro/Epoch/SCV/CrabSCV/Graphics/Background.scn')
out_png = Path('examples/assets/crab_bg_spr_tiles.png')
out_c = Path('examples/assets/crab_bg_scn_data.c')

spr = spr_path.read_bytes()
frames = len(spr) // 32
cols = 8
rows = (frames + cols - 1) // cols
sheet = Image.new('RGBA', (cols * 16, rows * 16), (0, 0, 0, 0))

for fi in range(frames):
  frame = spr[fi*32:(fi+1)*32]
  tile = Image.new('RGBA', (16, 16), (0, 0, 0, 0))
  px = tile.load()
  bi = 0
  for y in range(0, 16, 2):
    for block in range(4):
      b = frame[bi]
      bi += 1
      for i in range(4):
        x = block * 4 + i
        if (b >> (7 - i)) & 1:
          px[x, y] = (0, 0, 0, 255)
        if (b >> (3 - i)) & 1:
          px[x, y + 1] = (0, 0, 0, 255)
  sheet.paste(tile, ((fi % cols) * 16, (fi // cols) * 16))

sheet.save(out_png)
scn = scn_path.read_bytes()
out_c.write_text(
  '/* Auto-generated from CrabSCV Background.scn */\\n'
  f'const int crab_bg_scn_data[] = {{ {", ".join(str(b) for b in scn)} }};\\n'
  f'const int crab_bg_scn_entry_count = {len(scn)//4};\\n',
  encoding='utf-8'
)
print('wrote', out_png)
print('wrote', out_c)
PY
```

Then build and run the canonical parity demo:

```bash
cd examples
python3 ../tools/c_to_l7801.py demo_crab_bg_autogen.c && l7801 demo_crab_bg_autogen.l7801
/Applications/mame/mame scv -cart ./demo_crab_bg_autogen.bin
```

## Migrating from Assembly Background Sprites (CrabSCV)

The SCV hardware supports two background rendering approaches:

**Traditional Assembly Approach** (used by CrabSCV):
- Separate Windows tool: `PNGToBackground.exe`
- Generates binary sprite table (.scn) and pattern data (.spr)
- Pre-computed, fixed layout attached to binary

**Modern C Approach** (new pragma system):
- Inline PNG import via `#pragma scv_asset backgroundsheet`
- Automatic cross-platform loader generation
- Fully programmable tile rendering at runtime

See [examples/demo_crabscv_migration.c](../examples/demo_crabscv_migration.c) and
[examples/MIGRATION_GUIDE.md](../examples/MIGRATION_GUIDE.md) for a complete comparison and migration guide.
