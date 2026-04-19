#include "../tools/scv_api.h"

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

#pragma scv_cart_profile banked64

const unsigned char title_line[] = "BANK OK";

#pragma scv_bank_data(1) banked_message
const unsigned char banked_message[] = "BANKED";

unsigned char banked_counter;

#pragma scv_bank 1
void banked_tick(void) {
    if (banked_counter < 99) {
        banked_counter = banked_counter + 1;
    } else {
        banked_counter = 0;
    }
}

int main(void) {
    scv_print_string(0, 0, title_line);
    while (1) {
        banked_tick();
        scv_wait_vblank();
    }
}
