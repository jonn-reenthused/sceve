#include "../tools/scv_api.h"

int scv_pad1_state;
int scv_pad2_state;
int scv_collision_result;

const char label_bits[] = "01234567";
const char label_j1[] = "J1:";
const char label_j2[] = "J2:";
const char label_keys[] = "NUMPAD RAW:";

const char fmt_j1[] = "RAW=%u";
const char fmt_j2[] = "RAW=%u";
const char fmt_k0[] = "K0=%u";
const char fmt_k1[] = "K1=%u";
const char fmt_k2[] = "K2=%u";
const char fmt_k3[] = "K3=%u";
const char fmt_k4[] = "K4=%u";
const char fmt_k5[] = "K5=%u";

char line_out[12];

int main(void) {
    int key0;
    int key1;
    int key2;
    int key3;
    int key4;
    int key5;

    scv_print_string(4, 0, label_bits);
    scv_print_string(0, 1, label_j1);
    scv_print_string(0, 2, label_j2);
    scv_print_string(0, 4, label_keys);

    while (1) {
        scv_wait_vblank();
        scv_read_pad1();
        scv_read_pad2();

        key0 = scv_read_input_scan(0xFB);
        key1 = scv_read_input_scan(0xF7);
        key2 = scv_read_input_scan(0xEF);
        key3 = scv_read_input_scan(0xDF);
        key4 = scv_read_input_scan(0xBF);
        key5 = scv_read_input_scan(0x7F);

        if ((scv_pad1_state & 0x01) == 0) { scv_print_char(1, 4, '0'); } else { scv_print_char(1, 4, '.'); }
        if ((scv_pad1_state & 0x02) == 0) { scv_print_char(1, 5, '1'); } else { scv_print_char(1, 5, '.'); }
        if ((scv_pad1_state & 0x04) == 0) { scv_print_char(1, 6, '2'); } else { scv_print_char(1, 6, '.'); }
        if ((scv_pad1_state & 0x08) == 0) { scv_print_char(1, 7, '3'); } else { scv_print_char(1, 7, '.'); }
        if ((scv_pad1_state & 0x10) == 0) { scv_print_char(1, 8, '4'); } else { scv_print_char(1, 8, '.'); }
        if ((scv_pad1_state & 0x20) == 0) { scv_print_char(1, 9, '5'); } else { scv_print_char(1, 9, '.'); }
        if ((scv_pad1_state & 0x40) == 0) { scv_print_char(1, 10, '6'); } else { scv_print_char(1, 10, '.'); }
        if ((scv_pad1_state & 0x80) == 0) { scv_print_char(1, 11, '7'); } else { scv_print_char(1, 11, '.'); }

        if ((scv_pad2_state & 0x01) == 0) { scv_print_char(2, 4, '0'); } else { scv_print_char(2, 4, '.'); }
        if ((scv_pad2_state & 0x02) == 0) { scv_print_char(2, 5, '1'); } else { scv_print_char(2, 5, '.'); }
        if ((scv_pad2_state & 0x04) == 0) { scv_print_char(2, 6, '2'); } else { scv_print_char(2, 6, '.'); }
        if ((scv_pad2_state & 0x08) == 0) { scv_print_char(2, 7, '3'); } else { scv_print_char(2, 7, '.'); }
        if ((scv_pad2_state & 0x10) == 0) { scv_print_char(2, 8, '4'); } else { scv_print_char(2, 8, '.'); }
        if ((scv_pad2_state & 0x20) == 0) { scv_print_char(2, 9, '5'); } else { scv_print_char(2, 9, '.'); }
        if ((scv_pad2_state & 0x40) == 0) { scv_print_char(2, 10, '6'); } else { scv_print_char(2, 10, '.'); }
        if ((scv_pad2_state & 0x80) == 0) { scv_print_char(2, 11, '7'); } else { scv_print_char(2, 11, '.'); }

        sprintf(line_out, fmt_j1, scv_pad1_state);
        scv_print_string(14, 1, line_out);
        sprintf(line_out, fmt_j2, scv_pad2_state);
        scv_print_string(14, 2, line_out);
        sprintf(line_out, fmt_k0, key0);
        scv_print_string(0, 5, line_out);
        sprintf(line_out, fmt_k1, key1);
        scv_print_string(0, 6, line_out);
        sprintf(line_out, fmt_k2, key2);
        scv_print_string(0, 7, line_out);
        sprintf(line_out, fmt_k3, key3);
        scv_print_string(0, 8, line_out);
        sprintf(line_out, fmt_k4, key4);
        scv_print_string(0, 9, line_out);
        sprintf(line_out, fmt_k5, key5);
        scv_print_string(0, 10, line_out);
    }
}
