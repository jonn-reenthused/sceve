#include "../tools/scv_api.h"

/*
 * LEGACY EXPLORATORY DEMO.
 *
 * This file demonstrates conceptual migration from CrabSCV to pragma-driven
 * tile rendering, but it is not the canonical parity path.
 * Use demo_crab_bg_autogen.c for exact visual parity.
 *
 * CrabSCV Background Sprite Migration Example
 * 
 * This demo shows how to convert a CrabSCV assembly background setup
 * to the new C backgroundsheet pragma system.
 * 
 * CrabSCV (assembly approach):
 *   1. Create full-screen PNG: Graphics/Source/Background.png
 *   2. Convert: PNGToBackground.exe → Background.scn + Background.spr
 *   3. Include as binary: binclude ../Graphics/Background.scn
 *   4. At startup, block transfer to VRAM:
 *      - BackgroundScreen → BGSpriteTable (0x3200)
 *      - BackgroundSprites → BGSpriteVRAM (0x2000)
 *   5. Hardware displays fixed background layout
 *   
 * NEW: C backgroundsheet approach:
 *   1. Create tile sheet PNG: assets/background.png (16x16 tiles)
 *   2. Use pragma: #pragma scv_asset backgroundsheet bg_tiles "assets/background.png" 16 16
 *   3. Compiler auto-generates: scv_asset_bg_tiles_0_load(), etc.
 *   4. Call loaders to populate pattern slots 0-63
 *   5. Use scv_set_hw_sprite_raw() to render tiles (fully programmable)
 * 
 * Advantages of the C approach:
 *   - Cross-platform (no Windows .exe dependency)
 *   - Integrated with C compiler, no external build step
 *   - Fully dynamic (change/animate tiles at runtime)
 *   - Can mix background (slots 0-63) with game sprites (64-127)
 */

#pragma scv_asset backgroundsheet bg_tiles "assets/arrows.png" 16 16

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

int main(void) {
    int row;
    int col;
    int id;
    int tile;
    int x;
    int y;

    /* Initialize VDC for background sprite mode (pattern bank 0-63) */
    scv_set_vdc_regs(0xD0, 0x00, 0x00, 0xF8);

    /*
     * Load all tile patterns into VRAM pattern slots.
     * This replaces CrabSCV's block transfer of BackgroundSprites.
     */
    scv_asset_bg_tiles_0_load(0);
    scv_asset_bg_tiles_1_load(1);
    scv_asset_bg_tiles_2_load(2);
    scv_asset_bg_tiles_3_load(3);

    /*
     * Render the background in a 6x10 grid.
     * This replaces CrabSCV's block transfer of BackgroundScreen.
     * But now we compute it dynamically in C, giving full flexibility.
     */
    id = 0;
    row = 0;
    while (row < 6) {
        col = 0;
        while (col < 10) {
            /* Pattern IDs cycle 0-3 */
            tile = (row + col) & 0x03;
            
            x = 20 + (col * 16);
            y = 28 + (row * 16);
            
            scv_set_hw_sprite_raw(id, x, y, tile, 15);
            
            id = id + 1;
            col = col + 1;
        }
        row = row + 1;
    }

    /* Hide remaining sprite slots (60-63) */
    while (id < 64) {
        scv_hide_hw_sprite(id);
        id = id + 1;
    }

    while (1) scv_wait_vblank();
    return 0;
}

/*
 * MIGRATION NOTES FOR CRABSCV
 * ============================================================================
 * 
 * CrabSCV ASSEMBLY APPROACH:
 * 
 *   File: Graphics/Source/Background.png
 *   Tool: PNGToBackground.exe Background.png Background
 *   Output: Background.scn (sprite table) + Background.spr (patterns)
 *   Assembly: binclude ../Graphics/Background.scn
 *   Runtime: block transfer to 0x3200 and 0x2000
 *   Result: Fixed, pre-computed background layout
 *
 * ============================================================================
 * 
 * NEW C APPROACH:
 * 
 *   1. Extract 16×16 tiles from CrabSCV Background.png
 *      → Save as assets/background_tileset.png (e.g., 8 cols × 6 rows)
 *   
 *   2. Add pragma to C code:
 *      #pragma scv_asset backgroundsheet bg_tiles \
 *          "assets/background_tileset.png" 16 16
 *   
 *   3. Compiler auto-generates loader functions:
 *      scv_asset_bg_tiles_0_load(slot)  // Frame 0 → pattern slot
 *      scv_asset_bg_tiles_1_load(slot)
 *      ... (one per PNG frame)
 *   
 *   4. In C code, call loaders to populate patterns:
 *      for (int i = 0; i < num_frames; i++) {
 *          scv_asset_bg_tiles_N_load(i);
 *      }
 *   
 *   5. Define tile layout in C (can be dynamic!):
 *      for (int row = 0; row < height; row++) {
 *          for (int col = 0; col < width; col++) {
 *              int pattern_id = get_layout(row, col);
 *              scv_set_hw_sprite_raw(sprite_id, x, y, pattern_id, 15);
 *          }
 *      }
 *
 * ============================================================================
 * ARCHITECTURE REFERENCE
 * ============================================================================
 * 
 * VRAM Layout:
 *   0x2000-0x27FF: Pattern memory (patterns 0-127)
 *     0x2000-0x20FF: Patterns 0-63 (background sprites)
 *     0x2100-0x21FF: Patterns 64-127 (game sprites)
 *   
 *   0x3200-0x32FF: Sprite attribute table (64 sprites)
 *     Each sprite: [Y, Color, X, Pattern]
 *
 * VDC Port (0x3400):
 *   Sequential 4-byte writes configure mode:
 *   scv_set_vdc_regs(0xD0, 0x00, 0x00, 0xF8)
 *     ↓
 *   [0xD0 @ 0x3400] [0x00 @ 0x3401] [0x00 @ 0x3402] [0xF8 @ 0x3403]
 *     Enables background sprite mode and pattern bank 0-63 access
 *
 * Pattern Data Format:
 *   16×16 monochrome (1 bit per pixel)
 *   32 bytes per pattern (16 rows × 2 bytes per row)
 *   Packed 2×4 pixels per byte (4-bit words)
 *
 * ============================================================================
 * 
 * COMPARISON TABLE
 * ============================================================================
 * 
 * | Aspect              | CrabSCV Assembly      | New C System         |
 * |---------------------|-----------------------|----------------------|
 * | Source              | Full-screen PNG       | Tile sheet PNG       |
 * | Conversion          | PNGToBackground.exe   | C pragma             |
 * | Generator output    | .scn + .spr binary    | C loader functions   |
 * | Pattern storage     | Block transfer        | Loader calls         |
 * | Layout definition   | PNG → tool → .scn     | C code array/loop    |
 * | Sprite rendering    | Hardware (fixed)      | C loop (dynamic)     |
 * | Platform            | Windows-dependent     | Cross-platform       |
 * | Flexibility         | Fixed layout          | Full C programmability |
 * | Pattern reuse       | Multiple refs OK      | Multiple refs OK     |
 * | VDC mode            | Implicit              | Explicit (C function)|
 *
 * ============================================================================
 */
