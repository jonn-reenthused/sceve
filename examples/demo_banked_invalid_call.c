#include "../tools/scv_api.h"

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

#pragma scv_cart_profile banked64
#pragma scv_bank_data(1) aux_data
const unsigned char aux_data[] = {
    1, 2, 3, 4
};

#pragma scv_bank 1
void load_bank1_assets(void) {
    scv_load_bg_pattern_array(0, aux_data, 0);
}

int main(void) {
    load_bank1_assets();
    while (1) {
        scv_wait_vblank();
    }
}
