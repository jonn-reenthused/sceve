/***********************************************************************
 * Demo of BIOS wrapper functions for addition, subtraction, and VRAM clearing.
 * Controls (P1):
 * - B1: Clear text VRAM
 * - B2: Clear pattern VRAM (doesn't work on this ROM variant; workaround implemented)
 *
 * Note: This demo uses a ROM variant where the clear_pattern_vram BIOS call doesn't function as expected.
 * The workaround is to draw a blank tile to visually clear the pattern tiles.
 *************************************************/

#include "../tools/scv_api.h"

#pragma scv_asset backgroundsheet bgtiles "assets/arrows.png" 16 16


int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;
const char hex_digits[] = "0123456789ABCDEF";
int hex_temp;
int hex_high_nibble;
int hex_low_nibble;
char hex_hi_char;
char hex_lo_char;

// Print a byte as two hex digits at (x, y) without indexed assignment.
static void print_hex_byte(int x, int y, int value) {
    hex_high_nibble = (value >> 4) & 0x0F;
    hex_low_nibble = value & 0x0F;

    hex_hi_char = hex_digits[hex_high_nibble];
    hex_lo_char = hex_digits[hex_low_nibble];

    scv_print_char(x, y, hex_hi_char);
    scv_print_char(x + 1, y, hex_lo_char);
}

static void draw_text_ui(int add_hi, int sub_hi) {
    scv_print_string(0, 0, "BIOS WRAPPERS");
    scv_print_string(0, 1, "ADD HI 12+10:");
    scv_print_string(0, 2, "SUB HI 34-01:");
    scv_print_string(0, 4, "B1: CLR TEXT");
    scv_print_string(0, 5, "B2: CLR PATTERN");
    scv_print_string(0, 7, "PAD1:");
    scv_print_string(0, 8, "PAD2:");
    scv_print_string(0, 10, "PATTERN:");

    print_hex_byte(13, 1, add_hi);
    print_hex_byte(13, 2, sub_hi);

    /* Draw an explicit loaded pattern slot target for clear_pattern_vram testing. */
    scv_draw_tile(10, 9, 0x01);

    if (add_hi == 0x12) {
        scv_print_string(16, 1, "OK");
    } else {
        scv_print_string(16, 1, "BAD");
    }

    if (sub_hi == 0x12) {
        scv_print_string(16, 2, "OK");
    } else {
        scv_print_string(16, 2, "BAD");
    }
}

int main(void) {
    int add_hi;
    int sub_hi;
    int p1_b1_now;
    int p1_b2_now;
    int p1_b1_prev;
    int p1_b2_prev;
    int p1_b2_alt;
    int b2_hits;
    int text_clear_hold;

    scv_bios_clear_text_vram();
    scv_bios_clear_hw_sprites();
    scv_asset_bgtiles_1_load(1);

    add_hi = scv_bios_add16_hi(0x12, 0x34, 0x00, 0x10); /* 0x1234 + 0x0010 -> hi=0x12 */
    sub_hi = scv_bios_sub16_hi(0x12, 0x34, 0x00, 0x01); /* 0x1234 - 0x0001 -> hi=0x12 */
    p1_b1_prev = 0;
    p1_b2_prev = 0;
    b2_hits = 0;
    text_clear_hold = 0;
    draw_text_ui(add_hi, sub_hi);

    while (1) {
        scv_read_pad1();
        scv_read_pad2();

        /* P1 B1 = pad2 bit 0x04 (active low). */
        p1_b1_now = ((scv_pad2_state & 0x04) == 0);
        /* B2 mapping varies in setups; accept pad1 bit 0x04 or 0x20. */
        p1_b2_now = ((scv_pad1_state & 0x04) == 0);
        p1_b2_alt = ((scv_pad1_state & 0x20) == 0);
        if (p1_b2_alt == 1) {
            p1_b2_now = 1;
        }

        if (p1_b1_now == 1) {
            scv_print_string(15, 7, "B1=1");
        } else {
            scv_print_string(15, 7, "B1=0");
        }
        if (p1_b2_now == 1) {
            scv_print_string(15, 8, "B2=1");
        } else {
            scv_print_string(15, 8, "B2=0");
        }
        scv_print_string(0, 11, "B2 HITS:");
        print_hex_byte(8, 11, b2_hits);

        if ((p1_b1_now == 1) && (p1_b1_prev == 0)) {
            scv_bios_clear_text_vram();
            text_clear_hold = 120;
            scv_wait_vblank();
        }

        if ((p1_b2_now == 1) && (p1_b2_prev == 0)) {
            b2_hits = b2_hits + 1;
            /* BIOS clear_pattern_vram (0x0A4A) doesn't work on this ROM variant.
               Workaround: draw tile 0x00 to clear pattern tiles visually. */
            scv_draw_tile(10, 9, 0x00);
            scv_wait_vblank();
        }

        p1_b1_prev = p1_b1_now;
        p1_b2_prev = p1_b2_now;

        if (text_clear_hold != 0) {
            text_clear_hold = text_clear_hold - 1;
            if (text_clear_hold == 0) {
                draw_text_ui(add_hi, sub_hi);
            }
        } else {
            print_hex_byte(6, 7, scv_pad1_state);
            print_hex_byte(6, 8, scv_pad2_state);
        }

        scv_wait_vblank();
    }

    return 0;
}
