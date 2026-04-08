#include <stdint.h>
#include "scv_api.h"

#pragma scv_asset backgroundsheet bgtiles "assets/arrows.png" 16 16

int main(void) {
    scv_set_vdc_regs(0xD0, 0x00, 0x00, 0xF8);
    scv_asset_bgtiles_0_load(0);
    scv_asset_bgtiles_1_load(1);
    scv_asset_bgtiles_2_load(2);
    scv_asset_bgtiles_3_load(3);
    
    // Render 6x10 grid - NO TEXT PRINTING
    scv_set_hw_sprite_raw(0, 20, 28, 0, 15);
    scv_set_hw_sprite_raw(1, 36, 28, 1, 15);
    scv_set_hw_sprite_raw(2, 52, 28, 2, 15);
    scv_set_hw_sprite_raw(3, 68, 28, 3, 15);
    scv_set_hw_sprite_raw(4, 84, 28, 0, 15);
    scv_set_hw_sprite_raw(5, 100, 28, 1, 15);
    scv_set_hw_sprite_raw(6, 116, 28, 2, 15);
    scv_set_hw_sprite_raw(7, 132, 28, 3, 15);
    scv_set_hw_sprite_raw(8, 148, 28, 0, 15);
    scv_set_hw_sprite_raw(9, 164, 28, 1, 15);
    
    scv_set_hw_sprite_raw(10, 20, 44, 2, 15);
    scv_set_hw_sprite_raw(11, 36, 44, 3, 15);
    scv_set_hw_sprite_raw(12, 52, 44, 0, 15);
    scv_set_hw_sprite_raw(13, 68, 44, 1, 15);
    scv_set_hw_sprite_raw(14, 84, 44, 2, 15);
    scv_set_hw_sprite_raw(15, 100, 44, 3, 15);
    scv_set_hw_sprite_raw(16, 116, 44, 0, 15);
    scv_set_hw_sprite_raw(17, 132, 44, 1, 15);
    scv_set_hw_sprite_raw(18, 148, 44, 2, 15);
    scv_set_hw_sprite_raw(19, 164, 44, 3, 15);
    
    scv_set_hw_sprite_raw(20, 20, 60, 0, 15);
    scv_set_hw_sprite_raw(21, 36, 60, 1, 15);
    scv_set_hw_sprite_raw(22, 52, 60, 2, 15);
    scv_set_hw_sprite_raw(23, 68, 60, 3, 15);
    scv_set_hw_sprite_raw(24, 84, 60, 0, 15);
    scv_set_hw_sprite_raw(25, 100, 60, 1, 15);
    scv_set_hw_sprite_raw(26, 116, 60, 2, 15);
    scv_set_hw_sprite_raw(27, 132, 60, 3, 15);
    scv_set_hw_sprite_raw(28, 148, 60, 0, 15);
    scv_set_hw_sprite_raw(29, 164, 60, 1, 15);
    
    scv_set_hw_sprite_raw(30, 20, 76, 2, 15);
    scv_set_hw_sprite_raw(31, 36, 76, 3, 15);
    scv_set_hw_sprite_raw(32, 52, 76, 0, 15);
    scv_set_hw_sprite_raw(33, 68, 76, 1, 15);
    scv_set_hw_sprite_raw(34, 84, 76, 2, 15);
    scv_set_hw_sprite_raw(35, 100, 76, 3, 15);
    scv_set_hw_sprite_raw(36, 116, 76, 0, 15);
    scv_set_hw_sprite_raw(37, 132, 76, 1, 15);
    scv_set_hw_sprite_raw(38, 148, 76, 2, 15);
    scv_set_hw_sprite_raw(39, 164, 76, 3, 15);
    
    scv_set_hw_sprite_raw(40, 20, 92, 0, 15);
    scv_set_hw_sprite_raw(41, 36, 92, 1, 15);
    scv_set_hw_sprite_raw(42, 52, 92, 2, 15);
    scv_set_hw_sprite_raw(43, 68, 92, 3, 15);
    scv_set_hw_sprite_raw(44, 84, 92, 0, 15);
    scv_set_hw_sprite_raw(45, 100, 92, 1, 15);
    scv_set_hw_sprite_raw(46, 116, 92, 2, 15);
    scv_set_hw_sprite_raw(47, 132, 92, 3, 15);
    scv_set_hw_sprite_raw(48, 148, 92, 0, 15);
    scv_set_hw_sprite_raw(49, 164, 92, 1, 15);
    
    scv_set_hw_sprite_raw(50, 20, 108, 2, 15);
    scv_set_hw_sprite_raw(51, 36, 108, 3, 15);
    scv_set_hw_sprite_raw(52, 52, 108, 0, 15);
    scv_set_hw_sprite_raw(53, 68, 108, 1, 15);
    scv_set_hw_sprite_raw(54, 84, 108, 2, 15);
    scv_set_hw_sprite_raw(55, 100, 108, 3, 15);
    scv_set_hw_sprite_raw(56, 116, 108, 0, 15);
    scv_set_hw_sprite_raw(57, 132, 108, 1, 15);
    scv_set_hw_sprite_raw(58, 148, 108, 2, 15);
    scv_set_hw_sprite_raw(59, 164, 108, 3, 15);
    
    // Hide remaining sprites
    scv_hide_hw_sprite(60);
    scv_hide_hw_sprite(61);
    scv_hide_hw_sprite(62);
    scv_hide_hw_sprite(63);
    
    while (1) scv_wait_vblank();
    return 0;
}
