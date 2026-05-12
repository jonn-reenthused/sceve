#include "../tools/scv_api.h"

/*
 * Near full-screen background-sprite demo for:
 *   scv_load_bg_pattern_array(pattern_slot, src_array, pattern_count)
 *
 * Two 16x16 patterns are copied into background-sprite slots 0 and 1,
 * then rendered via raw hardware sprites in an 11x11 grid (121 sprites)
 * using 128-sprite mode for near full-screen coverage.
 */
const unsigned char demo_bg_patterns[64] = {
    /* Pattern 0: fully empty tile. */
    0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
    0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
    0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
    0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,

    /* Pattern 1: fully filled tile. */
    0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,
    0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,
    0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,
    0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF
};

int main(void)
{
    int row;
    int col;
    int tile;
    int id;
    int x;
    int y;

    scv_set_vdc_regs(0xD0, 0x00, 0x00, 0xF8);
    scv_set_hw_sprite_mode(0);  /* 128-sprite mode */

    /* Load two patterns into background-sprite slots 0 and 1. */
    scv_load_bg_pattern_array(0, demo_bg_patterns, 2);

    /* Dense background-sprite fill (11x11 = 121 sprites). */
    id = 0;
    row = 0;
    while (row < 11) {
        col = 0;
        while (col < 11) {
            tile = (row + col) & 1;
            x = 20 + (col * 16);
            y = 8 + (row * 16);
            scv_set_hw_sprite_raw(id, x, y, tile, 15);
            id = id + 1;
            col = col + 1;
        }
        row = row + 1;
    }

    while (1) {
        scv_wait_vblank();
    }

    return 0;
}
