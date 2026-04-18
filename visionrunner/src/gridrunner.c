#include "../../tools/scv_api.h"

/*
 * Vision Runner
 * Johnny Blanchard 2026-04-18
 * An example game for the SCeVe Super Cassette Vision SDK. This shows off using sprite sheets
 * and hardware sprites, controls, collision detection, and sound effects.
 * A big apology to Jeff for this hacky version of his great game
*/

// Here i've split up the various spritesheets, but you could just put them all in one
// Sprites are 16x16 and for best results use a transparent background and one colour for
// all the pixels, you'll set a colour later.
// You can also overlay sprites if you want multicolours
#pragma scv_asset spritesheet player "../assets/player.png" 16 16
#pragma scv_asset spritesheet enemy "../assets/enemy.png" 16 16
#pragma scv_asset spritesheet shot "../assets/shot.png" 16 16

enum SpritePattern {
    PLAYER_BASE_PATTERN = 0,
    PLAYER_FRAME_HORIZONTAL = 0,
    PLAYER_FRAME_VERTICAL = 1,
    ENEMY_BASE_PATTERN = 2,
    SHOT_BASE_PATTERN = 6,
    SHOT_FRAME_VERTICAL = 0,
    SHOT_FRAME_HORIZONTAL = 1
};

enum SoundState {
    SOUND_NONE = 0,
    SOUND_PLAYER_FIRE = 1,
    SOUND_ENEMY_FIRE = 2,
    SOUND_HIT = 3
};

enum GridLayout {
    PLAYER_LEFT_X = 32,
    PLAYER_BOTTOM_Y = 210,
    GRID_MIN_X = 40,
    GRID_MAX_X = 200,
    GRID_STEP_X = 16,
    GRID_MIN_Y = 40,
    GRID_MAX_Y = 152,
    ENEMY_MAX_Y = 136,
    GRID_STEP_Y = 16,
    SPRITE_HITBOX_SIZE = 12,
    PLAYER_REPEAT_DELAY = 8,
    PLAYER_REPEAT_RATE = 3,
    PLAYER_FIRE_SOUND_TICKS = 4,
    ENEMY_FIRE_SOUND_TICKS = 4,
    GRID_CHAR_COL_START = 2,
    GRID_CHAR_ROW_START = 2,
    GRID_CHAR_COL_COUNT = 11,
    GRID_CHAR_ROW_COUNT = 10,
    ENEMY1_MOVE_TICKS = 8,
    ENEMY2_MOVE_TICKS = 6
};

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

int bottom_player_x;
int bottom_player_y;
int side_player_x;
int side_player_y;
int enemy_x;
int enemy_y;
int enemy_dir;
int enemy_y_dir;
int enemy_frame;
int enemy_tick;
int enemy2_x;
int enemy2_y;
int enemy2_dir;
int enemy2_y_dir;
int enemy2_frame;
int enemy2_tick;
int bottom_shot_x;
int bottom_shot_y;
int bottom_shot_active;
int side_shot_x;
int side_shot_y;
int side_shot_active;
int enemy_shot_x;
int enemy_shot_y;
int enemy_shot_active;
int enemy_fire_tick;
int enemy_fire_sound_tick;
int player_fire_sound_tick;
int active_sound;
int score;
int lives;
int fire_down;
int left_down;
int right_down;
int up_down;
int down_down;
int hit_flash;
int hit_sound_tick;
int lane_tick;
int game_over;

void load_assets(void)
{
	// This is the two different ways of loading sprite sheets
	// The first way just finds all 16x16 tiles and loads them all starting
	// at index 0

	// The second way is to load each index, in this case it still loads all
	// the tiles, but does them one at a time starting at indexes 2,3,4 and 5

    scv_asset_player_load_all(0);
    scv_asset_enemy_0_load(2);
    scv_asset_enemy_1_load(3);
    scv_asset_enemy_2_load(4);
    scv_asset_enemy_3_load(5);
    scv_asset_shot_load_all(6);
}

void draw_hud(void)
{
    scv_print_string(0, 0, "VISIONRUNNER");
    scv_print_string(0, 1, "S:");
    scv_print_string(6, 1, "L:");
}

void draw_grid(void)
{
    int row;
    int col;
    int char_row;
    int char_col;

    row = 0;
    while (row < GRID_CHAR_ROW_COUNT) {
        char_row = GRID_CHAR_ROW_START + row;
        col = 0;
        while (col < GRID_CHAR_COL_COUNT) {
            char_col = GRID_CHAR_COL_START + (col * 2);
            scv_print_char(char_col, char_row, '+');
            if (col + 1 < GRID_CHAR_COL_COUNT) {
                scv_print_char(char_col + 1, char_row, '-');
            }
            col = col + 1;
        }
        row = row + 1;
    }
}

void draw_status(void)
{
    scv_print_char(2, 1, '0' + score);
    scv_print_char(8, 1, '0' + lives);
}

void reset_enemy(void)
{
    enemy_x = GRID_MIN_X;
    enemy_y = GRID_MIN_Y;
    enemy_dir = 0;
    enemy_y_dir = 0;
    enemy_frame = 2;
    enemy_tick = 0;
}

void reset_enemy2(void)
{
    enemy2_x = GRID_MAX_X;
    enemy2_y = 104;
    enemy2_dir = 1;
    enemy2_y_dir = 1;
    enemy2_frame = 4;
    enemy2_tick = 0;
}

void step_enemy_row(int which_enemy)
{
    if (which_enemy == 0) {
        if (enemy_y_dir == 0) {
            enemy_y = enemy_y + GRID_STEP_Y;
            if (enemy_y >= ENEMY_MAX_Y) {
                enemy_y = ENEMY_MAX_Y;
                enemy_y_dir = 1;
            }
        } else {
            enemy_y = enemy_y - GRID_STEP_Y;
            if (enemy_y <= GRID_MIN_Y) {
                enemy_y = GRID_MIN_Y;
                enemy_y_dir = 0;
            }
        }
    } else {
        if (enemy2_y_dir == 0) {
            enemy2_y = enemy2_y + GRID_STEP_Y;
            if (enemy2_y >= ENEMY_MAX_Y) {
                enemy2_y = ENEMY_MAX_Y;
                enemy2_y_dir = 1;
            }
        } else {
            enemy2_y = enemy2_y - GRID_STEP_Y;
            if (enemy2_y <= GRID_MIN_Y) {
                enemy2_y = GRID_MIN_Y;
                enemy2_y_dir = 0;
            }
        }
    }
}

int enemy_is_lined_up(int enemy_pos_x)
{
    if (enemy_pos_x == bottom_player_x) {
        return 1;
    }
    if (enemy_pos_x == side_player_x) {
        return 1;
    }
    return 0;
}

void reset_bottom_shot(void)
{
    bottom_shot_active = 0;
    bottom_shot_x = 0;
    bottom_shot_y = 0;
    scv_hide_hw_sprite(2);
}

void reset_side_shot(void)
{
    side_shot_active = 0;
    side_shot_x = 0;
    side_shot_y = 0;
    scv_hide_hw_sprite(6);
}

void reset_player_shots(void)
{
    reset_bottom_shot();
    reset_side_shot();
}

void reset_enemy_shot(void)
{
    enemy_shot_active = 0;
    enemy_shot_x = 0;
    enemy_shot_y = 0;
    scv_hide_hw_sprite(4);
}

void start_round(void)
{
    bottom_player_x = 120;
    bottom_player_y = PLAYER_BOTTOM_Y;
    side_player_x = PLAYER_LEFT_X;
    side_player_y = 104;
    score = 0;
    lives = 3;
    fire_down = 0;
    left_down = 0;
    right_down = 0;
    up_down = 0;
    down_down = 0;
    hit_flash = 0;
    hit_sound_tick = 0;
    lane_tick = 0;
    game_over = 0;
    enemy_fire_tick = 0;
    enemy_fire_sound_tick = 0;
    player_fire_sound_tick = 0;
    active_sound = SOUND_NONE;
    scv_stop_sound();
    reset_enemy();
    reset_enemy2();
    reset_player_shots();
    reset_enemy_shot();
}

void reset_after_contact(void)
{
    bottom_player_x = 120;
    bottom_player_y = PLAYER_BOTTOM_Y;
    side_player_x = PLAYER_LEFT_X;
    side_player_y = 104;
    reset_enemy();
    reset_enemy2();
    reset_player_shots();
    reset_enemy_shot();
    hit_sound_tick = 0;
    enemy_fire_sound_tick = 0;
    player_fire_sound_tick = 0;
    active_sound = SOUND_NONE;
    scv_stop_sound();
    scv_set_hw_sprite(0, bottom_player_x, bottom_player_y, PLAYER_BASE_PATTERN + PLAYER_FRAME_HORIZONTAL, SCV_WHITE);
    scv_set_hw_sprite(5, side_player_x, side_player_y, PLAYER_BASE_PATTERN + PLAYER_FRAME_VERTICAL, SCV_WHITE);
    scv_set_hw_sprite_anim(1, enemy_x, enemy_y, ENEMY_BASE_PATTERN, enemy_frame - ENEMY_BASE_PATTERN, SCV_ORANGE);
    scv_set_hw_sprite_anim(3, enemy2_x, enemy2_y, ENEMY_BASE_PATTERN, enemy2_frame - ENEMY_BASE_PATTERN, SCV_YELLOW);
}

void render_scene(void)
{
    scv_set_hw_sprite(0, bottom_player_x, bottom_player_y, PLAYER_BASE_PATTERN + PLAYER_FRAME_HORIZONTAL, SCV_WHITE);
    scv_set_hw_sprite(5, side_player_x, side_player_y, PLAYER_BASE_PATTERN + PLAYER_FRAME_VERTICAL, SCV_WHITE);
    scv_set_hw_sprite_anim(1, enemy_x, enemy_y, ENEMY_BASE_PATTERN, enemy_frame - ENEMY_BASE_PATTERN, SCV_ORANGE);
    scv_set_hw_sprite_anim(3, enemy2_x, enemy2_y, ENEMY_BASE_PATTERN, enemy2_frame - ENEMY_BASE_PATTERN, SCV_YELLOW);

    if (bottom_shot_active == 1) {
        scv_set_hw_sprite(2, bottom_shot_x, bottom_shot_y, SHOT_BASE_PATTERN + SHOT_FRAME_VERTICAL, SCV_CYAN);
    } else {
        scv_hide_hw_sprite(2);
    }

    if (enemy_shot_active == 1) {
        scv_set_hw_sprite(4, enemy_shot_x, enemy_shot_y, SHOT_BASE_PATTERN + SHOT_FRAME_VERTICAL, SCV_RED);
    } else {
        scv_hide_hw_sprite(4);
    }

    if (side_shot_active == 1) {
        scv_set_hw_sprite(6, side_shot_x, side_shot_y, SHOT_BASE_PATTERN + SHOT_FRAME_HORIZONTAL, SCV_CYAN);
    } else {
        scv_hide_hw_sprite(6);
    }
}

void read_input(void)
{
	// A slightly annoying quirk of the hardware is that you have to read both pads
	// in order to get the correct state for either one

    scv_read_pad1();
    scv_read_pad2();
}

void update_player(void)
{
    if (scv_is_p1_left_pressed(scv_pad2_state)) {
        if (scv_is_p1_right_pressed(scv_pad1_state) == 0) {
            if (left_down == 0) {
                if (bottom_player_x > GRID_MIN_X) {
                    bottom_player_x = bottom_player_x - GRID_STEP_X;
                    if (bottom_player_x < GRID_MIN_X) {
                        bottom_player_x = GRID_MIN_X;
                    }
                    scv_set_hw_sprite_pos(0, bottom_player_x, bottom_player_y);
                }
                left_down = PLAYER_REPEAT_DELAY;
            } else {
                left_down = left_down - 1;
                if (left_down == 0) {
                    if (bottom_player_x > GRID_MIN_X) {
                        bottom_player_x = bottom_player_x - GRID_STEP_X;
                        if (bottom_player_x < GRID_MIN_X) {
                            bottom_player_x = GRID_MIN_X;
                        }
                        scv_set_hw_sprite_pos(0, bottom_player_x, bottom_player_y);
                    }
                    left_down = PLAYER_REPEAT_RATE;
                }
            }
        } else {
            left_down = 0;
        }
    } else {
        left_down = 0;
    }

    if (scv_is_p1_right_pressed(scv_pad1_state)) {
        if (scv_is_p1_left_pressed(scv_pad2_state) == 0) {
            if (right_down == 0) {
                if (bottom_player_x < GRID_MAX_X) {
                    bottom_player_x = bottom_player_x + GRID_STEP_X;
                    if (bottom_player_x > GRID_MAX_X) {
                        bottom_player_x = GRID_MAX_X;
                    }
                    scv_set_hw_sprite_pos(0, bottom_player_x, bottom_player_y);
                }
                right_down = PLAYER_REPEAT_DELAY;
            } else {
                right_down = right_down - 1;
                if (right_down == 0) {
                    if (bottom_player_x < GRID_MAX_X) {
                        bottom_player_x = bottom_player_x + GRID_STEP_X;
                        if (bottom_player_x > GRID_MAX_X) {
                            bottom_player_x = GRID_MAX_X;
                        }
                        scv_set_hw_sprite_pos(0, bottom_player_x, bottom_player_y);
                    }
                    right_down = PLAYER_REPEAT_RATE;
                }
            }
        } else {
            right_down = 0;
        }
    } else {
        right_down = 0;
    }

    if (scv_is_p1_up_pressed(scv_pad2_state)) {
        if (scv_is_p1_down_pressed(scv_pad1_state) == 0) {
            if (up_down == 0) {
                if (side_player_y > GRID_MIN_Y) {
                    side_player_y = side_player_y - GRID_STEP_Y;
                    if (side_player_y < GRID_MIN_Y) {
                        side_player_y = GRID_MIN_Y;
                    }
                    scv_set_hw_sprite_pos(5, side_player_x, side_player_y);
                }
                up_down = PLAYER_REPEAT_DELAY;
            } else {
                up_down = up_down - 1;
                if (up_down == 0) {
                    if (side_player_y > GRID_MIN_Y) {
                        side_player_y = side_player_y - GRID_STEP_Y;
                        if (side_player_y < GRID_MIN_Y) {
                            side_player_y = GRID_MIN_Y;
                        }
                        scv_set_hw_sprite_pos(5, side_player_x, side_player_y);
                    }
                    up_down = PLAYER_REPEAT_RATE;
                }
            }
        } else {
            up_down = 0;
        }
    } else {
        up_down = 0;
    }

    if (scv_is_p1_down_pressed(scv_pad1_state)) {
        if (scv_is_p1_up_pressed(scv_pad2_state) == 0) {
            if (down_down == 0) {
                if (side_player_y < GRID_MAX_Y) {
                    side_player_y = side_player_y + GRID_STEP_Y;
                    if (side_player_y > GRID_MAX_Y) {
                        side_player_y = GRID_MAX_Y;
                    }
                    scv_set_hw_sprite_pos(5, side_player_x, side_player_y);
                }
                down_down = PLAYER_REPEAT_DELAY;
            } else {
                down_down = down_down - 1;
                if (down_down == 0) {
                    if (side_player_y < GRID_MAX_Y) {
                        side_player_y = side_player_y + GRID_STEP_Y;
                        if (side_player_y > GRID_MAX_Y) {
                            side_player_y = GRID_MAX_Y;
                        }
                        scv_set_hw_sprite_pos(5, side_player_x, side_player_y);
                    }
                    down_down = PLAYER_REPEAT_RATE;
                }
            }
        } else {
            down_down = 0;
        }
    } else {
        down_down = 0;
    }
}

void update_fire(void)
{
    int fire_pressed;
    int spawned_shot;

    fire_pressed = 0;
    spawned_shot = 0;
    if (scv_is_p1_fire1_pressed(scv_pad2_state)) {
        fire_pressed = 1;
    }
    if (scv_is_p1_fire2_pressed(scv_pad1_state)) {
        fire_pressed = 1;
    }

    if (fire_pressed == 1) {
        if (game_over == 1) {
            if (fire_down == 0) {
                start_round();
                draw_grid();
                render_scene();
                draw_status();
            }
            fire_down = 1;
            return;
        }

        if (fire_down == 0) {
            if (bottom_shot_active == 0) {
                bottom_shot_active = 1;
                bottom_shot_x = bottom_player_x;
                bottom_shot_y = bottom_player_y - 16;
                scv_set_hw_sprite(2, bottom_shot_x, bottom_shot_y, SHOT_BASE_PATTERN + SHOT_FRAME_VERTICAL, SCV_CYAN);
                spawned_shot = 1;
            }

            if (side_shot_active == 0) {
                side_shot_active = 1;
                side_shot_x = side_player_x + 16;
                side_shot_y = side_player_y;
                scv_set_hw_sprite(6, side_shot_x, side_shot_y, SHOT_BASE_PATTERN + SHOT_FRAME_HORIZONTAL, SCV_CYAN);
                spawned_shot = 1;
            }

            if (spawned_shot == 1) {
                hit_sound_tick = 0;
                enemy_fire_sound_tick = 0;
                player_fire_sound_tick = PLAYER_FIRE_SOUND_TICKS;
                active_sound = SOUND_PLAYER_FIRE;
                scv_stop_sound();
                scv_play_tone_packet(0x90, 0x1A);
            }
        }
        fire_down = 1;
    } else {
        fire_down = 0;
    }
}

void update_enemies(void)
{
    lane_tick = lane_tick + 1;
    if (lane_tick == 64) {
        lane_tick = 0;
    }

    enemy_tick = enemy_tick + 1;
    if (enemy_tick == ENEMY1_MOVE_TICKS) {
        enemy_tick = 0;

        if (enemy_dir == 0) {
            enemy_x = enemy_x + GRID_STEP_X;
            if (enemy_x >= GRID_MAX_X) {
                enemy_x = GRID_MAX_X;
                enemy_dir = 1;
                step_enemy_row(0);
            }
        } else {
            enemy_x = enemy_x - GRID_STEP_X;
            if (enemy_x <= GRID_MIN_X) {
                enemy_x = GRID_MIN_X;
                enemy_dir = 0;
                step_enemy_row(0);
            }
        }

        enemy_frame = enemy_frame + 1;
        if (enemy_frame == 5) {
            enemy_frame = 2;
        }
        scv_set_hw_sprite_frame(1, ENEMY_BASE_PATTERN, enemy_frame - ENEMY_BASE_PATTERN);
    }

    scv_set_hw_sprite_pos(1, enemy_x, enemy_y);

    enemy2_tick = enemy2_tick + 1;
    if (enemy2_tick == ENEMY2_MOVE_TICKS) {
        enemy2_tick = 0;

        if (enemy2_dir == 0) {
            enemy2_x = enemy2_x + GRID_STEP_X;
            if (enemy2_x >= GRID_MAX_X) {
                enemy2_x = GRID_MAX_X;
                enemy2_dir = 1;
                step_enemy_row(1);
            }
        } else {
            enemy2_x = enemy2_x - GRID_STEP_X;
            if (enemy2_x <= GRID_MIN_X) {
                enemy2_x = GRID_MIN_X;
                enemy2_dir = 0;
                step_enemy_row(1);
            }
        }

        enemy2_frame = enemy2_frame + 1;
        if (enemy2_frame == 5) {
            enemy2_frame = 2;
        }
        scv_set_hw_sprite_frame(3, ENEMY_BASE_PATTERN, enemy2_frame - ENEMY_BASE_PATTERN);
    }

    scv_set_hw_sprite_pos(3, enemy2_x, enemy2_y);

    enemy_fire_tick = enemy_fire_tick + 1;
}

void update_bottom_shot(void)
{
    if (bottom_shot_active == 1) {
        bottom_shot_y = bottom_shot_y - 4;
        if (bottom_shot_y <= 20) {
            reset_bottom_shot();
        } else {
            scv_set_hw_sprite_pos(2, bottom_shot_x, bottom_shot_y);
        }
    }
}

void update_side_shot(void)
{
    if (side_shot_active == 1) {
        side_shot_x = side_shot_x + 4;
        if (side_shot_x >= 190) {
            reset_side_shot();
        } else {
            scv_set_hw_sprite_pos(6, side_shot_x, side_shot_y);
        }
    }
}

void spawn_enemy_shot(int start_x, int start_y)
{
    if (enemy_shot_active == 0) {
        enemy_shot_active = 1;
        enemy_shot_x = start_x;
        enemy_shot_y = start_y + 12;
        scv_set_hw_sprite(4, enemy_shot_x, enemy_shot_y, SHOT_BASE_PATTERN + SHOT_FRAME_VERTICAL, SCV_RED);
        player_fire_sound_tick = 0;
        enemy_fire_sound_tick = ENEMY_FIRE_SOUND_TICKS;
        active_sound = SOUND_ENEMY_FIRE;
        scv_stop_sound();
        scv_play_tone_packet(0x58, 0x16);
    }
}

void update_enemy_fire(void)
{
    if (enemy_shot_active == 0) {
        if ((enemy_fire_tick & 0x0f) == 0) {
            if (enemy_is_lined_up(enemy_x)) {
                spawn_enemy_shot(enemy_x, enemy_y);
                return;
            }
        }

        if ((enemy_fire_tick & 0x0f) == 8) {
            if (enemy_is_lined_up(enemy2_x)) {
                spawn_enemy_shot(enemy2_x, enemy2_y);
                return;
            }
        }

        if (enemy_fire_tick == 48) {
            spawn_enemy_shot(enemy_x, enemy_y);
        }
        if (enemy_fire_tick == 96) {
            spawn_enemy_shot(enemy2_x, enemy2_y);
            enemy_fire_tick = 0;
        }
    }
}

void update_enemy_shot(void)
{
    if (enemy_shot_active == 1) {
        enemy_shot_y = enemy_shot_y + 4;
        if (enemy_shot_y >= 190) {
            reset_enemy_shot();
        } else {
            scv_set_hw_sprite_pos(4, enemy_shot_x, enemy_shot_y);
        }
    }
}

void handle_hit(void)
{
    score = score + 1;
    if (score == 10) {
        score = 0;
        if (lives < 9) {
            lives = lives + 1;
        }
    }

    hit_flash = 12;
    hit_sound_tick = 12;
    player_fire_sound_tick = 0;
    enemy_fire_sound_tick = 0;
    active_sound = SOUND_HIT;
    scv_stop_sound();
    scv_play_tone_packet(0x68, 0x1C);
    reset_player_shots();
    reset_enemy_shot();
    reset_enemy();
    reset_enemy2();
    scv_set_hw_sprite_anim(1, enemy_x, enemy_y, ENEMY_BASE_PATTERN, enemy_frame - ENEMY_BASE_PATTERN, SCV_ORANGE);
    scv_set_hw_sprite_anim(3, enemy2_x, enemy2_y, ENEMY_BASE_PATTERN, enemy2_frame - ENEMY_BASE_PATTERN, SCV_YELLOW);
}

void handle_player_contact(void)
{
    hit_flash = 18;
    hit_sound_tick = 18;
    player_fire_sound_tick = 0;
    enemy_fire_sound_tick = 0;
    active_sound = SOUND_HIT;
    scv_stop_sound();
    scv_play_tone_packet(0x48, 0x1E);

    if (lives > 0) {
        lives = lives - 1;
    }

    if (lives == 0) {
        game_over = 1;
        scv_print_string(9, 5, "GAME OVER");
        scv_print_string(3, 7, "PRESS FIRE");
        scv_print_string(2, 8, "TO RESTART");
        reset_player_shots();
        scv_hide_hw_sprite(1);
        scv_hide_hw_sprite(3);
    } else {
        reset_after_contact();
    }
}

int sprite_overlap(int ax, int ay, int bx, int by)
{
    if (ax + SPRITE_HITBOX_SIZE < bx) {
        return 0;
    }
    if (ax > bx + SPRITE_HITBOX_SIZE) {
        return 0;
    }
    if (ay + SPRITE_HITBOX_SIZE < by) {
        return 0;
    }
    if (ay > by + SPRITE_HITBOX_SIZE) {
        return 0;
    }
    return 1;
}

void check_enemy_shot_hit(void)
{
    if (enemy_shot_active == 1) {
        if (sprite_overlap(enemy_shot_x, enemy_shot_y, bottom_player_x, bottom_player_y)) {
            reset_enemy_shot();
            handle_player_contact();
            return;
        }

        if (sprite_overlap(enemy_shot_x, enemy_shot_y, side_player_x, side_player_y)) {
            reset_enemy_shot();
            handle_player_contact();
            return;
        }
    }
}

void check_shot_hit(void)
{
    if (bottom_shot_active == 1) {
        if (sprite_overlap(bottom_shot_x, bottom_shot_y, enemy_x, enemy_y)) {
            handle_hit();
            return;
        }

        if (sprite_overlap(bottom_shot_x, bottom_shot_y, enemy2_x, enemy2_y)) {
            handle_hit();
            return;
        }
    }

    if (side_shot_active == 1) {
        if (sprite_overlap(side_shot_x, side_shot_y, enemy_x, enemy_y)) {
            handle_hit();
            return;
        }

        if (sprite_overlap(side_shot_x, side_shot_y, enemy2_x, enemy2_y)) {
            handle_hit();
            return;
        }
    }
}

void check_player_hit(void)
{
    if (game_over == 1) {
        return;
    }

    if (sprite_overlap(bottom_player_x, bottom_player_y, enemy_x, enemy_y)) {
        handle_player_contact();
        return;
    }

    if (sprite_overlap(bottom_player_x, bottom_player_y, enemy2_x, enemy2_y)) {
        handle_player_contact();
        return;
    }

    if (sprite_overlap(side_player_x, side_player_y, enemy_x, enemy_y)) {
        handle_player_contact();
        return;
    }

    if (sprite_overlap(side_player_x, side_player_y, enemy2_x, enemy2_y)) {
        handle_player_contact();
        return;
    }
}

void tick_effects(void)
{
    if (hit_flash > 0) {
        hit_flash = hit_flash - 1;
    }

    if (hit_sound_tick > 0) {
        hit_sound_tick = hit_sound_tick - 1;
        if (hit_sound_tick == 0) {
            if (active_sound == SOUND_HIT) {
                active_sound = SOUND_NONE;
                scv_stop_sound();
            }
        }
    }

    if (player_fire_sound_tick > 0) {
        player_fire_sound_tick = player_fire_sound_tick - 1;
        if (player_fire_sound_tick == 0) {
            if (active_sound == SOUND_PLAYER_FIRE) {
                active_sound = SOUND_NONE;
                scv_stop_sound();
            }
        }
    }

    if (enemy_fire_sound_tick > 0) {
        enemy_fire_sound_tick = enemy_fire_sound_tick - 1;
        if (enemy_fire_sound_tick == 0) {
            if (active_sound == SOUND_ENEMY_FIRE) {
                active_sound = SOUND_NONE;
                scv_stop_sound();
            }
        }
    }
}

int main(void)
{
    load_assets();
    draw_hud();
    draw_grid();
    start_round();
    render_scene();
    draw_status();

    while (1) {
        scv_wait_vblank();
        read_input();
        update_fire();
        if (game_over == 0) {
            update_player();
            update_enemies();
            update_enemy_fire();
            update_bottom_shot();
            update_side_shot();
            update_enemy_shot();
            check_shot_hit();
            check_enemy_shot_hit();
            check_player_hit();
        }
        tick_effects();
        draw_status();
    }

    return 0;
}
