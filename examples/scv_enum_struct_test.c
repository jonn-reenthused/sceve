#include "../tools/scv_api.h"

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

enum Weapon {
    WEAPON_BASIC = 1,
    WEAPON_LASER = 3,
    WEAPON_PLASMA = 7
};

struct Ship {
    int hp;
    int weapon;
};

const char header[] = "ENM";
const char hp_label[] = "HP";

int main(void) {
    struct Ship ship;

    ship.hp = 9;
    ship.weapon = WEAPON_LASER;

    scv_print_string(0, 0, header);
    scv_print_char(0, 3, ' ');
    scv_print_char(0, 4, 'W');
    scv_print_char(0, 5, '=');
    scv_print_char(0, 6, '0' + ship.weapon);
    scv_print_string(4, 1, hp_label);
    scv_print_char(1, 6, '=');
    scv_print_char(1, 7, '0' + ship.hp);

    while (1) {
        scv_wait_vblank();
    }
}
