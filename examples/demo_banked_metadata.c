#include "../tools/scv_api.h"

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

#pragma scv_cart_profile banked64
#pragma scv_bank_data(1) cutscene_tiles
const unsigned char cutscene_tiles[] = {
    0, 1, 2, 3,
    4, 5, 6, 7
};

void show_title(void) {
    scv_print_string(0, 0, "BANK META");
}

#pragma scv_bank 1
void load_bank1_assets(void) {
    scv_load_bg_pattern_array(0, cutscene_tiles, 0);
}

int main(void) {
    show_title();
    while (1) {
        scv_wait_vblank();
    }
}
