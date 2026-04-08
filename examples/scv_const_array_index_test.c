#include "../tools/scv_api.h"

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

const int palette_lut[8] = {2, 4, 6, 8, 1, 3, 5, 7};
const char label_idx[] = "IDX I=";
const char label_value[] = "V=";

int main(void) {
    int idx;
    int value;

    idx = 6;
    value = palette_lut[idx];

    scv_print_string(0, 0, label_idx);
    scv_print_char(0, 6, '0' + idx);
    scv_print_string(4, 1, label_value);
    scv_print_char(1, 6, '0' + value);

    while (1) {
        scv_wait_vblank();
    }
}
