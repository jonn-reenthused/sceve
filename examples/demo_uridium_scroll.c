#include "../tools/scv_api.h"
#include "../tools/scv_screen_pipeline.c"
#include "assets/uridium/uridium_part00_map.c"

#pragma scv_asset backgroundsheet uridiumtiles "assets/uridium/uridium_part00_tiles.png" 16 16
#pragma scv_asset sprite pilot "assets/uridium-ship.png"

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

const char demo_title[] = "URIDIUM MAP SCROLL";
const unsigned char WORLD_MAP_WIDTH = 100;
const unsigned char WORLD_MAP_HEIGHT = 5;
const unsigned char MAP_VIEW_TOP = 0;
const unsigned char VISIBLE_TILE_COLUMNS = 10;
const unsigned char VISIBLE_TILE_ROWS = 4;
const unsigned char BG_ORIGIN_X = 32;
const unsigned char BG_ORIGIN_Y = 80;
const unsigned char SCROLL_DELAY_FRAMES = 2;
const unsigned char PILOT_PATTERN_SLOT = 0;

unsigned char camera_tile_x;
unsigned char max_camera_tile_x;
unsigned char pilot_sprite_id;
unsigned char pilot_x;
unsigned char pilot_y;
unsigned char scroll_right;
unsigned char scroll_delay;

unsigned char visible_world_column(unsigned char visible_col) {
    return camera_tile_x + visible_col;
}

unsigned char column_buffer[5];

void load_column_into_slot(unsigned char column_slot, unsigned char world_col) {
    unsigned char sprite_id;
    unsigned char tile_id;
    unsigned char tile_colour;
    unsigned char row;

    scv_map_extract_column(
        column_buffer,
        uridium_part00_map,
        WORLD_MAP_WIDTH,
        world_col,
        MAP_VIEW_TOP,
        VISIBLE_TILE_ROWS
    );

    row = 0;
    while (row < VISIBLE_TILE_ROWS) {
        tile_id = column_buffer[row];
        tile_colour = SCV_CYAN;
        sprite_id = scv_screen_pipeline_bg_ring_sprite_id(column_slot, row);
        scv_set_hw_sprite_pattern(sprite_id, tile_id);
        scv_set_hw_sprite_colour(sprite_id, tile_colour);
        row = row + 1;
    }
}

void initialize_graphic_window(void) {
    unsigned char column_slot;

    column_slot = 0;
    while (column_slot < scv_screen_pipeline_bg_resident_cols) {
        load_column_into_slot(column_slot, visible_world_column(column_slot));
        column_slot = column_slot + 1;
    }

    scv_screen_pipeline_bg_ring_position();
}

void advance_graphic_window(void) {
    unsigned char entering_slot;
    unsigned char entering_world_col;

    if (scroll_delay > 0) {
        scroll_delay = scroll_delay - 1;
        return;
    }
    scroll_delay = SCROLL_DELAY_FRAMES;

    if (scroll_right != 0) {
        if (camera_tile_x >= max_camera_tile_x && scv_screen_pipeline_bg_pixel_phase >= 15) {
            scroll_right = 0;
        } else {
            scv_screen_pipeline_bg_pixel_phase = scv_screen_pipeline_bg_pixel_phase + scv_screen_pipeline_bg_pixel_step;
            if (scv_screen_pipeline_bg_pixel_phase >= 16) {
                scv_screen_pipeline_bg_pixel_phase = 0;
                camera_tile_x = camera_tile_x + 1;

                scv_screen_pipeline_bg_column_head = scv_screen_pipeline_bg_column_head + 1;
                if (scv_screen_pipeline_bg_column_head >= scv_screen_pipeline_bg_resident_cols) {
                    scv_screen_pipeline_bg_column_head = 0;
                }

                entering_slot = scv_screen_pipeline_bg_column_head + scv_screen_pipeline_bg_resident_cols - 1;
                if (entering_slot >= scv_screen_pipeline_bg_resident_cols) {
                    entering_slot = entering_slot - scv_screen_pipeline_bg_resident_cols;
                }

                entering_world_col = visible_world_column(scv_screen_pipeline_bg_resident_cols - 1);
                load_column_into_slot(entering_slot, entering_world_col);
            }
        }
    } else {
        if (camera_tile_x == 0 && scv_screen_pipeline_bg_pixel_phase == 0) {
            scroll_right = 1;
        } else if (scv_screen_pipeline_bg_pixel_phase == 0) {
            camera_tile_x = camera_tile_x - 1;

            if (scv_screen_pipeline_bg_column_head > 0) {
                scv_screen_pipeline_bg_column_head = scv_screen_pipeline_bg_column_head - 1;
            } else {
                scv_screen_pipeline_bg_column_head = scv_screen_pipeline_bg_resident_cols - 1;
            }

            entering_slot = scv_screen_pipeline_bg_column_head;
            entering_world_col = visible_world_column(0);
            load_column_into_slot(entering_slot, entering_world_col);
            scv_screen_pipeline_bg_pixel_phase = 16 - scv_screen_pipeline_bg_pixel_step;
        } else {
            scv_screen_pipeline_bg_pixel_phase = scv_screen_pipeline_bg_pixel_phase - scv_screen_pipeline_bg_pixel_step;
        }
    }

    scv_screen_pipeline_bg_ring_position();
}

void move_pilot(void) {
    scv_read_pad1();
    scv_read_pad2();

    if (scv_is_p1_left_pressed(scv_pad2_state)) {
        if (pilot_x > BG_ORIGIN_X) {
            pilot_x = pilot_x - 2;
        }
    }

    if (scv_is_p1_right_pressed(scv_pad1_state)) {
        if (pilot_x < 204) {
            pilot_x = pilot_x + 2;
        }
    }

    if (scv_is_p1_up_pressed(scv_pad2_state)) {
        if (pilot_y > BG_ORIGIN_Y) {
            pilot_y = pilot_y - 2;
        }
    }

    if (scv_is_p1_down_pressed(scv_pad1_state)) {
        if (pilot_y < (BG_ORIGIN_Y + (VISIBLE_TILE_ROWS * 16) - 16)) {
            pilot_y = pilot_y + 2;
        }
    }

    scv_set_hw_sprite(pilot_sprite_id, pilot_x, pilot_y, PILOT_PATTERN_SLOT, SCV_YELLOW);
}

int main(void) {
    scv_bios_clear_text_vram();
    scv_bios_clear_hw_sprites();
    scv_set_vdc_regs(0xF4, 0x00, 0x00, 0xF1);

    scv_print_string(0, 0, demo_title);
    scv_print_string(0, 1, "SEAMLESS 2PX");

    scv_asset_uridiumtiles_load_all(0);
	scv_asset_pilot_load(PILOT_PATTERN_SLOT);

    camera_tile_x = 0;
        pilot_x = BG_ORIGIN_X + 32;
        pilot_y = BG_ORIGIN_Y + 4;
    scroll_right = 1;
    scroll_delay = SCROLL_DELAY_FRAMES;

    scv_screen_pipeline_bg_ring_configure_scroller(0, VISIBLE_TILE_COLUMNS, VISIBLE_TILE_ROWS, BG_ORIGIN_X, BG_ORIGIN_Y);
    scv_screen_pipeline_bg_ring_apply_sprite_mode();
    max_camera_tile_x = WORLD_MAP_WIDTH - scv_screen_pipeline_bg_resident_cols;
        pilot_sprite_id = scv_screen_pipeline_bg_resident_cols * VISIBLE_TILE_ROWS;
    initialize_graphic_window();
    scv_screen_pipeline_bg_ring_hide_to(scv_screen_pipeline_bg_ring_hide_limit());

    while (1) {
        scv_wait_vblank();
        advance_graphic_window();
		move_pilot();
    }
}