#include "../tools/scv_api.h"

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

const char label_text[] = "TEXT";
const char label_api[] = "API";

int main(void) {
    scv_print_string(0, 0, label_text);
    scv_print_string(0, 1, label_api);

    scv_draw_tile(3, 4, 0x23);
    scv_draw_tile(3, 5, 0x24);
    scv_draw_tile(3, 6, 0x25);
    scv_draw_tile(4, 4, 0x26);
    scv_draw_tile(4, 5, 0x27);
    scv_draw_tile(4, 6, 0x28);

    return 0;
}
