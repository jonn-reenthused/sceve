#include "../tools/scv_api.h"

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

int main(void) {
    scv_print_string(0, 0, "Hello");
    scv_print_string(0, 1, "World");
    scv_print_string(0, 2, "Test");
    
    while (1) {
        scv_wait_vblank();
    }
}
