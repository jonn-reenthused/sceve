#include "../tools/scv_api.h"

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

const char title_bg_scrl[] = "BG SCRL";

int main(void) {
    int x;
    int y;
    int frame;
    int tx;
    int ty;

    x = 0;
    y = 0;
    frame = 0;

    scv_print_string(0, 0, title_bg_scrl);

    /* Seed background with tile IDs beyond 63 to show forced 0..63 mapping. */
    ty = 0;
    while (ty < 12) {
        tx = 0;
        while (tx < 32) {
            scv_draw_bg_tile(ty, tx, 64 + ((tx + ty) & 0x3F));
            tx = tx + 1;
        }
        ty = ty + 1;
    }

    while (1) {
        scv_wait_vblank();

        frame = frame + 1;
        if ((frame & 0x03) == 0) {
            x = x + 1;
        }
        if ((frame & 0x07) == 0) {
            y = y + 1;
        }

        scv_set_bg_scroll(x, y);

        /* Moving marker via scrolled draw helper. */
        scv_draw_bg_tile_scrolled(5, 15, 127);
        scv_draw_bg_tile_scrolled(6, 15, 95);
    }
}
