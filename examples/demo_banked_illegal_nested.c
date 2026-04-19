#include "../tools/scv_api.h"

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

#pragma scv_cart_profile banked64

#pragma scv_bank 1
void helper_bank1(void) {
    scv_wait_vblank();
}

#pragma scv_bank 1
void load_bank1_assets(void) {
    helper_bank1();
}

int main(void) {
    while (1) {
        scv_wait_vblank();
    }
}
