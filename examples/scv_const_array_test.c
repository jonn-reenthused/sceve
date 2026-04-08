#include "../tools/scv_api.h"

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

const int wave[5] = {1, 2, 3, 4, 5};
const char label_arr_total[] = "ARR T=";

int main(void) {
    int i;
    int total;

    i = 0;
    total = 0;
    while (i < 5) {
        total = total + wave[i];
        i = i + 1;
    }

    scv_print_string(0, 0, label_arr_total);
    scv_print_char(0, 6, '0' + 1);
    scv_print_char(0, 7, '0' + (total - 10));

    while (1) {
        scv_wait_vblank();
    }
}
