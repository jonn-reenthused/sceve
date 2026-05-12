#include "../tools/scv_api.h"

#pragma scv_asset backgroundsheet bgtiles "assets/arrows.png" 16 16

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

const char title_bg_png[] = "BG PNG TILES";

int main(void) {
    int row;
    int col;
    int id;
    int tile;
    int x;
    int y;

    /* Match known-good SCV VDC setup for first-bank background sprites. */
    scv_set_vdc_regs(0xD0, 0x00, 0x00, 0xF8);

    /*
     * backgroundsheet loaders target pattern slots 0..63 (first hardware
     * sprite bank). Draw them with scv_set_hw_sprite_raw so pattern values
     * are not forced into 64..127.
     * 
     * NOTE: Text printing (scv_print_string) interferes with hardware sprite
     * rendering in character mode. Omit text when using background sprites.
     */
    scv_asset_bgtiles_0_load(0);
    scv_asset_bgtiles_1_load(1);
    scv_asset_bgtiles_2_load(2);
    scv_asset_bgtiles_3_load(3);

    // scv_print_string(0, 0, title_bg_png);

    id = 0;
    row = 0;
    while (row < 6) {
        col = 0;
        while (col < 10) {
            tile = (row + col) & 0x03;
            x = 20 + (col * 16);
            y = 28 + (row * 16);
            scv_set_hw_sprite_raw(id, x, y, tile, 15);
            id = id + 1;
            col = col + 1;
        }
        row = row + 1;
    }

    while (id < 64) {
        scv_hide_hw_sprite(id);
        id = id + 1;
    }

    while (1) {
        scv_wait_vblank();
    }

    return 0;
}
