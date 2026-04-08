#include "../tools/scv_api.h"

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

const char label_nest_sum[] = "NEST S=";
const char label_lives[] = "L=";

struct Vec2 {
    int x;
    int y;
};

struct Player {
    struct Vec2 pos;
    int lives;
};

int main(void) {
    struct Player p;
    int sum;

    p.pos.x = 2;
    p.pos.y = 5;
    p.lives = 3;
    sum = p.pos.x + p.pos.y;

    scv_print_string(0, 0, label_nest_sum);
    scv_print_char(0, 7, '0' + sum);
    scv_print_string(5, 1, label_lives);
    scv_print_char(1, 7, '0' + p.lives);

    while (1) {
        scv_wait_vblank();
    }
}
