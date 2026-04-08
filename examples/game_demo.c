#include "../tools/scv_api.h"

#pragma scv_asset sprite player "assets/face.png"
#pragma scv_asset spritesheet enemy "assets/arrows.png" 16 16
#pragma scv_asset sound tone snd_tone 2 0x80 0xFF 0x7F

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

int main(void) {
    int s1_x;
    int s1_y;
    int enemy_frame;
    int enemy_tick;
    int y_dbg;
    char any_btn = 0;
    char last_any_btn = 0;
    char p2_btn = 0;
    char p1_btn = 0;
	char up = 0;
	char down = 0;
	char left = 0;
	char right = 0;

    s1_x = 112;
    s1_y = 80;
    enemy_frame = 0;
    enemy_tick = 0;

    scv_print_string(11, 0, "SCV SDK");
    scv_print_string(12, 0, "TONSOMO");

    scv_print_char(0, 4, 'Y');
    scv_print_char(0, 5, ':');
    scv_print_char(0, 15, 'U');
    scv_print_char(0, 16, ':');
    scv_print_char(0, 18, 'D');
    scv_print_char(0, 19, ':');

    scv_print_char(5, 3, '@');
    scv_print_char(1, 3, 'D');
    scv_print_char(1, 4, 'R');
    scv_print_char(1, 5, 'L');
    scv_print_char(1, 6, 'U');
    scv_print_char(1, 7, 'B');
    scv_print_char(1, 8, '2');
    scv_print_char(1, 9, 'B');
    scv_print_char(1, 10, '2');

    scv_asset_player_load(0);
    scv_asset_enemy_0_load(1);
    scv_asset_enemy_1_load(2);
    scv_asset_enemy_2_load(3);
    scv_asset_enemy_3_load(4);

    scv_set_hw_sprite(0, 64, 80, 0, 15);
    scv_set_hw_sprite_anim(1, s1_x, s1_y, 1, enemy_frame, 12);

    while (1) {
        scv_wait_vblank();
        scv_read_pad1();
        scv_read_pad2();

        enemy_tick = enemy_tick + 1;
        if (enemy_tick == 20) {
            enemy_tick = 0;
            enemy_frame = enemy_frame + 1;
            if (enemy_frame == 4) {
                enemy_frame = 0;
            }
            scv_set_hw_sprite_frame(1, 1, enemy_frame);
        }

        /* 0xFE scan group: left/up/button ; 0xFD scan group: right/down */
        if ((scv_pad1_state & 0x01) == 0) {
            scv_print_char(2, 3, 'D');
			down = 1;
        } else {
            scv_print_char(2, 3, '.');
			down = 0;
        }
        if ((scv_pad1_state & 0x02) == 0) {
            scv_print_char(2, 4, 'R');
			right = 1;
        } else {
            scv_print_char(2, 4, '.');
			right = 0;
        }
        if ((scv_pad2_state & 0x01) == 0) {
            scv_print_char(2, 5, 'L');
			left = 1;
        } else {
            scv_print_char(2, 5, '.');
			left = 0;
        }
        if ((scv_pad2_state & 0x02) == 0) {
            scv_print_char(2, 6, 'U');
			up = 1;
        } else {
            scv_print_char(2, 6, '.');
			up = 0;
        }
        if ((scv_pad2_state & 0x04) == 0) {
            scv_print_char(2, 7, 'B');
            p2_btn = 1;
        } else {
            scv_print_char(2, 7, '.');
            p2_btn = 0;
        }
        if ((scv_pad1_state & 0x04) == 0) {
            scv_print_char(2, 9, 'B');
            p1_btn = 1;
        } else {
            scv_print_char(2, 9, '.');
            p1_btn = 0;
        }

        if (p2_btn == 1) {
            any_btn = 1;
        } else {
            if (p1_btn == 1) {
                any_btn = 1;
            } else {
                any_btn = 0;
            }
        }

        if (any_btn == 1) {
            if (last_any_btn == 0) {
                scv_asset_snd_tone_play();
            }
        } else {
            if (last_any_btn == 1) {
                scv_stop_sound();
            }
        }
        last_any_btn = any_btn;

        if (left == 1) {
            scv_move_hw_sprite_left(0, 2, 8);
        }
        if (right == 1) {
            scv_move_hw_sprite_right(0, 2, 204);
        }

        if (up == 1) {
            scv_move_hw_sprite_up(0, 2, 16);
        }
		if (down == 1) {
			scv_move_hw_sprite_down(0, 2, 204);
		}

        y_dbg = scv_get_hw_sprite_y(0);
        if ((y_dbg & 0x80) == 0) {
            scv_print_char(0, 6, '0');
        } else {
            scv_print_char(0, 6, '1');
        }
        if ((y_dbg & 0x40) == 0) {
            scv_print_char(0, 7, '0');
        } else {
            scv_print_char(0, 7, '1');
        }
        if ((y_dbg & 0x20) == 0) {
            scv_print_char(0, 8, '0');
        } else {
            scv_print_char(0, 8, '1');
        }
        if ((y_dbg & 0x10) == 0) {
            scv_print_char(0, 9, '0');
        } else {
            scv_print_char(0, 9, '1');
        }
        if ((y_dbg & 0x08) == 0) {
            scv_print_char(0, 10, '0');
        } else {
            scv_print_char(0, 10, '1');
        }
        if ((y_dbg & 0x04) == 0) {
            scv_print_char(0, 11, '0');
        } else {
            scv_print_char(0, 11, '1');
        }
        if ((y_dbg & 0x02) == 0) {
            scv_print_char(0, 12, '0');
        } else {
            scv_print_char(0, 12, '1');
        }
        if ((y_dbg & 0x01) == 0) {
            scv_print_char(0, 13, '0');
        } else {
            scv_print_char(0, 13, '1');
        }

        if (up == 1) {
            scv_print_char(0, 17, '1');
        } else {
            scv_print_char(0, 17, '0');
        }
        if (down == 1) {
            scv_print_char(0, 20, '1');
        } else {
            scv_print_char(0, 20, '0');
        }
    }
}
