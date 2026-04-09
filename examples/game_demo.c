#include "../tools/scv_api.h"

#pragma scv_asset sprite player "assets/face.png"
#pragma scv_asset spritesheet enemy "assets/arrows.png" 16 16
#pragma scv_asset sound tone snd_tone 2 0x80 0xFF 0x7F

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

void showtext(void)
{
	scv_print_string(11, 0, "SCV SDK");
	scv_print_string(12, 0, "TONSOMO");
}

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

	showtext();

    scv_print_char(4, 0, 'Y');
    scv_print_char(5, 0, ':');
    scv_print_char(15, 0, 'U');
    scv_print_char(16, 0, ':');
    scv_print_char(18, 0, 'D');
    scv_print_char(19, 0, ':');

    scv_print_char(3, 5, '@');
    scv_print_char(3, 1, 'D');
    scv_print_char(4, 1, 'R');
    scv_print_char(5, 1, 'L');
    scv_print_char(6, 1, 'U');
    scv_print_char(7, 1, 'B');
    scv_print_char(8, 1, '2');
    scv_print_char(9, 1, 'B');
    scv_print_char(10, 1, '2');

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
            scv_print_char(3, 2, 'D');
			down = 1;
        } else {
            scv_print_char(3, 2, '.');
			down = 0;
        }
        if ((scv_pad1_state & 0x02) == 0) {
            scv_print_char(4, 2, 'R');
			right = 1;
        } else {
            scv_print_char(4, 2, '.');
			right = 0;
        }
        if ((scv_pad2_state & 0x01) == 0) {
            scv_print_char(5, 2, 'L');
			left = 1;
        } else {
            scv_print_char(5, 2, '.');
			left = 0;
        }
        if ((scv_pad2_state & 0x02) == 0) {
            scv_print_char(6, 2, 'U');
			up = 1;
        } else {
            scv_print_char(6, 2, '.');
			up = 0;
        }
        if ((scv_pad2_state & 0x04) == 0) {
            scv_print_char(7, 2, 'B');
            p2_btn = 1;
        } else {
            scv_print_char(7, 2, '.');
            p2_btn = 0;
        }
        if ((scv_pad1_state & 0x04) == 0) {
            scv_print_char(9, 2, 'B');
            p1_btn = 1;
        } else {
            scv_print_char(9, 2, '.');
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
            scv_print_char(6, 0, '0');
        } else {
            scv_print_char(6, 0, '1');
        }
        if ((y_dbg & 0x40) == 0) {
            scv_print_char(7, 0, '0');
        } else {
            scv_print_char(7, 0, '1');
        }
        if ((y_dbg & 0x20) == 0) {
            scv_print_char(8, 0, '0');
        } else {
            scv_print_char(8, 0, '1');
        }
        if ((y_dbg & 0x10) == 0) {
            scv_print_char(9, 0, '0');
        } else {
            scv_print_char(9, 0, '1');
        }
        if ((y_dbg & 0x08) == 0) {
            scv_print_char(10, 0, '0');
        } else {
            scv_print_char(10, 0, '1');
        }
        if ((y_dbg & 0x04) == 0) {
            scv_print_char(11, 0, '0');
        } else {
            scv_print_char(11, 0, '1');
        }
        if ((y_dbg & 0x02) == 0) {
            scv_print_char(12, 0, '0');
        } else {
            scv_print_char(12, 0, '1');
        }
        if ((y_dbg & 0x01) == 0) {
            scv_print_char(13, 0, '0');
        } else {
            scv_print_char(13, 0, '1');
        }

        if (up == 1) {
            scv_print_char(17, 0, '1');
        } else {
            scv_print_char(17, 0, '0');
        }
        if (down == 1) {
            scv_print_char(20, 0, '1');
        } else {
            scv_print_char(20, 0, '0');
        }
    }
}
