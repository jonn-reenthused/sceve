#include "scv_api.h"

/* Include this file directly from a game translation unit when only the
   lightweight screen helpers are needed and the scrolling ring runtime is not. */

void scv_screen_pipeline_prepare(char clear_patterns)
{
	scv_bios_clear_text_vram();
	if (clear_patterns != 0) {
		scv_bios_clear_pattern_vram();
	}
	scv_bios_clear_hw_sprites();
	scv_set_vdc_regs(0xF4, 0x00, 0x00, 0xF1);
}

void scv_screen_pipeline_hide_sprite_range(char first_id, char end_id)
{
	while (first_id < end_id) {
		scv_hide_hw_sprite(first_id);
		first_id = first_id + 1;
	}
}

void scv_screen_pipeline_print_u8_2(int x, int y, unsigned char value)
{
	unsigned char tens;

	tens = 0;
	while (value >= 10) {
		value = value - 10;
		tens = tens + 1;
	}
	scv_print_char(x, y, '0' + tens);
	scv_print_char(x + 1, y, '0' + value);
}