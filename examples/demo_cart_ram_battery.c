#include "../tools/scv_api.h"

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

#pragma scv_cart_profile flat32_ram4k_battery

unsigned char record[4];

const unsigned char signature[3] = {
	0x42, 0x41, 0x54
};

const unsigned char record_seed[4] = {
	0x11, 0x22, 0x33, 0x44
};

int main(void) {
	unsigned char boots_lo;
	unsigned char boots_hi;

	scv_print_string(0, 0, "BATTERY");

	if (scv_cart_ram_read(0x00, 0x00) != 0x42 ||
		scv_cart_ram_read(0x00, 0x01) != 0x41 ||
		scv_cart_ram_read(0x00, 0x02) != 0x54) {
		scv_cart_ram_clear();
		scv_cart_ram_copy_to(0x00, 0x00, signature, 3);
		scv_cart_ram_copy_to(0x00, 0x20, record_seed, 4);
		scv_cart_ram_write16(0x00, 0x10, 1, 0);
		scv_print_string(0, 1, "FIRST BOOT");
	} else {
		boots_lo = scv_cart_ram_read16_lo(0x00, 0x10);
		boots_hi = scv_cart_ram_read16_hi(0x00, 0x10);
		boots_lo = boots_lo + 1;
		if (boots_lo == 0) {
			boots_hi = boots_hi + 1;
		}
		scv_cart_ram_write16(0x00, 0x10, boots_lo, boots_hi);
		scv_print_string(0, 1, "SEEN BEFORE");
	}

	boots_lo = scv_cart_ram_read16_lo(0x00, 0x10);
	boots_hi = scv_cart_ram_read16_hi(0x00, 0x10);
	scv_cart_ram_copy_from(0x00, 0x20, record, 4);

	scv_print_string(0, 2, "BOOTS: ");
	scv_print_char(7, 2, '0' + ((boots_lo / 10) % 10));
	scv_print_char(8, 2, '0' + (boots_lo % 10));

	if (record[0] == 0x11 && record[1] == 0x22 && record[2] == 0x33 && record[3] == 0x44) {
		scv_print_string(0, 3, "REC OK");
	} else {
		scv_print_string(0, 3, "REC BAD");
	}

	if (boots_hi != 0) {
		scv_print_string(0, 4, "HI!=0");
	}

	while (1) {
		scv_wait_vblank();
	}
}