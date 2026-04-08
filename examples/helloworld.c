/*
 * SCV Hello World
 *
 * Writes "Hello!" to the first row of the SCV text plane (VRAM 0x3044+).
 *
 * The two extern helpers below must be provided as hand-written l7801 sections:
 *   scv_init        - runs the BIOS screen-clear (calt 0x8C) and VDC setup.
 *   vram_write_row0 - writes byte ch to row-0 VRAM at 8-bit column offset.
 *                     The high address base 0x30 is fixed in the asm stub;
 *                     offset is in range 0x44-0xFF (columns 0-187).
 *
 * The converter will emit stub sections for both with TODO markers.
 * Note: the converter supports 8-bit integer arguments only (0-255).
 */

void scv_init(void);
void vram_write_row0(int offset, int ch);

void main(void) {
    scv_init();

    vram_write_row0(0x44, 72);    /* col 0 -> H */
    vram_write_row0(0x45, 101);   /* col 1 -> e */
    vram_write_row0(0x46, 108);   /* col 2 -> l */
    vram_write_row0(0x47, 108);   /* col 3 -> l */
    vram_write_row0(0x48, 111);   /* col 4 -> o */
    vram_write_row0(0x49, 33);    /* col 5 -> ! */
}
