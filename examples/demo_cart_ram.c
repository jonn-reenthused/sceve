#include "../tools/scv_api.h"

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

#pragma scv_cart_profile flat32_ram4k

unsigned char scratch[4];

const unsigned char seed_bytes[4] = {
	1, 2, 3, 4
};

int main(void) {
	/* Run this via the generated softlist package; loose .bin launches do not expose cart RAM in MAME. */
	scv_print_string(0, 0, "CART RAM");

	scv_cart_ram_clear();
	scv_cart_ram_copy_to(0x00, 0x10, seed_bytes, 4);
	scratch[0] = scv_cart_ram_read(0x00, 0x10);
	scv_cart_ram_write(0x00, 0x11, 9);
	scv_cart_ram_copy_from(0x00, 0x10, scratch, 4);

	if (scratch[1] == 9) {
		scv_print_string(0, 1, "OK");
	} else {
		scv_print_string(0, 1, "BAD");
	}

	while (1) {
		scv_wait_vblank();
	}
}