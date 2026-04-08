/*
 * scv_api.h -- Super Cassette Vision Hardware API
 * 
 * Johnny Blanchard (Tonsomo Entertainment / RE:Enthused / Roguegunners Productions)
 * This isn't a 'real' header per se, you couldn't use it in a real C program (plus theres no lib anyway)
 * It really exists to act like self documentation, technically the process could entirely exist without this
 *
 * Include this header in your C source and call these functions.
 * The c_to_l7801.py converter recognises them and emits real
 * uPD7801 assembly for each one (no stub / TODO needed).
 *
 * IMPORTANT: add these global variable declarations to exactly ONE
 * translation unit (your main .c file):
 *
 *   int scv_pad1_state;
 *   int scv_pad2_state;
 *   int scv_collision_result;
 *
 * The converter automatically emits SCV startup code (di, lxi sp,
 * calt 0x8C, VDC init) so your C main() can run without boilerplate.
 *
 * RAM layout (uPD7801 internal RAM, 0xFF80-0xFFFF, 128 bytes total):
 *   0xFF80-0xFF9F  software sprite shadow table (8 sprites x 4 bytes)
 *   0xFFA0-0xFFEF  user variables  (default --ram-base 0xFFA0)
 *   0xFFF0         stack pointer init; stack grows downward from here
 *
 * Software sprite shadow table layout (0xFF80-0xFF9F):
 *   sprite N (0-7): byte[N*4+0]=col, byte[N*4+1]=row,
 *                   byte[N*4+2]=tile, byte[N*4+3]=flags (1=active)
 * These are character-cell sprites drawn into text VRAM (0x3040+),
 * not the hardware sprite plane at 0x3200.
 *
 * Controller scan groups (active-low, 0 = pressed):
 *   scv_read_pad1() scans PA=0xFD  ->  stored in scv_pad1_state
 *   scv_read_pad2() scans PA=0xFE  ->  stored in scv_pad2_state
 *
 *   Verified bit map (both players share the two scan bytes):
 *
 *          | L         | U         | R         | D         | B1        | B2
 *   -------|-----------|-----------|-----------|-----------|-----------|----------
 *   P1     | pad2 0x01 | pad2 0x02 | pad1 0x02 | pad1 0x01 | pad2 0x04 | pad1 0x04
 *   P2     | pad2 0x08 | pad2 0x10 | pad1 0x10 | pad1 0x08 | pad2 0x20 | pad1 0x20
 */

#ifndef SCV_API_H
#define SCV_API_H

/* ----------------------------------------------------------------
 * Feature 1 -- Text output
 * Print ASCII character ch at character position (row, col).
 * row: 0-11;  col: 0-31
 *
 * scv_print_string(x, y, str) prints a zero-terminated string
 * starting at character coordinates (x, y), incrementing x by 1
 * for each byte until '\\0'.
 *
 * str can be:
 *   - a const/static const array identifier (ROM-backed)
 *   - a mutable RAM array (char buf[N])
 *   - a string literal (e.g., "hello")
 * ---------------------------------------------------------------- */
extern void scv_print_char(int row, int col, int ch);
extern void scv_print_string(int x, int y, char *str);

/* ----------------------------------------------------------------
 * Feature 1b -- Minimal C string helpers (header-free libc subset)
 *
 * strlen(str):
 *   - For const/static const arrays, the compiler folds to an
 *     immediate constant length (up to first '\\0').
 *   - For RAM arrays, emits a runtime byte scan to '\\0'.
 *
 * sprintf(dst, fmt, value):
 *   - dst must be a mutable RAM array identifier.
 *   - fmt must be a ROM or RAM zero-terminated array identifier.
 *   - Supported specifiers: %%d, %%u, %%%% (all other specifiers emit '?').
 *   - value is treated as unsigned 8-bit (0-255).
 *   - Returns number of bytes written (excluding trailing '\\0').
 * ---------------------------------------------------------------- */
extern int strlen(char *str);
extern int sprintf(char *dst, char *fmt, int value);

/* ----------------------------------------------------------------
 * Feature 2 -- Graphics tiles / background mapping
 * Background tiles are mapped to pattern range 0-63.
 * Effective background pattern = (tile_id & 0x3F).
 *
 * scv_draw_tile/scv_draw_bg_tile mask tile_id to 0..63.
 * scv_set_bg_scroll sets background scroll offsets (x wraps 0..31,
 * y wraps 0..11).
 * scv_draw_bg_tile_scrolled draws using those offsets.
 * ---------------------------------------------------------------- */
extern void scv_draw_tile(int row, int col, int tile_id);
extern void scv_draw_bg_tile(int row, int col, int tile_id);
extern void scv_set_bg_scroll(int scroll_x, int scroll_y);
extern void scv_draw_bg_tile_scrolled(int row, int col, int tile_id);

/* ----------------------------------------------------------------
 * Feature 3 -- Software sprites (up to 8, index 0-7)
 * Sprites occupy one character cell each.
 *
 * scv_set_sprite  -- place a new sprite; id overwrites any prior
 *                    entry at that slot.
 * scv_move_sprite -- erase old position, draw at new position.
 * scv_hide_sprite -- erase sprite from screen; marks slot inactive.
 * ---------------------------------------------------------------- */
extern void scv_set_sprite(int id, int col, int row, int tile_id);
extern void scv_move_sprite(int id, int col, int row);
extern void scv_hide_sprite(int id);

/* ----------------------------------------------------------------
 * Feature 3b -- Hardware sprites backed by imported PNG assets
 * PNG assets are imported with source directives handled by the
 * converter, for example:
 *   #pragma scv_asset sprite hero "assets/hero.png"
 *   #pragma scv_asset spritesheet enemies "assets/enemies.png" 16 16
 *
 * Each imported frame generates a loader function:
 *   scv_asset_<name>_load(pattern_slot)                for sprite
 *   scv_asset_<name>_<frame_index>_load(pattern_slot)  for sheet
 *
 * The loader copies a 16x16 1bpp frame into sprite pattern memory at
 * 0x2000 + (64 + pattern_slot) * 0x20. Then scv_set_hw_sprite() displays it
 * from the hardware sprite table at 0x3200.
 *
 * Hardware sprite pattern values are forced into range 64-127.
 * Effective sprite pattern = 0x40 | (pattern & 0x3F).
 * Pass pattern/base_pattern in logical range 0-63.
 *
 * Dedicated helpers let game logic update just one attribute without
 * rewriting the entire tuple each frame.
 * ---------------------------------------------------------------- */
extern void scv_set_hw_sprite(int id, int x, int y, int pattern, int color);
extern void scv_set_hw_sprite_raw(int id, int x, int y, int pattern, int color);
extern void scv_hide_hw_sprite(int id);
extern void scv_set_hw_sprite_pos(int id, int x, int y);
extern void scv_set_hw_sprite_pattern(int id, int pattern);
extern void scv_set_hw_sprite_colour(int id, int color);
extern void scv_set_hw_sprite_frame(int id, int base_pattern, int frame);
extern void scv_set_hw_sprite_anim(int id, int x, int y,
                                   int base_pattern, int frame, int color);
extern void scv_set_hw_sprite_mode(int use_64_sprite_mode);
extern void scv_set_vdc_regs(int r0, int r1, int r2, int r3);
extern void scv_move_hw_sprite_left(int id, int step, int min_x);
extern void scv_move_hw_sprite_right(int id, int step, int max_x);
extern void scv_move_hw_sprite_up(int id, int step, int min_y);
extern void scv_move_hw_sprite_down(int id, int step, int max_y);
extern int scv_get_hw_sprite_y(int id);

/* ----------------------------------------------------------------
 * Feature 4 -- Controller input
 * SCV pads are matrix-scanned in two groups. Call both read functions
 * each frame, then combine bits from scv_pad1_state/scv_pad2_state.
 * ---------------------------------------------------------------- */
extern void scv_read_pad1(void);
extern void scv_read_pad2(void);
extern int scv_read_input_scan(int pa_mask);

/* Output globals -- declare in one translation unit */
extern int scv_pad1_state;
extern int scv_pad2_state;

/* ----------------------------------------------------------------
 * Feature 5 -- Sound  (uPD1771C)
 * Sound data lives in cartridge ROM, declared via pragma:
 *
 *   #pragma scv_asset sound tone  my_tone  p0 p1 p2 p3
 *   #pragma scv_asset sound noise my_noise p0 p1 p2 p3 p4 p5 p6 p7 p8 p9
 *
 * tone  params: p0=voice p1=freq_lo p2=freq_hi p3=duration
 * noise params: p0..p8 envelope/freq bytes, p9=duration
 *
 * Each directive generates a zero-arg play function:
 *   scv_asset_my_tone_play()    -- plays tone from ROM
 *   scv_asset_my_noise_play()   -- plays noise from ROM
 *
 * Sound bytes are stored in cartridge ROM (not RAM).
 *
 * scv_stop_sound() explicitly silences the active voice.
 * ---------------------------------------------------------------- */
extern void scv_stop_sound(void);

/* ----------------------------------------------------------------
 * Feature 6 -- Collision detection (axis-aligned, 1-cell resolution)
 * Call scv_check_collision(), then read scv_collision_result.
 * Returns 1 if both sprites are at the same (col, row); 0 otherwise.
 * Treats inactive sprites (flags==0) as non-colliding.
 * ---------------------------------------------------------------- */
extern void scv_check_collision(int id_a, int id_b);
extern int scv_collision_result;

/* ----------------------------------------------------------------
 * Feature 7 -- VBlank synchronisation
 * Stalls until the next vertical blank interrupt fires (flag f2).
 * Call once per game loop iteration to cap the frame rate.
 * ---------------------------------------------------------------- */
extern void scv_wait_vblank(void);

#endif /* SCV_API_H */
