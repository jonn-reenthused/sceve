#include "../tools/scv_api.h"

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

#pragma scv_cart_profile flat32_ram4k_battery

const unsigned char signature[3] = {
	0x41, 0x52, 0x47
};

int main(void) {
	/* Run this via the generated softlist package; loose .bin launches do not expose cart RAM in MAME. */
	scv_print_string(0, 0, "CALL ARGS");

	if (scv_cart_ram_read(0x00, 0x00) != 0x41 ||
		scv_cart_ram_read(0x00, 0x01) != 0x52 ||
		scv_cart_ram_read(0x00, 0x02) != 0x47) {
		scv_cart_ram_clear();
		scv_cart_ram_copy_to(0x00, 0x00, signature, 3);
		scv_cart_ram_write(0x00, 0x10, 5);
		scv_cart_ram_write(0x00, 0x11, 1);
	}

	scv_print_string(0, 2, "ARG:");
	/* Nested cart-RAM reads inside scv_print_char arguments used to clobber x/y slots. */
	scv_print_char(4, 2, '0' + (scv_cart_ram_read(0x00, 0x10) % 10));
	scv_print_char(6 + (scv_cart_ram_read(0x00, 0x11) % 2), 2, 'X');
	scv_print_string(0, 4, "ARG OK");

	while (1) {
		scv_wait_vblank();
	}
}