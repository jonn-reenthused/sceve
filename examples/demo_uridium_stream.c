#include "../tools/scv_api.h"



#pragma scv_asset spritesheet uridium_s00 "assets/uridium_stream_s00.png" 16 16

#pragma scv_asset spritesheet uridium_s01 "assets/uridium_stream_s01.png" 16 16

#pragma scv_asset spritesheet uridium_s02 "assets/uridium_stream_s02.png" 16 16

#pragma scv_asset spritesheet uridium_s03 "assets/uridium_stream_s03.png" 16 16



int scv_pad1_state;

int scv_pad2_state;

int scv_collision_result;



const int uridium_screen_count = 4;

const int uridium_pattern_bank_size = 64;

int current_screen;

int next_screen;

int current_pattern_base;

int next_pattern_base;

int scroll_x;

int frame_div;

int dispatch_screen_id;

int active_pattern_base;

int active_sprite_base;

int active_x_offset;

int draw_result;



const int uridium_screen_00_sprite_count = 59;

const int uridium_screen_00_pattern_count = 55;

const int uridium_screen_00_x[] = {
    20, 36, 52, 68, 84, 100, 132, 148,
    164, 20, 36, 52, 68, 84, 100, 116,
    116, 132, 148, 164, 20, 36, 52, 68,
    84, 100, 116, 132, 148, 164, 20, 36,
    52, 68, 84, 100, 116, 132, 148, 164,
    20, 36, 52, 68, 84, 100, 116, 132,
    148, 164, 20, 36, 52, 68, 84, 132,
    132, 148, 164
};

const int uridium_screen_00_y[] = {
    28, 28, 28, 28, 28, 28, 28, 28,
    28, 44, 44, 44, 44, 44, 44, 44,
    44, 44, 44, 44, 60, 60, 60, 60,
    60, 60, 60, 60, 60, 60, 76, 76,
    76, 76, 76, 76, 76, 76, 76, 76,
    92, 92, 92, 92, 92, 92, 92, 92,
    92, 92, 108, 108, 108, 108, 108, 108,
    108, 108, 108
};

const int uridium_screen_00_pattern[] = {
    0, 1, 2, 3, 4, 5, 6, 7,
    8, 9, 10, 11, 12, 13, 14, 15,
    16, 17, 18, 19, 20, 21, 22, 23,
    24, 25, 26, 27, 28, 29, 30, 31,
    32, 33, 34, 35, 36, 37, 38, 39,
    9, 10, 11, 12, 40, 41, 42, 43,
    44, 45, 46, 47, 48, 49, 50, 51,
    52, 53, 54
};

const int uridium_screen_00_color[] = {
    6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6,
    12, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6,
    12, 6, 6
};

const int uridium_screen_01_sprite_count = 60;

const int uridium_screen_01_pattern_count = 58;

const int uridium_screen_01_x[] = {
    20, 36, 52, 68, 84, 100, 116, 132,
    148, 164, 20, 36, 52, 68, 84, 100,
    116, 132, 148, 164, 20, 36, 52, 68,
    84, 100, 116, 132, 148, 164, 20, 36,
    52, 68, 84, 100, 116, 132, 148, 164,
    20, 36, 52, 68, 84, 100, 116, 132,
    148, 164, 20, 36, 52, 68, 84, 100,
    116, 132, 148, 164
};

const int uridium_screen_01_y[] = {
    28, 28, 28, 28, 28, 28, 28, 28,
    28, 28, 44, 44, 44, 44, 44, 44,
    44, 44, 44, 44, 60, 60, 60, 60,
    60, 60, 60, 60, 60, 60, 76, 76,
    76, 76, 76, 76, 76, 76, 76, 76,
    92, 92, 92, 92, 92, 92, 92, 92,
    92, 92, 108, 108, 108, 108, 108, 108,
    108, 108, 108, 108
};

const int uridium_screen_01_pattern[] = {
    0, 1, 2, 0, 3, 4, 5, 6,
    7, 8, 9, 10, 11, 12, 13, 14,
    15, 16, 17, 18, 19, 20, 21, 22,
    23, 24, 25, 26, 27, 28, 29, 30,
    31, 29, 32, 33, 34, 35, 36, 37,
    38, 39, 40, 41, 42, 43, 44, 45,
    46, 47, 48, 49, 50, 51, 52, 53,
    54, 55, 56, 57
};

const int uridium_screen_01_color[] = {
    6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6
};

const int uridium_screen_02_sprite_count = 60;

const int uridium_screen_02_pattern_count = 56;

const int uridium_screen_02_x[] = {
    20, 36, 52, 68, 84, 100, 116, 132,
    148, 164, 20, 36, 52, 68, 84, 100,
    116, 132, 148, 164, 20, 36, 52, 68,
    84, 100, 116, 132, 148, 164, 20, 36,
    52, 68, 84, 100, 116, 132, 148, 164,
    20, 36, 52, 68, 84, 100, 116, 132,
    148, 164, 20, 36, 52, 68, 84, 100,
    116, 132, 148, 164
};

const int uridium_screen_02_y[] = {
    28, 28, 28, 28, 28, 28, 28, 28,
    28, 28, 44, 44, 44, 44, 44, 44,
    44, 44, 44, 44, 60, 60, 60, 60,
    60, 60, 60, 60, 60, 60, 76, 76,
    76, 76, 76, 76, 76, 76, 76, 76,
    92, 92, 92, 92, 92, 92, 92, 92,
    92, 92, 108, 108, 108, 108, 108, 108,
    108, 108, 108, 108
};

const int uridium_screen_02_pattern[] = {
    0, 1, 2, 3, 4, 5, 6, 4,
    7, 8, 9, 10, 11, 12, 13, 14,
    15, 16, 17, 18, 19, 20, 21, 22,
    23, 24, 25, 26, 27, 28, 29, 30,
    31, 32, 33, 34, 35, 36, 37, 38,
    39, 40, 41, 42, 43, 44, 45, 46,
    47, 48, 49, 50, 51, 52, 53, 54,
    52, 50, 51, 55
};

const int uridium_screen_02_color[] = {
    6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6
};

const int uridium_screen_03_sprite_count = 59;

const int uridium_screen_03_pattern_count = 58;

const int uridium_screen_03_x[] = {
    20, 36, 52, 84, 100, 116, 132, 148,
    164, 20, 36, 52, 68, 68, 84, 100,
    116, 132, 148, 164, 20, 36, 52, 68,
    84, 100, 116, 132, 148, 164, 20, 36,
    36, 52, 68, 84, 100, 116, 132, 148,
    164, 20, 36, 52, 68, 84, 100, 116,
    132, 148, 164, 20, 36, 52, 84, 100,
    116, 132, 164
};

const int uridium_screen_03_y[] = {
    28, 28, 28, 28, 28, 28, 28, 28,
    28, 44, 44, 44, 44, 44, 44, 44,
    44, 44, 44, 44, 60, 60, 60, 60,
    60, 60, 60, 60, 60, 60, 76, 76,
    76, 76, 76, 76, 76, 76, 76, 76,
    76, 92, 92, 92, 92, 92, 92, 92,
    92, 92, 92, 108, 108, 108, 108, 108,
    108, 108, 108
};

const int uridium_screen_03_pattern[] = {
    0, 1, 2, 3, 4, 5, 6, 7,
    8, 9, 10, 11, 12, 13, 14, 15,
    16, 17, 18, 19, 20, 21, 22, 23,
    24, 25, 26, 27, 28, 29, 30, 31,
    32, 33, 34, 35, 36, 37, 38, 39,
    40, 41, 42, 43, 44, 45, 46, 47,
    17, 48, 49, 50, 51, 52, 53, 54,
    55, 56, 57
};

const int uridium_screen_03_color[] = {
    6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 12, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6,
    12, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6
};

void load_screen_00(void) {
    scv_asset_uridium_s00_0_load_raw(active_pattern_base + 0);
    scv_asset_uridium_s00_1_load_raw(active_pattern_base + 1);
    scv_asset_uridium_s00_2_load_raw(active_pattern_base + 2);
    scv_asset_uridium_s00_3_load_raw(active_pattern_base + 3);
    scv_asset_uridium_s00_4_load_raw(active_pattern_base + 4);
    scv_asset_uridium_s00_5_load_raw(active_pattern_base + 5);
    scv_asset_uridium_s00_6_load_raw(active_pattern_base + 6);
    scv_asset_uridium_s00_7_load_raw(active_pattern_base + 7);
    scv_asset_uridium_s00_8_load_raw(active_pattern_base + 8);
    scv_asset_uridium_s00_9_load_raw(active_pattern_base + 9);
    scv_asset_uridium_s00_10_load_raw(active_pattern_base + 10);
    scv_asset_uridium_s00_11_load_raw(active_pattern_base + 11);
    scv_asset_uridium_s00_12_load_raw(active_pattern_base + 12);
    scv_asset_uridium_s00_13_load_raw(active_pattern_base + 13);
    scv_asset_uridium_s00_14_load_raw(active_pattern_base + 14);
    scv_asset_uridium_s00_15_load_raw(active_pattern_base + 15);
    scv_asset_uridium_s00_16_load_raw(active_pattern_base + 16);
    scv_asset_uridium_s00_17_load_raw(active_pattern_base + 17);
    scv_asset_uridium_s00_18_load_raw(active_pattern_base + 18);
    scv_asset_uridium_s00_19_load_raw(active_pattern_base + 19);
    scv_asset_uridium_s00_20_load_raw(active_pattern_base + 20);
    scv_asset_uridium_s00_21_load_raw(active_pattern_base + 21);
    scv_asset_uridium_s00_22_load_raw(active_pattern_base + 22);
    scv_asset_uridium_s00_23_load_raw(active_pattern_base + 23);
    scv_asset_uridium_s00_24_load_raw(active_pattern_base + 24);
    scv_asset_uridium_s00_25_load_raw(active_pattern_base + 25);
    scv_asset_uridium_s00_26_load_raw(active_pattern_base + 26);
    scv_asset_uridium_s00_27_load_raw(active_pattern_base + 27);
    scv_asset_uridium_s00_28_load_raw(active_pattern_base + 28);
    scv_asset_uridium_s00_29_load_raw(active_pattern_base + 29);
    scv_asset_uridium_s00_30_load_raw(active_pattern_base + 30);
    scv_asset_uridium_s00_31_load_raw(active_pattern_base + 31);
    scv_asset_uridium_s00_32_load_raw(active_pattern_base + 32);
    scv_asset_uridium_s00_33_load_raw(active_pattern_base + 33);
    scv_asset_uridium_s00_34_load_raw(active_pattern_base + 34);
    scv_asset_uridium_s00_35_load_raw(active_pattern_base + 35);
    scv_asset_uridium_s00_36_load_raw(active_pattern_base + 36);
    scv_asset_uridium_s00_37_load_raw(active_pattern_base + 37);
    scv_asset_uridium_s00_38_load_raw(active_pattern_base + 38);
    scv_asset_uridium_s00_39_load_raw(active_pattern_base + 39);
    scv_asset_uridium_s00_40_load_raw(active_pattern_base + 40);
    scv_asset_uridium_s00_41_load_raw(active_pattern_base + 41);
    scv_asset_uridium_s00_42_load_raw(active_pattern_base + 42);
    scv_asset_uridium_s00_43_load_raw(active_pattern_base + 43);
    scv_asset_uridium_s00_44_load_raw(active_pattern_base + 44);
    scv_asset_uridium_s00_45_load_raw(active_pattern_base + 45);
    scv_asset_uridium_s00_46_load_raw(active_pattern_base + 46);
    scv_asset_uridium_s00_47_load_raw(active_pattern_base + 47);
    scv_asset_uridium_s00_48_load_raw(active_pattern_base + 48);
    scv_asset_uridium_s00_49_load_raw(active_pattern_base + 49);
    scv_asset_uridium_s00_50_load_raw(active_pattern_base + 50);
    scv_asset_uridium_s00_51_load_raw(active_pattern_base + 51);
    scv_asset_uridium_s00_52_load_raw(active_pattern_base + 52);
    scv_asset_uridium_s00_53_load_raw(active_pattern_base + 53);
    scv_asset_uridium_s00_54_load_raw(active_pattern_base + 54);
}

void load_screen_01(void) {
    scv_asset_uridium_s01_0_load_raw(active_pattern_base + 0);
    scv_asset_uridium_s01_1_load_raw(active_pattern_base + 1);
    scv_asset_uridium_s01_2_load_raw(active_pattern_base + 2);
    scv_asset_uridium_s01_3_load_raw(active_pattern_base + 3);
    scv_asset_uridium_s01_4_load_raw(active_pattern_base + 4);
    scv_asset_uridium_s01_5_load_raw(active_pattern_base + 5);
    scv_asset_uridium_s01_6_load_raw(active_pattern_base + 6);
    scv_asset_uridium_s01_7_load_raw(active_pattern_base + 7);
    scv_asset_uridium_s01_8_load_raw(active_pattern_base + 8);
    scv_asset_uridium_s01_9_load_raw(active_pattern_base + 9);
    scv_asset_uridium_s01_10_load_raw(active_pattern_base + 10);
    scv_asset_uridium_s01_11_load_raw(active_pattern_base + 11);
    scv_asset_uridium_s01_12_load_raw(active_pattern_base + 12);
    scv_asset_uridium_s01_13_load_raw(active_pattern_base + 13);
    scv_asset_uridium_s01_14_load_raw(active_pattern_base + 14);
    scv_asset_uridium_s01_15_load_raw(active_pattern_base + 15);
    scv_asset_uridium_s01_16_load_raw(active_pattern_base + 16);
    scv_asset_uridium_s01_17_load_raw(active_pattern_base + 17);
    scv_asset_uridium_s01_18_load_raw(active_pattern_base + 18);
    scv_asset_uridium_s01_19_load_raw(active_pattern_base + 19);
    scv_asset_uridium_s01_20_load_raw(active_pattern_base + 20);
    scv_asset_uridium_s01_21_load_raw(active_pattern_base + 21);
    scv_asset_uridium_s01_22_load_raw(active_pattern_base + 22);
    scv_asset_uridium_s01_23_load_raw(active_pattern_base + 23);
    scv_asset_uridium_s01_24_load_raw(active_pattern_base + 24);
    scv_asset_uridium_s01_25_load_raw(active_pattern_base + 25);
    scv_asset_uridium_s01_26_load_raw(active_pattern_base + 26);
    scv_asset_uridium_s01_27_load_raw(active_pattern_base + 27);
    scv_asset_uridium_s01_28_load_raw(active_pattern_base + 28);
    scv_asset_uridium_s01_29_load_raw(active_pattern_base + 29);
    scv_asset_uridium_s01_30_load_raw(active_pattern_base + 30);
    scv_asset_uridium_s01_31_load_raw(active_pattern_base + 31);
    scv_asset_uridium_s01_32_load_raw(active_pattern_base + 32);
    scv_asset_uridium_s01_33_load_raw(active_pattern_base + 33);
    scv_asset_uridium_s01_34_load_raw(active_pattern_base + 34);
    scv_asset_uridium_s01_35_load_raw(active_pattern_base + 35);
    scv_asset_uridium_s01_36_load_raw(active_pattern_base + 36);
    scv_asset_uridium_s01_37_load_raw(active_pattern_base + 37);
    scv_asset_uridium_s01_38_load_raw(active_pattern_base + 38);
    scv_asset_uridium_s01_39_load_raw(active_pattern_base + 39);
    scv_asset_uridium_s01_40_load_raw(active_pattern_base + 40);
    scv_asset_uridium_s01_41_load_raw(active_pattern_base + 41);
    scv_asset_uridium_s01_42_load_raw(active_pattern_base + 42);
    scv_asset_uridium_s01_43_load_raw(active_pattern_base + 43);
    scv_asset_uridium_s01_44_load_raw(active_pattern_base + 44);
    scv_asset_uridium_s01_45_load_raw(active_pattern_base + 45);
    scv_asset_uridium_s01_46_load_raw(active_pattern_base + 46);
    scv_asset_uridium_s01_47_load_raw(active_pattern_base + 47);
    scv_asset_uridium_s01_48_load_raw(active_pattern_base + 48);
    scv_asset_uridium_s01_49_load_raw(active_pattern_base + 49);
    scv_asset_uridium_s01_50_load_raw(active_pattern_base + 50);
    scv_asset_uridium_s01_51_load_raw(active_pattern_base + 51);
    scv_asset_uridium_s01_52_load_raw(active_pattern_base + 52);
    scv_asset_uridium_s01_53_load_raw(active_pattern_base + 53);
    scv_asset_uridium_s01_54_load_raw(active_pattern_base + 54);
    scv_asset_uridium_s01_55_load_raw(active_pattern_base + 55);
    scv_asset_uridium_s01_56_load_raw(active_pattern_base + 56);
    scv_asset_uridium_s01_57_load_raw(active_pattern_base + 57);
}

void load_screen_02(void) {
    scv_asset_uridium_s02_0_load_raw(active_pattern_base + 0);
    scv_asset_uridium_s02_1_load_raw(active_pattern_base + 1);
    scv_asset_uridium_s02_2_load_raw(active_pattern_base + 2);
    scv_asset_uridium_s02_3_load_raw(active_pattern_base + 3);
    scv_asset_uridium_s02_4_load_raw(active_pattern_base + 4);
    scv_asset_uridium_s02_5_load_raw(active_pattern_base + 5);
    scv_asset_uridium_s02_6_load_raw(active_pattern_base + 6);
    scv_asset_uridium_s02_7_load_raw(active_pattern_base + 7);
    scv_asset_uridium_s02_8_load_raw(active_pattern_base + 8);
    scv_asset_uridium_s02_9_load_raw(active_pattern_base + 9);
    scv_asset_uridium_s02_10_load_raw(active_pattern_base + 10);
    scv_asset_uridium_s02_11_load_raw(active_pattern_base + 11);
    scv_asset_uridium_s02_12_load_raw(active_pattern_base + 12);
    scv_asset_uridium_s02_13_load_raw(active_pattern_base + 13);
    scv_asset_uridium_s02_14_load_raw(active_pattern_base + 14);
    scv_asset_uridium_s02_15_load_raw(active_pattern_base + 15);
    scv_asset_uridium_s02_16_load_raw(active_pattern_base + 16);
    scv_asset_uridium_s02_17_load_raw(active_pattern_base + 17);
    scv_asset_uridium_s02_18_load_raw(active_pattern_base + 18);
    scv_asset_uridium_s02_19_load_raw(active_pattern_base + 19);
    scv_asset_uridium_s02_20_load_raw(active_pattern_base + 20);
    scv_asset_uridium_s02_21_load_raw(active_pattern_base + 21);
    scv_asset_uridium_s02_22_load_raw(active_pattern_base + 22);
    scv_asset_uridium_s02_23_load_raw(active_pattern_base + 23);
    scv_asset_uridium_s02_24_load_raw(active_pattern_base + 24);
    scv_asset_uridium_s02_25_load_raw(active_pattern_base + 25);
    scv_asset_uridium_s02_26_load_raw(active_pattern_base + 26);
    scv_asset_uridium_s02_27_load_raw(active_pattern_base + 27);
    scv_asset_uridium_s02_28_load_raw(active_pattern_base + 28);
    scv_asset_uridium_s02_29_load_raw(active_pattern_base + 29);
    scv_asset_uridium_s02_30_load_raw(active_pattern_base + 30);
    scv_asset_uridium_s02_31_load_raw(active_pattern_base + 31);
    scv_asset_uridium_s02_32_load_raw(active_pattern_base + 32);
    scv_asset_uridium_s02_33_load_raw(active_pattern_base + 33);
    scv_asset_uridium_s02_34_load_raw(active_pattern_base + 34);
    scv_asset_uridium_s02_35_load_raw(active_pattern_base + 35);
    scv_asset_uridium_s02_36_load_raw(active_pattern_base + 36);
    scv_asset_uridium_s02_37_load_raw(active_pattern_base + 37);
    scv_asset_uridium_s02_38_load_raw(active_pattern_base + 38);
    scv_asset_uridium_s02_39_load_raw(active_pattern_base + 39);
    scv_asset_uridium_s02_40_load_raw(active_pattern_base + 40);
    scv_asset_uridium_s02_41_load_raw(active_pattern_base + 41);
    scv_asset_uridium_s02_42_load_raw(active_pattern_base + 42);
    scv_asset_uridium_s02_43_load_raw(active_pattern_base + 43);
    scv_asset_uridium_s02_44_load_raw(active_pattern_base + 44);
    scv_asset_uridium_s02_45_load_raw(active_pattern_base + 45);
    scv_asset_uridium_s02_46_load_raw(active_pattern_base + 46);
    scv_asset_uridium_s02_47_load_raw(active_pattern_base + 47);
    scv_asset_uridium_s02_48_load_raw(active_pattern_base + 48);
    scv_asset_uridium_s02_49_load_raw(active_pattern_base + 49);
    scv_asset_uridium_s02_50_load_raw(active_pattern_base + 50);
    scv_asset_uridium_s02_51_load_raw(active_pattern_base + 51);
    scv_asset_uridium_s02_52_load_raw(active_pattern_base + 52);
    scv_asset_uridium_s02_53_load_raw(active_pattern_base + 53);
    scv_asset_uridium_s02_54_load_raw(active_pattern_base + 54);
    scv_asset_uridium_s02_55_load_raw(active_pattern_base + 55);
}

void load_screen_03(void) {
    scv_asset_uridium_s03_0_load_raw(active_pattern_base + 0);
    scv_asset_uridium_s03_1_load_raw(active_pattern_base + 1);
    scv_asset_uridium_s03_2_load_raw(active_pattern_base + 2);
    scv_asset_uridium_s03_3_load_raw(active_pattern_base + 3);
    scv_asset_uridium_s03_4_load_raw(active_pattern_base + 4);
    scv_asset_uridium_s03_5_load_raw(active_pattern_base + 5);
    scv_asset_uridium_s03_6_load_raw(active_pattern_base + 6);
    scv_asset_uridium_s03_7_load_raw(active_pattern_base + 7);
    scv_asset_uridium_s03_8_load_raw(active_pattern_base + 8);
    scv_asset_uridium_s03_9_load_raw(active_pattern_base + 9);
    scv_asset_uridium_s03_10_load_raw(active_pattern_base + 10);
    scv_asset_uridium_s03_11_load_raw(active_pattern_base + 11);
    scv_asset_uridium_s03_12_load_raw(active_pattern_base + 12);
    scv_asset_uridium_s03_13_load_raw(active_pattern_base + 13);
    scv_asset_uridium_s03_14_load_raw(active_pattern_base + 14);
    scv_asset_uridium_s03_15_load_raw(active_pattern_base + 15);
    scv_asset_uridium_s03_16_load_raw(active_pattern_base + 16);
    scv_asset_uridium_s03_17_load_raw(active_pattern_base + 17);
    scv_asset_uridium_s03_18_load_raw(active_pattern_base + 18);
    scv_asset_uridium_s03_19_load_raw(active_pattern_base + 19);
    scv_asset_uridium_s03_20_load_raw(active_pattern_base + 20);
    scv_asset_uridium_s03_21_load_raw(active_pattern_base + 21);
    scv_asset_uridium_s03_22_load_raw(active_pattern_base + 22);
    scv_asset_uridium_s03_23_load_raw(active_pattern_base + 23);
    scv_asset_uridium_s03_24_load_raw(active_pattern_base + 24);
    scv_asset_uridium_s03_25_load_raw(active_pattern_base + 25);
    scv_asset_uridium_s03_26_load_raw(active_pattern_base + 26);
    scv_asset_uridium_s03_27_load_raw(active_pattern_base + 27);
    scv_asset_uridium_s03_28_load_raw(active_pattern_base + 28);
    scv_asset_uridium_s03_29_load_raw(active_pattern_base + 29);
    scv_asset_uridium_s03_30_load_raw(active_pattern_base + 30);
    scv_asset_uridium_s03_31_load_raw(active_pattern_base + 31);
    scv_asset_uridium_s03_32_load_raw(active_pattern_base + 32);
    scv_asset_uridium_s03_33_load_raw(active_pattern_base + 33);
    scv_asset_uridium_s03_34_load_raw(active_pattern_base + 34);
    scv_asset_uridium_s03_35_load_raw(active_pattern_base + 35);
    scv_asset_uridium_s03_36_load_raw(active_pattern_base + 36);
    scv_asset_uridium_s03_37_load_raw(active_pattern_base + 37);
    scv_asset_uridium_s03_38_load_raw(active_pattern_base + 38);
    scv_asset_uridium_s03_39_load_raw(active_pattern_base + 39);
    scv_asset_uridium_s03_40_load_raw(active_pattern_base + 40);
    scv_asset_uridium_s03_41_load_raw(active_pattern_base + 41);
    scv_asset_uridium_s03_42_load_raw(active_pattern_base + 42);
    scv_asset_uridium_s03_43_load_raw(active_pattern_base + 43);
    scv_asset_uridium_s03_44_load_raw(active_pattern_base + 44);
    scv_asset_uridium_s03_45_load_raw(active_pattern_base + 45);
    scv_asset_uridium_s03_46_load_raw(active_pattern_base + 46);
    scv_asset_uridium_s03_47_load_raw(active_pattern_base + 47);
    scv_asset_uridium_s03_48_load_raw(active_pattern_base + 48);
    scv_asset_uridium_s03_49_load_raw(active_pattern_base + 49);
    scv_asset_uridium_s03_50_load_raw(active_pattern_base + 50);
    scv_asset_uridium_s03_51_load_raw(active_pattern_base + 51);
    scv_asset_uridium_s03_52_load_raw(active_pattern_base + 52);
    scv_asset_uridium_s03_53_load_raw(active_pattern_base + 53);
    scv_asset_uridium_s03_54_load_raw(active_pattern_base + 54);
    scv_asset_uridium_s03_55_load_raw(active_pattern_base + 55);
    scv_asset_uridium_s03_56_load_raw(active_pattern_base + 56);
    scv_asset_uridium_s03_57_load_raw(active_pattern_base + 57);
}

void draw_screen_00(void) {
    int i;
    i = 0;
    while (i < uridium_screen_00_sprite_count) {
        scv_set_hw_sprite_raw(active_sprite_base + i, uridium_screen_00_x[i] + active_x_offset, uridium_screen_00_y[i], uridium_screen_00_pattern[i] + active_pattern_base, uridium_screen_00_color[i]);
        i = i + 1;
    }
    draw_result = active_sprite_base + uridium_screen_00_sprite_count;
}

void draw_screen_01(void) {
    int i;
    i = 0;
    while (i < uridium_screen_01_sprite_count) {
        scv_set_hw_sprite_raw(active_sprite_base + i, uridium_screen_01_x[i] + active_x_offset, uridium_screen_01_y[i], uridium_screen_01_pattern[i] + active_pattern_base, uridium_screen_01_color[i]);
        i = i + 1;
    }
    draw_result = active_sprite_base + uridium_screen_01_sprite_count;
}

void draw_screen_02(void) {
    int i;
    i = 0;
    while (i < uridium_screen_02_sprite_count) {
        scv_set_hw_sprite_raw(active_sprite_base + i, uridium_screen_02_x[i] + active_x_offset, uridium_screen_02_y[i], uridium_screen_02_pattern[i] + active_pattern_base, uridium_screen_02_color[i]);
        i = i + 1;
    }
    draw_result = active_sprite_base + uridium_screen_02_sprite_count;
}

void draw_screen_03(void) {
    int i;
    i = 0;
    while (i < uridium_screen_03_sprite_count) {
        scv_set_hw_sprite_raw(active_sprite_base + i, uridium_screen_03_x[i] + active_x_offset, uridium_screen_03_y[i], uridium_screen_03_pattern[i] + active_pattern_base, uridium_screen_03_color[i]);
        i = i + 1;
    }
    draw_result = active_sprite_base + uridium_screen_03_sprite_count;
}

void load_screen_patterns(void) {
    if (dispatch_screen_id == 0) {
        load_screen_00();
        return;
    }
    else if (dispatch_screen_id == 1) {
        load_screen_01();
        return;
    }
    else if (dispatch_screen_id == 2) {
        load_screen_02();
        return;
    }
    else if (dispatch_screen_id == 3) {
        load_screen_03();
        return;
    }
}

void draw_screen(void) {
    if (dispatch_screen_id == 0) {
        draw_screen_00();
        return;
    }
    else if (dispatch_screen_id == 1) {
        draw_screen_01();
        return;
    }
    else if (dispatch_screen_id == 2) {
        draw_screen_02();
        return;
    }
    else if (dispatch_screen_id == 3) {
        draw_screen_03();
        return;
    }
    draw_result = active_sprite_base;
}

void advance_pair(void) {
    int tmp;
    current_screen = next_screen;
    next_screen = next_screen + 1;
    if (next_screen >= uridium_screen_count) {
        next_screen = 0;
    }
    tmp = current_pattern_base;
    current_pattern_base = next_pattern_base;
    next_pattern_base = tmp;
    dispatch_screen_id = next_screen;
    active_pattern_base = next_pattern_base;
    load_screen_patterns();
}

void draw_pair(void) {
    int sprite_end;
    dispatch_screen_id = current_screen;
    active_sprite_base = 0;
    active_pattern_base = current_pattern_base;
    active_x_offset = scroll_x;
    draw_screen();
    sprite_end = draw_result;

    dispatch_screen_id = next_screen;
    active_sprite_base = sprite_end;
    active_pattern_base = next_pattern_base;
    active_x_offset = scroll_x + 160;
    draw_screen();
    sprite_end = draw_result;

    while (sprite_end < 128) {
        scv_hide_hw_sprite(sprite_end);
        sprite_end = sprite_end + 1;
    }
}

int main(void) {
    scv_set_hw_sprite_mode(1);
    current_screen = 0;
    next_screen = 1;
    current_pattern_base = 0;
    next_pattern_base = 64;
    scroll_x = 0;
    frame_div = 0;

    dispatch_screen_id = current_screen;
    active_pattern_base = current_pattern_base;
    load_screen_patterns();
    dispatch_screen_id = next_screen;
    active_pattern_base = next_pattern_base;
    load_screen_patterns();
    draw_pair();

    while (1) {
        scv_wait_vblank();
        frame_div = frame_div + 1;
        if (frame_div >= 2) {
            frame_div = 0;
            scroll_x = scroll_x - 4;
            if (scroll_x == 96) {
                scroll_x = 0;
                advance_pair();
            }
            draw_pair();
        }
    }
}
