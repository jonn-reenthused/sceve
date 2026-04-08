#include "../tools/scv_api.h"

#pragma scv_asset sprite pilot "assets/face.png"

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

const char title_combo[] = "COMBO";

int main(void) {
    int sx;
    int sy;
    int frame;
    int tx;
    int ty;
    int scroll_x;
    int scroll_y;

    sx = 96;
    sy = 88;
    frame = 0;
    scroll_x = 0;
    scroll_y = 0;

    scv_print_string(0, 0, title_combo);

    ty = 0;
    while (ty < 12) {
        tx = 0;
        while (tx < 32) {
            /* Intentionally pass >63 values; draw API constrains to bg bank 0..63. */
            scv_draw_bg_tile(ty, tx, tx + 96);
            tx = tx + 1;
        }
        ty = ty + 1;
    }

    scv_asset_pilot_load(0);
    scv_set_hw_sprite(0, sx, sy, 0, 15);

    while (1) {
        scv_wait_vblank();
        scv_read_pad1();
        scv_read_pad2();

        if ((scv_pad2_state & 0x01) == 0) {
            if (sx > 8) {
                sx = sx - 2;
            } else {
                sx = 8;
            }
        }
        if ((scv_pad1_state & 0x02) == 0) {
            if (sx < 204) {
                sx = sx + 2;
            } else {
                sx = 204;
            }
        }
        if ((scv_pad2_state & 0x02) == 0) {
            if (sy > 16) {
                sy = sy - 2;
            } else {
                sy = 16;
            }
        }
        if ((scv_pad1_state & 0x01) == 0) {
            if (sy < 204) {
                sy = sy + 2;
            } else {
                sy = 204;
            }
        }
        scv_set_hw_sprite_pos(0, sx, sy);

        frame = frame + 1;
        if ((frame & 0x03) == 0) {
            scroll_x = scroll_x + 1;
        }
        if ((frame & 0x07) == 0) {
            scroll_y = scroll_y + 1;
        }

        scv_set_bg_scroll(scroll_x, scroll_y);

        /* Redraw two rows each frame at the scrolled VRAM position so the
           scroll is visible.  64 tile writes — well within frame budget. */
        tx = 0;
        while (tx < 32) {
            /* Use tile IDs 32-63 (printable ASCII chars, loaded by BIOS) so scroll is visible. */
            scv_draw_bg_tile_scrolled(4, tx, tx + 32);
            scv_draw_bg_tile_scrolled(7, tx, tx + 33);
            tx = tx + 1;
        }
    }
}
