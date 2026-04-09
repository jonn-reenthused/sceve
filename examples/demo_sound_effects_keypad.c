#include "../tools/scv_api.h"

/* Keypad-triggered SFX bank demo with edge-triggered playback. */

#pragma scv_asset sound noise sfx_noise_hit 0x20 0x10 0x08 0x04 0x02 0x01 0x04 0x08 0x10 0x20

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

const char hex_digits[] = "0123456789ABCDEF";

int effect_hits;
int last_effect_id;
int last_key_number;
int last_active_key;

int hex_high_nibble;
int hex_low_nibble;
char hex_hi_char;
char hex_lo_char;

static void print_hex_byte(int x, int y, int value) {
    hex_high_nibble = (value >> 4) & 0x0F;
    hex_low_nibble = value & 0x0F;

    hex_hi_char = hex_digits[hex_high_nibble];
    hex_lo_char = hex_digits[hex_low_nibble];

    scv_print_char(x, y, hex_hi_char);
    scv_print_char(x + 1, y, hex_lo_char);
}

static void wait_frames(int frames) {
    while (frames > 0) {
        scv_wait_vblank();
        frames = frames - 1;
    }
}

static void play_tone_step(int pitch, int param, int frames) {
    scv_stop_sound();
    scv_play_tone_packet(pitch, param);
    wait_frames(frames);
}

static void play_fx_beep(void) {
    play_tone_step(0x84, 0x12, 7);
    scv_stop_sound();
    wait_frames(2);
    play_tone_step(0x84, 0x12, 8);
    scv_stop_sound();
}

static void play_fx_horn(void) {
    play_tone_step(0x64, 0x18, 10);
    play_tone_step(0x58, 0x1A, 10);
    play_tone_step(0x64, 0x18, 10);
    play_tone_step(0x58, 0x1A, 12);
    scv_stop_sound();
}

static void play_fx_explosion(void) {
    play_tone_step(0x78, 0x1A, 4);
    play_tone_step(0x68, 0x1C, 4);
    play_tone_step(0x58, 0x1E, 4);
    play_tone_step(0x48, 0x1E, 4);
    scv_stop_sound();
    scv_asset_sfx_noise_hit_play();
    wait_frames(10);
    scv_stop_sound();
}

static void play_fx_shot(void) {
    play_tone_step(0xD0, 0x10, 1);
    play_tone_step(0xB8, 0x10, 1);
    play_tone_step(0x98, 0x10, 1);
    wait_frames(1);
    scv_stop_sound();
}

static void play_fx_lazer(void) {
    play_tone_step(0x44, 0x12, 2);
    play_tone_step(0x64, 0x12, 2);
    play_tone_step(0x4C, 0x12, 2);
    play_tone_step(0x74, 0x12, 2);
    play_tone_step(0x54, 0x12, 2);
    play_tone_step(0x7C, 0x12, 2);
    play_tone_step(0x5C, 0x12, 2);
    play_tone_step(0x84, 0x12, 2);
    scv_stop_sound();
}

static int read_fixed_key_number(int scan_fb_now,
                                 int scan_f7_now,
                                 int scan_ee_now) {
    if ((scan_fb_now & 0x80) == 0) { return 1; }
    if ((scan_f7_now & 0x40) == 0) { return 2; }
    if ((scan_f7_now & 0x80) == 0) { return 3; }
    if ((scan_ee_now & 0x40) == 0) { return 4; }
    if ((scan_ee_now & 0x80) == 0) { return 5; }
    return 0;
}

static void play_effect_id(int effect_id) {
    if (effect_id == 0) {
        play_fx_beep();
    } else if (effect_id == 1) {
        play_fx_horn();
    } else if (effect_id == 2) {
        play_fx_explosion();
    } else if (effect_id == 3) {
        play_fx_shot();
    } else if (effect_id == 4) {
        play_fx_lazer();
    }
}

int main(void) {
    int scan_fb_now;
    int scan_f7_now;
    int scan_ee_now;
    int key_number;
    int triggered_effect;

    effect_hits = 0;
    last_effect_id = -1;
    last_key_number = 0;
    last_active_key = 0;

    scv_bios_clear_text_vram();
    scv_bios_clear_hw_sprites();
    scv_set_vdc_regs(0xF4, 0x00, 0x00, 0xF1);

    while (1) {
        scv_read_pad1();
        scv_read_pad2();

        scan_fb_now = scv_read_input_scan(0xFB);
        scan_f7_now = scv_read_input_scan(0xF7);
        scan_ee_now = scv_read_input_scan(0xEE);

        key_number = read_fixed_key_number(scan_fb_now, scan_f7_now, scan_ee_now);
        triggered_effect = -1;

        if ((key_number != 0) && (key_number != last_active_key)) {
            last_active_key = key_number;
        } else if (key_number == 0) {
            last_active_key = 0;
        } else {
            key_number = 0;
        }

        if (key_number == 1) {
            triggered_effect = 0;
        } else if (key_number == 2) {
            triggered_effect = 1;
        } else if (key_number == 3) {
            triggered_effect = 2;
        } else if (key_number == 4) {
            triggered_effect = 3;
        } else if (key_number == 5) {
            triggered_effect = 4;
        }

        if (triggered_effect >= 0) {
            play_effect_id(triggered_effect);
            effect_hits = effect_hits + 1;
            last_effect_id = triggered_effect;
            last_key_number = key_number;
        } else {
            /* Keep the mixer quiet unless an effect was explicitly triggered. */
            scv_stop_sound();
        }

        scv_wait_vblank();

        scv_print_string(0, 0, "KEYPAD SFX");
        scv_print_string(0, 2, "1 BEEP");
        scv_print_string(0, 3, "2 HORN");
        scv_print_string(0, 4, "3 EXPLOSION");
        scv_print_string(0, 5, "4 SHOT");
        scv_print_string(0, 6, "5 LAZER");
        scv_print_string(0, 7, "KEYS 1-5 ACTIVE");
        scv_print_string(0, 8, "LAST KEY:");
        scv_print_string(0, 9, "LAST FX:");
        scv_print_string(0, 10, "HITS:");

        if (last_key_number == 1) {
            scv_print_string(10, 8, "1 ");
        } else if (last_key_number == 2) {
            scv_print_string(10, 8, "2 ");
        } else if (last_key_number == 3) {
            scv_print_string(10, 8, "3 ");
        } else if (last_key_number == 4) {
            scv_print_string(10, 8, "4 ");
        } else if (last_key_number == 5) {
            scv_print_string(10, 8, "5 ");
        } else {
            scv_print_string(10, 8, "- ");
        }

        print_hex_byte(6, 10, effect_hits);

        if (last_effect_id == 0) {
            scv_print_string(6, 9, "BEEP     ");
        } else if (last_effect_id == 1) {
            scv_print_string(6, 9, "HORN     ");
        } else if (last_effect_id == 2) {
            scv_print_string(6, 9, "EXPLOSION");
        } else if (last_effect_id == 3) {
            scv_print_string(6, 9, "SHOT     ");
        } else if (last_effect_id == 4) {
            scv_print_string(6, 9, "LAZER    ");
        } else {
            scv_print_string(6, 9, "NONE     ");
        }
    }
}
