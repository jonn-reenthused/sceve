#include "../tools/scv_api.h"

#pragma scv_asset sound tone snd_tone 2 0x80 0xE0 0x1F
#pragma scv_asset sound noise snd_noise 0x20 0x10 0x08 0x04 0x02 0x01 0x04 0x08 0x10 0x20

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

const char label_p1_colon[] = "P1:";
const char label_p2_colon[] = "P2:";

int main(void) {
    int last_p1_btn;
    int last_p2_btn;
    int p1_btn;
    int p2_btn;

    last_p1_btn = 0;
    last_p2_btn = 0;

    scv_print_string(0, 0, label_p1_colon);
    scv_print_string(0, 1, label_p2_colon);

    while (1) {
        scv_wait_vblank();
        scv_read_pad1();
        scv_read_pad2();

        p1_btn = ((scv_pad1_state & 0x04) == 0);
        p2_btn = ((scv_pad2_state & 0x04) == 0);

        if (p1_btn == 1) {
            scv_print_char(0, 3, '1');
        } else {
            scv_print_char(0, 3, '0');
        }
        if (p2_btn == 1) {
            scv_print_char(1, 3, '1');
        } else {
            scv_print_char(1, 3, '0');
        }

        if (p1_btn == 1) {
            if (last_p1_btn == 0) {
                scv_asset_snd_tone_play();
            }
        }

        if (p2_btn == 1) {
            if (last_p2_btn == 0) {
                scv_asset_snd_noise_play();
            }
        }

        last_p1_btn = p1_btn;
        last_p2_btn = p2_btn;
    }
}
