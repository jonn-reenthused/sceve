#include "../tools/scv_api.h"

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

#pragma scv_cart_profile flat32_ram4k_battery

#pragma scv_cart_ram_data(0x00, 0x00) save_signature
unsigned char save_signature[3];

#pragma scv_cart_ram_data(0x00, 0x10) boot_count_lo
unsigned char boot_count_lo;

#pragma scv_cart_ram_data(0x00, 0x11) boot_count_hi
unsigned char boot_count_hi;

#pragma scv_cart_ram_data(0x00, 0x20) save_record
unsigned char save_record[4];

char line[12];

int main(void) {
	/* Run this via the generated softlist package; loose .bin launches do not expose cart RAM in MAME. */
	scv_print_string(0, 0, "PRAGMA RAM");

	if (save_signature[0] != 0x50 ||
		save_signature[1] != 0x52 ||
		save_signature[2] != 0x47) {
		save_signature[0] = 0x50;
		save_signature[1] = 0x52;
		save_signature[2] = 0x47;
		boot_count_lo = 1;
		boot_count_hi = 0;
		save_record[0] = 0x11;
		save_record[1] = 0x22;
		save_record[2] = 0x33;
		save_record[3] = 0x44;
		scv_print_string(0, 1, "FIRST BOOT");
	} else {
		boot_count_lo = boot_count_lo + 1;
		if (boot_count_lo == 0) {
			boot_count_hi = boot_count_hi + 1;
		}
		scv_print_string(0, 1, "SEEN BEFORE");
	}

	scv_print_string(0, 2, "BOOTS: ");
	scv_print_char(7, 2, '0' + ((boot_count_lo / 10) % 10));
	scv_print_char(8, 2, '0' + (boot_count_lo % 10));

	if (save_record[0] == 0x11 &&
		save_record[1] == 0x22 &&
		save_record[2] == 0x33 &&
		save_record[3] == 0x44) {
		scv_print_string(0, 3, "REC OK");
	} else {
		scv_print_string(0, 3, "REC BAD");
	}

	if (boot_count_hi != 0) {
		scv_print_string(0, 4, "HI!=0");
	}

	while (1) {
		scv_wait_vblank();
	}
}