#include "../tools/scv_api.h"

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

const char label_rng[] = "RND 3-9:";

int main(void) {
	int value;

	scv_random_seed(0x2D);
	scv_print_string(0, 0, label_rng);
	scv_print_char(9, 0, '?');

	while (1) {
		scv_wait_vblank();
		value = scv_random_range(3, 9);
		scv_print_char(9, 0, '0' + value);
	}
}