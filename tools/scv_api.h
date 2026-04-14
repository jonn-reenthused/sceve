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
 * Hardware colour indices (0-15)
 * Use these with hardware sprite and tile colour parameters.
 * ---------------------------------------------------------------- */
enum ScvColor {
    SCV_BLACK		= 1,
    SCV_DKBLUE		= 2,
    SCV_PURPLE		= 3,
    SCV_GREEN		= 4,
    SCV_LTGREEN		= 5,
    SCV_CYAN		= 6,
    SCV_DKGREEN		= 7,
    SCV_RED			= 8,
    SCV_ORANGE		= 9,
    SCV_PINK		= 10,
    SCV_SALMON		= 11,
    SCV_YELLOW		= 12,
    SCV_DKYELLOW	= 13,
    SCV_GREY		= 14,
    SCV_WHITE		= 15
};

/* ----------------------------------------------------------------
 * Text output
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
extern void scv_print_char(int x, int y, int ch);
extern void scv_print_string(int x, int y, char *str);

/* ----------------------------------------------------------------
 * Minimal C string helpers (header-free libc subset)
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
 * Graphics tiles / background mapping
 * Background tiles are mapped to pattern range 0-63.
 * Effective background pattern = (tile_id & 0x3F).
 *
 * scv_draw_tile/scv_draw_bg_tile mask tile_id to 0..63.
 * scv_set_bg_scroll sets background scroll offsets (x wraps 0..31,
 * y wraps 0..11).
 * scv_draw_bg_tile_scrolled draws using those offsets.
 *
 * scv_load_bg_array(pattern_slot, src_array, pattern_count):
 *   Bulk-copy contiguous pattern bytes into the background-sprite
 *   pattern bank used by scv_set_hw_sprite_raw (VRAM base 0x2000).
 *   - pattern_slot: destination slot 0..63
 *   - src_array: ROM or RAM byte array identifier
 *   - pattern_count: number of 32-byte patterns to copy
 *   Total copied bytes = pattern_count * 32.
 * ---------------------------------------------------------------- */
extern void scv_draw_tile(int row, int col, int tile_id);
extern void scv_draw_bg_tile(int row, int col, int tile_id);
extern int scv_get_bg_tile(int row, int col);
extern void scv_set_bg_scroll(int scroll_x, int scroll_y);
extern void scv_load_bg_array(int pattern_slot, char *src_array, int pattern_count);
extern void scv_draw_bg_tile_scrolled(int row, int col, int tile_id);

/* Efficient incremental background scrolling (Sky Kid-inspired):
 * Instead of redrawing entire tilemap (32x12), only update edges.
 * For horizontal scroll: operate on one column of 12 tiles.
 * For vertical scroll: operate on one row of 32 tiles.
 * Performance: ~23 VRAM writes/frame vs 384 (14x faster).
 * Pass array of new tile IDs for the edge that scrolled in.
 */
extern void scv_scroll_bg_right(void);
extern void scv_scroll_bg_left(void);
extern void scv_scroll_bg_down(void);
extern void scv_scroll_bg_up(void);

/* ----------------------------------------------------------------
 * Software sprites (up to 8, index 0-7)
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
 * Hardware sprites backed by imported PNG assets
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
 * BIOS helper wrappers
 * These map directly to BIOS CALT entries discovered from BIOS/game
 * disassembly and provide stable call points from C.
 *
 * scv_bios_clear_text_vram()    -> CALT 0x86 (0x0A1B)
 * scv_bios_clear_pattern_vram() -> CALT 0x88 (0x0A4A)
 * scv_bios_clear_hw_sprites()   -> BIOS routine 0x0A28
 *                                  (CALT 0x87 equivalent; emitted as CALL
 *                                   because current l7801 rejects odd CALT)
 *
 * 16-bit helpers expose the BIOS ALU routines and return the high
 * result byte in A:
 *   add16_hi: BIOS CALT 0x9A (0x0D48)
 *   sub16_hi: BIOS CALT 0x9C (0x0D6B)
 * ---------------------------------------------------------------- */
extern void scv_bios_clear_text_vram(void);
extern void scv_bios_clear_pattern_vram(void);
extern void scv_bios_clear_hw_sprites(void);
extern int scv_bios_add16_hi(int de_hi, int de_lo, int hl_hi, int hl_lo);
extern int scv_bios_sub16_hi(int de_hi, int de_lo, int hl_hi, int hl_lo);

/* Compatibility aliases recognised by the converter. */
extern int scv_bios_add16(int de_hi, int de_lo, int hl_hi, int hl_lo);
extern int scv_bios_sub16(int de_hi, int de_lo, int hl_hi, int hl_lo);
extern int svc_bios_add16(int de_hi, int de_lo, int hl_hi, int hl_lo);
extern int svc_bios_sub16(int de_hi, int de_lo, int hl_hi, int hl_lo);
extern void svc_bios_clear_text_vram(void);
extern void svc_bios_clear_pattern_vram(void);
extern void svc_bios_clear_hw_sprites(void);

/* ----------------------------------------------------------------
 * Controller input
 * SCV pads are matrix-scanned in two groups. Call both read functions
 * each frame, then combine bits from scv_pad1_state/scv_pad2_state.
 *
 * Pad-state helpers return 1 when the named control is pressed, else 0.
 * They accept the already-read scan byte so callers do not need to know
 * the active-low bit mask:
 *   - pass scv_pad2_state for P1 left/up/fire1 and P2 left/up/fire1
 *   - pass scv_pad1_state for P1 right/down/fire2 and P2 right/down/fire2
 *
 * Keypad helpers provide a higher-level decoded view of the numeric pad:
 *   scv_read_keypad_number() returns 0 for no key, 1..9 for digits,
 *   10 for 0, 11 for CLEAR, and 12 for ENTER.
 *
 *   scv_read_keypad_char() returns 0 for no key, '0'..'9' for digits,
 *   'C' for CLEAR, and 'E' for ENTER.
 * ---------------------------------------------------------------- */
extern void scv_read_pad1(void);
extern void scv_read_pad2(void);
extern int scv_read_input_scan(int pa_mask);
extern int scv_is_p1_left_pressed(int pad_state);
extern int scv_is_p1_up_pressed(int pad_state);
extern int scv_is_p1_right_pressed(int pad_state);
extern int scv_is_p1_down_pressed(int pad_state);
extern int scv_is_p1_fire1_pressed(int pad_state);
extern int scv_is_p1_fire2_pressed(int pad_state);
extern int scv_is_p2_left_pressed(int pad_state);
extern int scv_is_p2_up_pressed(int pad_state);
extern int scv_is_p2_right_pressed(int pad_state);
extern int scv_is_p2_down_pressed(int pad_state);
extern int scv_is_p2_fire1_pressed(int pad_state);
extern int scv_is_p2_fire2_pressed(int pad_state);
extern int scv_read_keypad_number(void);
extern int scv_read_keypad_char(void);

/* Output globals -- declare in one translation unit */
extern int scv_pad1_state;
extern int scv_pad2_state;

/* ----------------------------------------------------------------
 * Sound  (uPD1771C)
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
 *
 * scv_play_tone_raw(p1, p2, p3) emits a direct 4-byte tone packet:
 *   0x02, p1, p2, p3
 * This is useful for reproducing game-native write patterns observed
 * in ROM traces without creating many sound assets.
 *
 * scv_play_tone_packet(pitch, param) is a sequencer-friendly wrapper
 * around the same packet format with p1 fixed to 0xA0.
 * If param is 0 it is clamped to 0x10 for safe playback.
 * ---------------------------------------------------------------- */
extern void scv_stop_sound(void);
extern void scv_play_tone_raw(int p1, int p2, int p3);
extern void scv_play_tone_packet(int pitch, int param);

/* ----------------------------------------------------------------
 * Collision detection (axis-aligned, 1-cell resolution)
 * Call scv_check_collision(), then read scv_collision_result.
 * Returns 1 if both sprites are at the same (col, row); 0 otherwise.
 * Treats inactive sprites (flags==0) as non-colliding.
 * ---------------------------------------------------------------- */
extern void scv_check_collision(int id_a, int id_b);
extern int scv_collision_result;

/* ----------------------------------------------------------------
 * uPD7801 Timer helpers
 *
 * scv_start_timer(count) loads TM0 with count, clears TM1,
 * and starts the timer (STM).
 *
 * scv_timer_expired() returns 1 when timer flag FT is set, else 0.
 * ---------------------------------------------------------------- */
extern void scv_start_timer(int count);
extern int scv_timer_expired(void);

/* ----------------------------------------------------------------
 * VBlank synchronisation
 * Stalls until the next vertical blank interrupt fires (flag f2).
 * Call once per game loop iteration to cap the frame rate.
 * ---------------------------------------------------------------- */
extern void scv_wait_vblank(void);

#endif /* SCV_API_H */
