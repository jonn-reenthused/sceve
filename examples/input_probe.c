#include "../tools/scv_api.h"

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

const char label_p1[] = "P1";
const char label_p2[] = "P2";
const char fmt_pad[] = "RAW=%u";
char line_p1[12];
char line_p2[12];

int main(void) {
    int title_len;

    scv_print_string(2, 2, label_p1);
    scv_print_string(2, 3, label_p2);
    title_len = strlen(label_p1);
    scv_print_char(2, 2 + title_len, ':');
    scv_print_char(3, 2 + title_len, ':');

    while (1) {
        scv_wait_vblank();
        scv_read_pad1();
        scv_read_pad2();

        if ((scv_pad2_state & 0x01) == 0) { scv_print_char(2, 6, 'L'); } else { scv_print_char(2, 6, '.'); }
        if ((scv_pad2_state & 0x02) == 0) { scv_print_char(2, 7, 'U'); } else { scv_print_char(2, 7, '.'); }
        if ((scv_pad1_state & 0x02) == 0) { scv_print_char(2, 8, 'R'); } else { scv_print_char(2, 8, '.'); }
        if ((scv_pad1_state & 0x01) == 0) { scv_print_char(2, 9, 'D'); } else { scv_print_char(2, 9, '.'); }
        if ((scv_pad2_state & 0x04) == 0) { scv_print_char(2, 10, '1'); } else { scv_print_char(2, 10, '.'); }
        if ((scv_pad1_state & 0x04) == 0) { scv_print_char(2, 11, '2'); } else { scv_print_char(2, 11, '.'); }

        if ((scv_pad2_state & 0x08) == 0) { scv_print_char(3, 6, 'L'); } else { scv_print_char(3, 6, '.'); }
        if ((scv_pad2_state & 0x10) == 0) { scv_print_char(3, 7, 'U'); } else { scv_print_char(3, 7, '.'); }
        if ((scv_pad1_state & 0x10) == 0) { scv_print_char(3, 8, 'R'); } else { scv_print_char(3, 8, '.'); }
        if ((scv_pad1_state & 0x08) == 0) { scv_print_char(3, 9, 'D'); } else { scv_print_char(3, 9, '.'); }
        if ((scv_pad2_state & 0x20) == 0) { scv_print_char(3, 10, '1'); } else { scv_print_char(3, 10, '.'); }
        if ((scv_pad1_state & 0x20) == 0) { scv_print_char(3, 11, '2'); } else { scv_print_char(3, 11, '.'); }

        sprintf(line_p1, fmt_pad, scv_pad1_state);
        sprintf(line_p2, fmt_pad, scv_pad2_state);
        scv_print_string(10, 2, line_p1);
        scv_print_string(10, 3, line_p2);
    }
}
