#include "../tools/scv_api.h"

#pragma scv_asset sprite face "assets/face.png"
#pragma scv_asset spritesheet arrows "assets/arrows.png" 16 16

int main(void) {
    scv_asset_face_load(0);
    scv_asset_arrows_0_load(1);
    scv_asset_arrows_1_load(2);
    scv_asset_arrows_2_load(3);
    scv_asset_arrows_3_load(4);

    scv_set_hw_sprite(0, 40, 40, 0, 15);
    scv_set_hw_sprite(1, 72, 40, 1, 12);
    scv_set_hw_sprite(2, 104, 40, 2, 10);
    scv_set_hw_sprite(3, 136, 40, 3, 9);
    scv_set_hw_sprite(4, 168, 40, 4, 14);

    while (1) {
        scv_wait_vblank();
    }

    return 0;
}