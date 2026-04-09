#include "../tools/scv_api.h"

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

int main(void) {
    scv_set_sprite(0, 12, 6, 'A');
    scv_set_sprite(1, 15, 6, 'B');

    scv_move_sprite(1, 12, 6);
    scv_check_collision(0, 1);

    if (scv_collision_result != 0) {
        scv_print_char(8, 8, 'H');
        scv_print_char(9, 8, 'I');
        scv_print_char(10, 8, 'T');
    }

    scv_hide_sprite(1);

    return 0;
}
