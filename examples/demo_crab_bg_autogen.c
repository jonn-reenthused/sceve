#include "../tools/scv_api.h"

/*
 * Canonical CrabSCV parity demo.
 *
 * This file reproduces CrabSCV background output by using:
 * - byte-exact pattern data converted from CrabSCV Background.spr
 * - byte-exact sparse sprite table converted from CrabSCV Background.scn
 * - matching VDC startup values from CrabSCV Startup.s
 *
 * Controls (P1):
 * - Left:  D-pad left
 * - Right: D-pad right
 * - B1:    Claw pose A
 * - B2:    Claw pose B
 */

#pragma scv_asset backgroundsheet crab_bg_exact_tiles "assets/crab_bg_spr_tiles.png" 16 16
#pragma scv_asset spritesheet crab_fg_tiles "assets/crab_fg_spr_tiles.png" 16 16

/* Auto-generated from CrabSCV Background.scn */
#include "assets/crab_bg_scn_data.c"

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

int main(void) {
    int id;
    int idx;
    int y;
    int color;
    int x;
    int tile;
    int player_x;
    int player_y;
    int player_body_frame;
    int player_body_overlay_frame;
    int claw_frame;
    int moving;
    int move_dir;

    /* Match CrabSCV Startup.s VDCData for correct backdrop/palette state. */
    scv_set_vdc_regs(0xF4, 0x00, 0x00, 0xF1);

    /* Load all 36 patterns preserving CrabSCV tile order */
    scv_asset_crab_bg_exact_tiles_load_all(0);

    /* Load foreground/player sprite patterns into hardware sprite bank 64..127. */
    scv_asset_crab_fg_tiles_load_all(0);

    player_x = 128;
    player_y = 208;
    player_body_frame = 0;
    player_body_overlay_frame = 1;
    claw_frame = 6;

    while (1) {
        moving = 0;
        move_dir = 0;

        scv_read_pad1();
        scv_read_pad2();

        /* P1 Left: pad2 bit0 (active-low) */
        if ((scv_pad2_state & 0x01) == 0) {
            if (player_x > 28) {
                player_x = player_x - 1;
            }
            moving = 1;
            move_dir = -1;
        }

        /* P1 Right: pad1 bit1 (active-low) */
        if ((scv_pad1_state & 0x02) == 0) {
            if (player_x < 209) {
                player_x = player_x + 1;
            }
            moving = 1;
            move_dir = 1;
        }

        /*
         * Explicit body frame pairs:
         * idle:       0 + overlay 1
         * move left:  2 + overlay 3
         * move right: 4 + overlay 5
         */
        if (moving == 0) {
            player_body_frame = 0;
            player_body_overlay_frame = 1;
        } else if (move_dir < 0) {
            player_body_frame = 2;
            player_body_overlay_frame = 3;
        } else {
            player_body_frame = 4;
            player_body_overlay_frame = 5;
        }

        /*
         * CrabSCV has a second overlaid claw/arm sprite.
         * Use P1 buttons to pick one of 3 claw poses.
         */
        claw_frame = 6;
        if ((scv_pad2_state & 0x04) == 0) {
            claw_frame = 7;
        }
        if ((scv_pad1_state & 0x04) == 0) {
            claw_frame = 6;
        }

        id = 0;
        while (id < crab_bg_scn_entry_count) {
            idx = id * 4;
            y = crab_bg_scn_data[idx];
            color = crab_bg_scn_data[idx + 1];
            x = crab_bg_scn_data[idx + 2];
            tile = crab_bg_scn_data[idx + 3];
            scv_set_hw_sprite_raw(id, x, y, tile, color);
            id = id + 1;
        }

        while (id < 61) {
            scv_hide_hw_sprite(id);
            id = id + 1;
        }

        /*
         * Reserve sprites 61/62/63 for body base + body overlay + claw.
         */
        /* Even frames (0/2/4) blue, odd overlay frames (1/3/5) red. */
        scv_set_hw_sprite(61, player_x, player_y, player_body_frame, 2);
        scv_set_hw_sprite(62, player_x, player_y, player_body_overlay_frame, 8);
        scv_set_hw_sprite(63, player_x, player_y - 4, claw_frame, 8);

        scv_wait_vblank();
    }

    return 0;
}
