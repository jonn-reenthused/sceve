#include "scv_api.h"

/* Include this file directly from a game translation unit.
   The current converter only inlines user includes that end in .c. */

#include "scv_screen_helpers.c"

unsigned char scv_screen_pipeline_bg_column_buffer[16];
unsigned char scv_screen_pipeline_bg_first_sprite_id;
unsigned char scv_screen_pipeline_bg_visible_cols;
unsigned char scv_screen_pipeline_bg_resident_cols;
unsigned char scv_screen_pipeline_bg_visible_rows;
unsigned char scv_screen_pipeline_bg_origin_x;
unsigned char scv_screen_pipeline_bg_origin_y;
unsigned char scv_screen_pipeline_bg_column_head;
unsigned char scv_screen_pipeline_bg_pixel_phase;
unsigned char scv_screen_pipeline_bg_pixel_step;
unsigned char scv_screen_pipeline_bg_sprite_limit;

void scv_screen_pipeline_bg_ring_configure_window(char first_sprite_id,
	char visible_cols,
	char preload_cols,
	char visible_rows,
	char origin_x,
	char origin_y)
{
	unsigned char required_sprites;

	scv_screen_pipeline_bg_first_sprite_id = first_sprite_id;
	scv_screen_pipeline_bg_visible_cols = visible_cols;
	scv_screen_pipeline_bg_resident_cols = visible_cols + preload_cols;
	scv_screen_pipeline_bg_visible_rows = visible_rows;
	scv_screen_pipeline_bg_origin_x = origin_x;
	scv_screen_pipeline_bg_origin_y = origin_y;
	scv_screen_pipeline_bg_column_head = 0;
	scv_screen_pipeline_bg_pixel_phase = 0;
	scv_screen_pipeline_bg_pixel_step = 2;
	required_sprites = scv_screen_pipeline_bg_resident_cols * visible_rows;
	if (required_sprites > 64) {
		scv_screen_pipeline_bg_sprite_limit = 128;
	} else {
		scv_screen_pipeline_bg_sprite_limit = 64;
	}
}

void scv_screen_pipeline_bg_ring_configure_scroller(char first_sprite_id,
	char visible_cols,
	char visible_rows,
	char origin_x,
	char origin_y)
{
	scv_screen_pipeline_bg_ring_configure_window(
		first_sprite_id,
		visible_cols,
		1,
		visible_rows,
		origin_x,
		origin_y
	);
}

void scv_screen_pipeline_bg_ring_configure(char first_sprite_id,
	char visible_cols,
	char visible_rows,
	char origin_x,
	char origin_y)
{
	scv_screen_pipeline_bg_ring_configure_window(
		first_sprite_id,
		visible_cols,
		0,
		visible_rows,
		origin_x,
		origin_y
	);
}

void scv_screen_pipeline_bg_ring_apply_sprite_mode(void)
{
	if (scv_screen_pipeline_bg_sprite_limit > 64) {
		scv_set_hw_sprite_mode(0);
	} else {
		scv_set_hw_sprite_mode(1);
	}
}

unsigned char scv_screen_pipeline_bg_ring_hide_limit(void)
{
	return scv_screen_pipeline_bg_sprite_limit;
}

unsigned char scv_screen_pipeline_bg_ring_sprite_id(char column_slot, char row)
{
	return scv_screen_pipeline_bg_first_sprite_id + (column_slot * scv_screen_pipeline_bg_visible_rows) + row;
}

void scv_screen_pipeline_bg_ring_load_staged_column(char column_slot, char colour)
{
	unsigned char row;
	unsigned char sprite_id;
	unsigned char draw_x;
	unsigned char draw_y;

	row = 0;
	while (row < scv_screen_pipeline_bg_visible_rows) {
		sprite_id = scv_screen_pipeline_bg_ring_sprite_id(column_slot, row);
		draw_x = scv_screen_pipeline_bg_origin_x + (column_slot * 16);
		draw_y = scv_screen_pipeline_bg_origin_y + (row * 16);
		scv_set_hw_sprite_raw(sprite_id, draw_x, draw_y, scv_screen_pipeline_bg_column_buffer[row], colour);
		row = row + 1;
	}
}

void scv_screen_pipeline_bg_ring_stage_value(char row, char value)
{
	scv_screen_pipeline_bg_column_buffer[row] = value;
}

void scv_screen_pipeline_bg_ring_position(void)
{
	unsigned char visible_col;
	unsigned char column_slot;
	unsigned char effective_pixel_phase;
	unsigned char row;
	unsigned char draw_x;
	unsigned char draw_y;
	unsigned char sprite_id;

	effective_pixel_phase = scv_screen_pipeline_bg_pixel_phase & 0xFE;

	visible_col = 0;
	while (visible_col < scv_screen_pipeline_bg_resident_cols) {
		column_slot = scv_screen_pipeline_bg_column_head + visible_col;
		if (column_slot >= scv_screen_pipeline_bg_resident_cols) {
			column_slot = column_slot - scv_screen_pipeline_bg_resident_cols;
		}

		draw_x = scv_screen_pipeline_bg_origin_x + (visible_col * 16) - effective_pixel_phase;
		row = 0;
		while (row < scv_screen_pipeline_bg_visible_rows) {
			sprite_id = scv_screen_pipeline_bg_ring_sprite_id(column_slot, row);
			draw_y = scv_screen_pipeline_bg_origin_y + (row * 16);
			scv_set_hw_sprite_pos(sprite_id, draw_x, draw_y);
			row = row + 1;
		}

		visible_col = visible_col + 1;
	}
}

void scv_screen_pipeline_bg_ring_hide_to(char end_sprite_id)
{
	unsigned char used_sprite_count;

	used_sprite_count = scv_screen_pipeline_bg_first_sprite_id +
		(scv_screen_pipeline_bg_resident_cols * scv_screen_pipeline_bg_visible_rows);
	while (used_sprite_count < end_sprite_id) {
		scv_hide_hw_sprite(used_sprite_count);
		used_sprite_count = used_sprite_count + 1;
	}
}