#include "../tools/scv_api.h"

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

#pragma scv_cart_profile banked64
const unsigned char title_line[] = "BANK PKG";

#pragma scv_bank_data(1) aux_tiles
const unsigned char aux_tiles[] = {
    0x10, 0x11, 0x12, 0x13,
    0x14, 0x15, 0x16, 0x17,
    0x18, 0x19, 0x1A, 0x1B,
    0x1C, 0x1D, 0x1E, 0x1F
};

int main(void) {
    scv_print_string(0, 0, title_line);
    while (1) {
        scv_wait_vblank();
    }
}
