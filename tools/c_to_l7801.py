#!/usr/bin/env python3
"""Convert a restricted subset of C into l7801/l65 source (.l7801).

Johnny Blanchard (Tonsomo Entertainment/RE:Enthused/Roguegunners Productions)

The output targets BlockoS l65 tooling and is intended as a conservative
starting point for SCV development.

As a note, when I started making this, l65 was still in active development, i've just realised that the last update was 2 years ago.
It should still be fine
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from png_to_scv import PngAssetError, ScvPngFrame, load_png_asset_frames

try:
    from pycparser import c_ast, c_parser
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency: pycparser. Install with: pip install pycparser"
    ) from exc


class ConversionError(RuntimeError):
    pass


@dataclass
class FunctionContext:
    name: str
    end_label: str
    param_symbols: Dict[str, str]


@dataclass
class AssetFunction:
    function_name: str
    frame: ScvPngFrame
    pattern_mode: str = "sprite"


@dataclass
class SoundAsset:
    """ROM-resident sound data for tone or noise commands."""
    kind: str          # 'tone' or 'noise'
    name: str
    data_label: str    # assembler label for the dc.b data
    play_fn: str       # generated play function name
    rom_bytes: List[int]  # bytes to store in ROM (cmd byte + params)


@dataclass
class AssetDirective:
    kind: str
    name: str
    source_path: Path
    frames: List[ScvPngFrame]


@dataclass
class RomDataBlock:
    alias_name: str
    label: str
    data: List[int]


class L7801L65Emitter:
    STACK_INIT = 0xFFF0
    DEFAULT_RAM_BASE = 0xFFA0
    RECLAIMED_RAM_BASE = 0xFF80
    CART_PROFILES: Dict[str, Dict[str, object]] = {
        "flat32": {"bank_count": 1, "layout": "flat", "supports_bank_switch": False, "hook_backend": "flat32-fixed"},
        "banked64": {"bank_count": 2, "layout": "monolithic", "supports_bank_switch": True, "hook_backend": "banked64-shadow-v1"},
        "banked128": {"bank_count": 4, "layout": "monolithic", "supports_bank_switch": True, "hook_backend": "banked128-shadow-v1"},
        "split32_8": {"bank_count": 2, "layout": "split", "supports_bank_switch": True, "hook_backend": "split32_8-shadow-v1"},
        "split32_32": {"bank_count": 2, "layout": "split", "supports_bank_switch": True, "hook_backend": "split32_32-shadow-v1"},
    }
    CART_BANK_SIZES: Dict[str, List[int]] = {
        "flat32": [0x8000],
        "banked64": [0x8000, 0x8000],
        "banked128": [0x8000, 0x8000, 0x8000, 0x8000],
        "split32_8": [0x8000, 0x2000],
        "split32_32": [0x8000, 0x8000],
    }
    SOFTWARE_SPRITE_APIS: Set[str] = {
        "scv_set_sprite",
        "scv_move_sprite",
        "scv_hide_sprite",
    }

    # Keep these APIs on dedicated arg slots to avoid clobbering during nested/inline flows.
    NON_SHARED_API_ARG_FUNCTIONS: Set[str] = {
        "sprintf",
        "strlen",
    }

    API_ALIASES: Dict[str, str] = {
        "scv_bios_add16": "scv_bios_add16_hi",
        "svc_bios_add16": "scv_bios_add16_hi",
        "svc_bios_sub16": "scv_bios_sub16_hi",
        "svc_bios_clear_text_vram": "scv_bios_clear_text_vram",
        "svc_bios_clear_pattern_vram": "scv_bios_clear_pattern_vram",
        "svc_bios_clear_hw_sprites": "scv_bios_clear_hw_sprites",
        "scv_load_bg_pattern_array": "scv_load_bg_sprite_array",
    }

    SCV_API_PARAMS: Dict[str, List[str]] = {
        "strlen": ["str"],
        "sprintf": ["dst", "fmt", "value"],
        "scv_random_range": ["min_value", "max_value"],
        "scv_cart_restore_bank": [],
        "scv_print_char": ["x", "y", "ch"],
        "scv_print_string": ["x", "y"],
        "scv_get_bg_tile": ["row", "col"],
        "scv_set_bg_scroll": ["scroll_x", "scroll_y"],
        "scv_vram_copy": ["addr_hi", "addr_lo", "src_array", "byte_count"],
        "scv_load_bg_array": ["pattern_slot", "src_array", "pattern_count"],
        "scv_load_bg_pattern_array": ["pattern_slot", "src_array", "pattern_count"],
        "scv_load_bg_sprite_array": ["pattern_slot", "src_array", "pattern_count"],
        "scv_draw_bg_tile_scrolled": ["row", "col", "tile_id"],
        "scv_scroll_bg_right": [],
        "scv_scroll_bg_left": [],
        "scv_patch_bg_column_right": ["row_start", "row_count", "src_array"],
        "scv_patch_bg_column_left": ["row_start", "row_count", "src_array"],
        "scv_patch_bg_row_top": ["col_start", "col_count", "src_array"],
        "scv_patch_bg_row_bottom": ["col_start", "col_count", "src_array"],
        "scv_map_extract_column": ["dst_array", "src_map", "map_width", "map_x", "map_y", "count"],
        "scv_map_extract_row": ["dst_array", "src_map", "map_width", "map_x", "map_y", "count"],
        "scv_set_sprite": ["id", "col", "row", "tile_id"],
        "scv_move_sprite": ["id", "col", "row"],
        "scv_hide_sprite": ["id"],
        "scv_set_hw_sprite": ["id", "x", "y", "pattern", "colour"],
        "scv_set_hw_sprite_raw": ["id", "x", "y", "pattern", "colour"],
        "scv_hide_hw_sprite": ["id"],
        "scv_set_hw_sprite_pos": ["id", "x", "y"],
        "scv_set_hw_sprite_pattern": ["id", "pattern"],
        "scv_set_hw_sprite_colour": ["id", "colour"],
        "scv_set_hw_sprite_frame": ["id", "base_pattern", "frame"],
        "scv_set_hw_sprite_anim": ["id", "x", "y", "base_pattern", "frame", "colour"],
        "scv_set_hw_sprite_mode": ["use_64_sprite_mode"],
        "scv_move_hw_sprite_left": ["id", "step", "min_x"],
        "scv_move_hw_sprite_right": ["id", "step", "max_x"],
        "scv_move_hw_sprite_up": ["id", "step", "min_y"],
        "scv_move_hw_sprite_down": ["id", "step", "max_y"],
        "scv_get_hw_sprite_y": ["id"],
        "scv_set_vdc_regs": ["r0", "r1", "r2", "r3"],
        "scv_bios_clear_text_vram": [],
        "scv_bios_clear_pattern_vram": [],
        "scv_bios_clear_hw_sprites": [],
        "scv_bios_add16_hi": ["de_hi", "de_lo", "hl_hi", "hl_lo"],
        "scv_bios_sub16_hi": ["de_hi", "de_lo", "hl_hi", "hl_lo"],
        "scv_read_pad1": [],
        "scv_read_pad2": [],
        "scv_read_input_scan": ["pa_mask"],
        "scv_read_keypad_number": [],
        "scv_read_keypad_char": [],
        "scv_stop_sound": [],
        "scv_play_tone_raw": ["p1", "p2", "p3"],
        "scv_play_tone_packet": ["pitch", "param"],
        "scv_check_collision": ["id_a", "id_b"],
        "scv_start_timer": ["count"],
        "scv_timer_expired": [],
        "scv_wait_vblank": [],
    }

    PAD_BOOL_HELPERS: Dict[str, int] = {
        "scv_is_p1_left_pressed": 0x01,
        "scv_is_p1_up_pressed": 0x02,
        "scv_is_p1_fire1_pressed": 0x04,
        "scv_is_p1_right_pressed": 0x02,
        "scv_is_p1_down_pressed": 0x01,
        "scv_is_p1_fire2_pressed": 0x04,
        "scv_is_p2_left_pressed": 0x08,
        "scv_is_p2_up_pressed": 0x10,
        "scv_is_p2_fire1_pressed": 0x20,
        "scv_is_p2_right_pressed": 0x10,
        "scv_is_p2_down_pressed": 0x08,
        "scv_is_p2_fire2_pressed": 0x20,
    }

    SCV_API_IMPLS: Dict[str, List[str]] = {
        "strlen": [
            "    mvi b,0x00",
            "@{fn}_loop",
            "    ldax (de)",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_continue_strlen",
            "    mov a,b",
            "    ret",
            "@{fn}_continue_strlen",
            "    inx de",
            "    mov a,b",
            "    adi a,0x01",
            "    mov b,a",
            "    jmp {fn}_loop",
        ],
        "sprintf": [
            "    mvi a,0x00",
            "    mov (sprintf__tmp_count),a",
            "@{fn}_loop",
            "    ldaxi (hl)",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_loop_continue",
            "    mvi a,0x00",
            "    stax (de)",
            "    mov a,(sprintf__tmp_count)",
            "    ret",
            "@{fn}_loop_continue",
            "    eqi a,0x25",
            "    skz",
            "    jmp {fn}_not_percent",
            "    jmp {fn}_handle_percent",
            "@{fn}_not_percent",
            "    ldaxi (hl)",
            "    stax (de)",
            "    inx de",
            "    mov a,(sprintf__tmp_count)",
            "    adi a,0x01",
            "    mov (sprintf__tmp_count),a",
            "    jmp {fn}_loop",
            "@{fn}_handle_percent",
            "    ldaxi (hl)",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_check_percent_code",
            "    mvi a,0x00",
            "    stax (de)",
            "    mov a,(sprintf__tmp_count)",
            "    ret",
            "@{fn}_check_percent_code",
            "    eqi a,0x25",
            "    skz",
            "    jmp {fn}_check_format_code",
            "    mvi a,0x25",
            "    stax (de)",
            "    inx de",
            "    mov a,(sprintf__tmp_count)",
            "    adi a,0x01",
            "    mov (sprintf__tmp_count),a",
            "    inx hl",
            "    jmp {fn}_loop",
            "@{fn}_check_format_code",
            "    eqi a,0x64",
            "    skz",
            "    jmp {fn}_check_unsigned_fmt",
            "    jmp {fn}_emit_decimal",
            "@{fn}_check_unsigned_fmt",
            "    eqi a,0x75",
            "    skz",
            "    jmp {fn}_unknown_format",
            "    jmp {fn}_emit_decimal",
            "@{fn}_unknown_format",
            "    mvi a,0x3F",
            "    stax (de)",
            "    inx de",
            "    mov a,(sprintf__tmp_count)",
            "    adi a,0x01",
            "    mov (sprintf__tmp_count),a",
            "    jmp {fn}_loop",
            "@{fn}_emit_decimal",
            "    mov a,({fn}__arg_value)",
            "    mov (sprintf__tmp_rem),a",
            "    mvi a,0x00",
            "    mov (sprintf__tmp_hundreds),a",
            "    mov (sprintf__tmp_tens),a",
            "@{fn}_hundreds_loop",
            "    mov a,(sprintf__tmp_rem)",
            "    mvi b,0x64",
            "    sub a,b",
            "    skc",
            "    jmp {fn}_hundreds_apply",
            "    jmp {fn}_hundreds_done",
            "@{fn}_hundreds_apply",
            "    mov (sprintf__tmp_rem),a",
            "    mov a,(sprintf__tmp_hundreds)",
            "    adi a,0x01",
            "    mov (sprintf__tmp_hundreds),a",
            "    jmp {fn}_hundreds_loop",
            "@{fn}_hundreds_done",
            "@{fn}_tens_loop",
            "    mov a,(sprintf__tmp_rem)",
            "    mvi b,0x0A",
            "    sub a,b",
            "    skc",
            "    jmp {fn}_tens_apply",
            "    jmp {fn}_tens_done",
            "@{fn}_tens_apply",
            "    mov (sprintf__tmp_rem),a",
            "    mov a,(sprintf__tmp_tens)",
            "    adi a,0x01",
            "    mov (sprintf__tmp_tens),a",
            "    jmp {fn}_tens_loop",
            "@{fn}_tens_done",
            "    mov a,(sprintf__tmp_hundreds)",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_skip_hundreds",
            "    mov a,(sprintf__tmp_hundreds)",
            "    adi a,0x30",
            "    stax (de)",
            "    inx de",
            "    mov a,(sprintf__tmp_count)",
            "    adi a,0x01",
            "    mov (sprintf__tmp_count),a",
            "@{fn}_skip_hundreds",
            "    mov a,(sprintf__tmp_hundreds)",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_emit_tens_check",
            "    mov a,(sprintf__tmp_tens)",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_skip_tens",
            "@{fn}_emit_tens_check",
            "    mov a,(sprintf__tmp_tens)",
            "    adi a,0x30",
            "    stax (de)",
            "    inx de",
            "    mov a,(sprintf__tmp_count)",
            "    adi a,0x01",
            "    mov (sprintf__tmp_count),a",
            "@{fn}_skip_tens",
            "    mov a,(sprintf__tmp_rem)",
            "    adi a,0x30",
            "    stax (de)",
            "    inx de",
            "    mov a,(sprintf__tmp_count)",
            "    adi a,0x01",
            "    mov (sprintf__tmp_count),a",
            "    jmp {fn}_loop",
        ],
        "scv_cart_select_bank": [
            "    mov a,(scv_cart__current_bank)",
            "    mov (scv_cart__saved_bank),a",
            "    mov a,({fn}__arg_bank_id)",
            "    mov (scv_cart__current_bank),a",
            "    ret",
        ],
        "scv_cart_restore_bank": [
            "    mov a,(scv_cart__saved_bank)",
            "    mov (scv_cart__current_bank),a",
            "    ret",
        ],
        "scv_random_seed": [
            "    mov a,({fn}__arg_seed)",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_store_seed",
            "    mvi a,0xA5",
            "@{fn}_store_seed",
            "    mov (scv_random__state),a",
            "    ret",
        ],
        "scv_random_u8": [
            "    mov a,(scv_random__state)",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_seeded",
            "    mvi a,0xA5",
            "@{fn}_seeded",
            "    mov b,a",
            "    add a,a",
            "    add a,a",
            "    add a,b",
            "    adi a,0x01",
            "    mov (scv_random__state),a",
            "    ret",
        ],
        "scv_random_range": [
            "    mov a,({fn}__arg_min_value)",
            "    mov b,a",
            "    mov a,({fn}__arg_max_value)",
            "    sub a,b",
            "    skc",
            "    jmp {fn}_check_full_range",
            "    mov a,b",
            "    ret",
            "@{fn}_check_full_range",
            "    adi a,0x01",
            "    mov c,a",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_have_span",
            "    call fn_scv_random_u8",
            "    ret",
            "@{fn}_have_span",
            "    call fn_scv_random_u8",
            "@{fn}_reduce_loop",
            "    sub a,c",
            "    skc",
            "    jmp {fn}_reduce_loop",
            "    add a,c",
            "    mov b,a",
            "    mov a,({fn}__arg_min_value)",
            "    add a,b",
            "    ret",
        ],
        "scv_print_char": [
            "    mvi h,0x30",
            "    mvi l,0x40",
            "    mov b,({fn}__arg_y)",
            "@{fn}_row_loop",
            "    mov a,b",
            "    nei a,0",
            "    jr {fn}_col_step",
            "    adi l,0x20",
            "    aci h,0",
            "    dcr b",
            "    jre {fn}_row_loop",
            "@{fn}_col_step",
            "    mov a,({fn}__arg_x)",
            "    adi a,0x03",
            "    add a,l",
            "    mov l,a",
            "    aci h,0",
            "    mov a,({fn}__arg_ch)",
            "    stax (hl)",
            "    ret",
        ],
        "scv_print_string": [
            "    mvi h,0x30",
            "    mvi l,0x40",
            "    mov b,({fn}__arg_y)",
            "@{fn}_row_loop",
            "    mov a,b",
            "    nei a,0",
            "    jr {fn}_col_step",
            "    adi l,0x20",
            "    aci h,0",
            "    dcr b",
            "    jre {fn}_row_loop",
            "@{fn}_col_step",
            "    mov a,({fn}__arg_x)",
            "    adi a,0x03",
            "    add a,l",
            "    mov l,a",
            "    aci h,0",
            "@{fn}_loop",
            "    ldax (de)",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_store_char",
            "    ret",
            "@{fn}_store_char",
            "    stax (hl)",
            "    inx de",
            "    inx hl",
            "    jmp {fn}_loop",
        ],
        "scv_draw_tile": [
            "    mvi h,0x30",
            "    mvi l,0x40",
            "    mov b,({fn}__arg_row)",
            "@{fn}_row_loop",
            "    mov a,b",
            "    nei a,0",
            "    jr {fn}_col_step",
            "    adi l,0x20",
            "    aci h,0",
            "    dcr b",
            "    jre {fn}_row_loop",
            "@{fn}_col_step",
            "    mov a,({fn}__arg_col)",
            "    adi a,0x03",
            "    add a,l",
            "    mov l,a",
            "    aci h,0",
            "    mov a,({fn}__arg_tile_id)",
            "    ani a,0x3F",
            "    stax (hl)",
            "    ret",
        ],
        "scv_draw_bg_tile": [
            "    mvi h,0x30",
            "    mvi l,0x40",
            "    mov b,({fn}__arg_row)",
            "@{fn}_row_loop",
            "    mov a,b",
            "    nei a,0",
            "    jr {fn}_col_step",
            "    adi l,0x20",
            "    aci h,0",
            "    dcr b",
            "    jre {fn}_row_loop",
            "@{fn}_col_step",
            "    mov a,({fn}__arg_col)",
            "    adi a,0x03",
            "    add a,l",
            "    mov l,a",
            "    aci h,0",
            "    mov a,({fn}__arg_tile_id)",
            "    ani a,0x3F",
            "    stax (hl)",
            "    ret",
        ],
        "scv_get_bg_tile": [
            "    mvi h,0x30",
            "    mvi l,0x40",
            "    mov b,({fn}__arg_row)",
            "@{fn}_row_loop",
            "    mov a,b",
            "    nei a,0",
            "    jr {fn}_col_step",
            "    adi l,0x20",
            "    aci h,0",
            "    dcr b",
            "    jre {fn}_row_loop",
            "@{fn}_col_step",
            "    mov a,({fn}__arg_col)",
            "    adi a,0x03",
            "    add a,l",
            "    mov l,a",
            "    aci h,0",
            "    ldax (hl)",
            "    ani a,0x3F",
            "    ret",
        ],
        "scv_set_bg_scroll": [
            "    mov a,({fn}__arg_scroll_x)",
            "    ani a,0x1F",
            "    mov (scv_bg_scroll_x),a",
            "    mov a,({fn}__arg_scroll_y)",
            "    mov c,a",
            "@{fn}_wrap_y",
            "    mov a,c",
            "    mvi b,0x0C",
            "    sub a,b",
            "    skc",
            "    jmp {fn}_wrap_y_apply",
            "    jmp {fn}_wrap_y_done",
            "@{fn}_wrap_y_apply",
            "    mov c,a",
            "    jmp {fn}_wrap_y",
            "@{fn}_wrap_y_done",
            "    mov a,c",
            "    mov (scv_bg_scroll_y),a",
            "    ret",
        ],
        "scv_vram_copy": [
            "    mov a,({fn}__arg_addr_hi)",
            "    mov h,a",
            "    mov a,({fn}__arg_addr_lo)",
            "    mov l,a",
            "    mov a,({fn}__arg_byte_count)",
            "    mov c,a",
            "@{fn}_outer_loop",
            "    mov a,c",
            "    nei a,0",
            "    jr {fn}_outer_done",
            "    ldax (de)",
            "    stax (hl)",
            "    inx de",
            "    inx hl",
            "    mov a,c",
            "    adi a,0xFF",
            "    mov c,a",
            "    jmp {fn}_outer_loop",
            "@{fn}_outer_done",
            "    ret",
        ],
        "scv_load_bg_array": [
            "    mvi h,0x20",
            "    mvi l,0x00",
            "    mov a,({fn}__arg_pattern_slot)",
            "    ani a,0x3F",
            "    mov b,a",
            "@{fn}_slot_loop",
            "    mov a,b",
            "    nei a,0",
            "    jr {fn}_slot_done",
            "    mvi a,0x10",
            "    add a,l",
            "    mov l,a",
            "    aci h,0",
            "    dcr b",
            "    jre {fn}_slot_loop",
            "@{fn}_slot_done",
            "    mov a,({fn}__arg_pattern_count)",
            "    mov c,a",
            "@{fn}_outer_loop",
            "    mov a,c",
            "    nei a,0",
            "    jr {fn}_outer_done",
            "    mvi b,0x10",
            "@{fn}_copy_loop",
            "    ldax (de)",
            "    stax (hl)",
            "    inx de",
            "    inx hl",
            "    dcr b",
            "    jre {fn}_copy_loop",
            "    mov a,c",
            "    adi a,0xFF",
            "    mov c,a",
            "    jmp {fn}_outer_loop",
            "@{fn}_outer_done",
            "    ret",
        ],
        "scv_load_bg_sprite_array": [
            "    mvi h,0x20",
            "    mvi l,0x00",
            "    mov a,({fn}__arg_pattern_slot)",
            "    ani a,0x3F",
            "    mov b,a",
            "@{fn}_slot_loop",
            "    mov a,b",
            "    nei a,0",
            "    jr {fn}_slot_done",
            "    mvi a,0x20",
            "    add a,l",
            "    mov l,a",
            "    aci h,0",
            "    dcr b",
            "    jre {fn}_slot_loop",
            "@{fn}_slot_done",
            "    mov a,({fn}__arg_pattern_count)",
            "    mov c,a",
            "@{fn}_outer_loop",
            "    mov a,c",
            "    nei a,0",
            "    jr {fn}_outer_done",
            "    mvi b,0x20",
            "@{fn}_copy_loop",
            "    ldax (de)",
            "    stax (hl)",
            "    inx de",
            "    inx hl",
            "    dcr b",
            "    jre {fn}_copy_loop",
            "    mov a,c",
            "    adi a,0xFF",
            "    mov c,a",
            "    jmp {fn}_outer_loop",
            "@{fn}_outer_done",
            "    ret",
        ],
        "scv_draw_bg_tile_scrolled": [
            "    mov a,({fn}__arg_row)",
            "    mov c,a",
            "    mov a,(scv_bg_scroll_y)",
            "    add a,c",
            "    mov c,a",
            "@{fn}_wrap_row",
            "    mov a,c",
            "    mvi b,0x0C",
            "    sub a,b",
            "    skc",
            "    jmp {fn}_wrap_row_apply",
            "    jmp {fn}_row_done",
            "@{fn}_wrap_row_apply",
            "    mov c,a",
            "    jmp {fn}_wrap_row",
            "@{fn}_row_done",
            "    mvi h,0x30",
            "    mvi l,0x40",
            "    mov a,c",
            "    mov b,a",
            "@{fn}_row_loop",
            "    mov a,b",
            "    nei a,0",
            "    jr {fn}_col_step",
            "    adi l,0x20",
            "    aci h,0",
            "    dcr b",
            "    jre {fn}_row_loop",
            "@{fn}_col_step",
            "    mov a,({fn}__arg_col)",
            "    mov b,a",
            "    mov a,(scv_bg_scroll_x)",
            "    add a,b",
            "    mov b,a",
            "@{fn}_addr_wrap_col",
            "    mov a,b",
            "    mvi c,0x20",
            "    sub a,c",
            "    skc",
            "    jmp {fn}_addr_wrap_col_apply",
            "    jmp {fn}_addr_col_done",
            "@{fn}_addr_wrap_col_apply",
            "    mov b,a",
            "    jmp {fn}_addr_wrap_col",
            "@{fn}_addr_col_done",
            "    mov a,b",
            "    adi a,0x03",
            "    add a,l",
            "    mov l,a",
            "    aci h,0",
            "    mov a,({fn}__arg_tile_id)",
            "    ani a,0x3F",
            "    stax (hl)",
            "    ret",
        ],
        "scv_scroll_bg_right": [
            "    lxi hl,0x31BE",
            "    lxi de,0x31BF",
            "    mvi b,0x0C",
            "@{fn}_row",
            "    mvi c,0x1F",
            "@{fn}_byte",
            "    ldax (hl)",
            "    stax (de)",
            "    dcx hl",
            "    dcx de",
            "    dcr c",
            "    jre {fn}_byte",
            "    dcx hl",
            "    dcx de",
            "    dcr b",
            "    jre {fn}_row",
            "    ret",
        ],
        "scv_scroll_bg_left": [
            "    lxi hl,0x3041",
            "    lxi de,0x3040",
            "    mvi b,0x0C",
            "@{fn}_row",
            "    mvi c,0x1F",
            "@{fn}_byte",
            "    ldax (hl)",
            "    stax (de)",
            "    inx hl",
            "    inx de",
            "    dcr c",
            "    jre {fn}_byte",
            "    inx hl",
            "    inx de",
            "    dcr b",
            "    jre {fn}_row",
            "    ret",
        ],
        "scv_scroll_bg_down": [
            "    lxi hl,0x319F",
            "    lxi de,0x31BF",
            "    mvi b,0x0B",
            "@{fn}_row",
            "    mvi c,0x1F",
            "@{fn}_byte",
            "    ldax (hl)",
            "    stax (de)",
            "    dcx hl",
            "    dcx de",
            "    dcr c",
            "    jre {fn}_byte",
            "    dcx hl",
            "    dcx de",
            "    dcr b",
            "    jre {fn}_row",
            "    ret",
        ],
        "scv_scroll_bg_up": [
            "    lxi hl,0x3060",
            "    lxi de,0x3040",
            "    mvi b,0x0B",
            "@{fn}_row",
            "    mvi c,0x1F",
            "@{fn}_byte",
            "    ldax (hl)",
            "    stax (de)",
            "    inx hl",
            "    inx de",
            "    dcr c",
            "    jre {fn}_byte",
            "    inx hl",
            "    inx de",
            "    dcr b",
            "    jre {fn}_row",
            "    ret",
        ],
        "scv_patch_bg_column_right": [
            "    mvi h,0x30",
            "    mvi l,0x40",
            "    mov a,({fn}__arg_row_start)",
            "    mov b,a",
            "@{fn}_row_addr",
            "    mov a,b",
            "    nei a,0",
            "    jr {fn}_row_addr_done",
            "    adi l,0x20",
            "    aci h,0",
            "    dcr b",
            "    jre {fn}_row_addr",
            "@{fn}_row_addr_done",
            "    mvi a,0x1F",
            "    add a,l",
            "    mov l,a",
            "    aci h,0",
            "    mov b,({fn}__arg_row_count)",
            "@{fn}_copy_loop",
            "    mov a,b",
            "    nei a,0",
            "    jr {fn}_done",
            "    ldax (de)",
            "    ani a,0x3F",
            "    stax (hl)",
            "    inx de",
            "    adi l,0x20",
            "    aci h,0",
            "    dcr b",
            "    jre {fn}_copy_loop",
            "@{fn}_done",
            "    ret",
        ],
        "scv_patch_bg_column_left": [
            "    mvi h,0x30",
            "    mvi l,0x40",
            "    mov a,({fn}__arg_row_start)",
            "    mov b,a",
            "@{fn}_row_addr",
            "    mov a,b",
            "    nei a,0",
            "    jr {fn}_row_addr_done",
            "    adi l,0x20",
            "    aci h,0",
            "    dcr b",
            "    jre {fn}_row_addr",
            "@{fn}_row_addr_done",
            "    mov b,({fn}__arg_row_count)",
            "@{fn}_copy_loop",
            "    mov a,b",
            "    nei a,0",
            "    jr {fn}_done",
            "    ldax (de)",
            "    ani a,0x3F",
            "    stax (hl)",
            "    inx de",
            "    adi l,0x20",
            "    aci h,0",
            "    dcr b",
            "    jre {fn}_copy_loop",
            "@{fn}_done",
            "    ret",
        ],
        "scv_patch_bg_row_top": [
            "    mvi h,0x30",
            "    mvi l,0x40",
            "    mov a,({fn}__arg_col_start)",
            "    add a,l",
            "    mov l,a",
            "    aci h,0",
            "    mov b,({fn}__arg_col_count)",
            "@{fn}_copy_loop",
            "    mov a,b",
            "    nei a,0",
            "    jr {fn}_done",
            "    ldax (de)",
            "    ani a,0x3F",
            "    stax (hl)",
            "    inx de",
            "    inx hl",
            "    dcr b",
            "    jre {fn}_copy_loop",
            "@{fn}_done",
            "    ret",
        ],
        "scv_patch_bg_row_bottom": [
            "    mvi h,0x31",
            "    mvi l,0xA0",
            "    mov a,({fn}__arg_col_start)",
            "    add a,l",
            "    mov l,a",
            "    aci h,0",
            "    mov b,({fn}__arg_col_count)",
            "@{fn}_copy_loop",
            "    mov a,b",
            "    nei a,0",
            "    jr {fn}_done",
            "    ldax (de)",
            "    ani a,0x3F",
            "    stax (hl)",
            "    inx de",
            "    inx hl",
            "    dcr b",
            "    jre {fn}_copy_loop",
            "@{fn}_done",
            "    ret",
        ],
        "scv_map_extract_column": [
            "    mov a,({fn}__arg_map_y)",
            "    mov b,a",
            "@{fn}_seek_row",
            "    mov a,b",
            "    nei a,0",
            "    jr {fn}_seek_row_done",
            "    mov a,({fn}__arg_map_width)",
            "    add a,e",
            "    mov e,a",
            "    aci d,0",
            "    dcr b",
            "    jre {fn}_seek_row",
            "@{fn}_seek_row_done",
            "    mov a,({fn}__arg_map_x)",
            "    add a,e",
            "    mov e,a",
            "    aci d,0",
            "    mov b,({fn}__arg_count)",
            "@{fn}_copy_loop",
            "    mov a,b",
            "    nei a,0",
            "    jr {fn}_done",
            "    ldax (de)",
            "    ani a,0x3F",
            "    stax (hl)",
            "    inx hl",
            "    mov a,({fn}__arg_map_width)",
            "    add a,e",
            "    mov e,a",
            "    aci d,0",
            "    dcr b",
            "    jre {fn}_copy_loop",
            "@{fn}_done",
            "    ret",
        ],
        "scv_map_extract_row": [
            "    mov a,({fn}__arg_map_y)",
            "    mov b,a",
            "@{fn}_seek_row",
            "    mov a,b",
            "    nei a,0",
            "    jr {fn}_seek_row_done",
            "    mov a,({fn}__arg_map_width)",
            "    add a,e",
            "    mov e,a",
            "    aci d,0",
            "    dcr b",
            "    jre {fn}_seek_row",
            "@{fn}_seek_row_done",
            "    mov a,({fn}__arg_map_x)",
            "    add a,e",
            "    mov e,a",
            "    aci d,0",
            "    mov b,({fn}__arg_count)",
            "@{fn}_copy_loop",
            "    mov a,b",
            "    nei a,0",
            "    jr {fn}_done",
            "    ldax (de)",
            "    ani a,0x3F",
            "    stax (hl)",
            "    inx de",
            "    inx hl",
            "    dcr b",
            "    jre {fn}_copy_loop",
            "@{fn}_done",
            "    ret",
        ],
        "scv_set_sprite": [
            "    mov a,({fn}__arg_id)",
            "    add a,a",
            "    add a,a",
            "    adi a,0x80",
            "    mov a,b",
            "    ani a,0x40",
            "    nei a,0",
            "    jmp {fn}_addr_ready",
            "    mov a,h",
            "    adi a,0x01",
            "    mov h,a",
            "@{fn}_addr_ready",
            "    mov a,({fn}__arg_tile_id)",
            "    staxi (hl)",
            "    mvi a,0x01",
            "    stax (hl)",
            "    mvi h,0x30",
            "    mvi l,0x40",
            "    mov b,({fn}__arg_row)",
            "@{fn}_row_loop",
            "    mov a,b",
            "    nei a,0",
            "    jr {fn}_col_step",
            "    adi l,0x20",
            "    aci h,0",
            "    dcr b",
            "    jre {fn}_row_loop",
            "@{fn}_col_step",
            "    mov a,({fn}__arg_col)",
            "    adi a,0x03",
            "    add a,l",
            "    mov l,a",
            "    aci h,0",
            "    mov a,({fn}__arg_tile_id)",
            "    stax (hl)",
            "    ret",
        ],
        "scv_move_sprite": [
            "    mov a,({fn}__arg_id)",
            "    add a,a",
            "    add a,a",
            "    adi a,0x80",
            "    mov a,b",
            "    ani a,0x40",
            "    nei a,0",
            "    jmp {fn}_addr_ready",
            "    mov a,h",
            "    adi a,0x01",
            "    mov h,a",
            "@{fn}_addr_ready",
            "    ldaxi (hl)",
            "    mov a,b",
            "    ani a,0x40",
            "    nei a,0",
            "    jmp {fn}_addr_ready",
            "    mov a,h",
            "    adi a,0x01",
            "    mov h,a",
            "@{fn}_addr_ready",
            "    mov a,b",
            "    nei a,0",
            "    jr {fn}_erase_col_step",
            "    adi l,0x20",
            "    aci h,0",
            "    dcr b",
            "    jre {fn}_erase_row_loop",
            "@{fn}_erase_col_step",
            "    mov a,d",
            "    adi a,0x03",
            "    add a,l",
            "    mov l,a",
            "    aci h,0",
            "    mvi a,0x20",
            "    stax (hl)",
            "    mov a,({fn}__arg_id)",
            "    add a,a",
            "    add a,a",
            "    adi a,0x80",
            "    mov a,b",
            "    ani a,0x40",
            "    nei a,0",
            "    jmp {fn}_addr_ready",
            "    mov a,h",
            "    adi a,0x01",
            "    mov h,a",
            "@{fn}_addr_ready",
            "    mov a,e",
            "    stax (hl)",
            "    mvi h,0x30",
            "    mvi l,0x40",
            "    mov b,({fn}__arg_row)",
            "@{fn}_draw_row_loop",
            "    mov a,b",
            "    nei a,0",
            "    jr {fn}_draw_col_step",
            "    adi l,0x20",
            "    aci h,0",
            "    dcr b",
            "    jre {fn}_draw_row_loop",
            "@{fn}_draw_col_step",
            "    mov a,({fn}__arg_col)",
            "    adi a,0x03",
            "    add a,l",
            "    mov l,a",
            "    aci h,0",
            "    mov a,e",
            "    stax (hl)",
            "    ret",
        ],
        "scv_hide_sprite": [
            "    mov a,({fn}__arg_id)",
            "    add a,a",
            "    add a,a",
            "    adi a,0x80",
            "    mov a,b",
            "    ani a,0x40",
            "    nei a,0",
            "    jmp {fn}_addr_ready",
            "    mov a,h",
            "    adi a,0x01",
            "    mov h,a",
            "@{fn}_addr_ready",
            "    inx hl",
            "    inx hl",
            "    mvix (hl),0x00",
            "    mvi h,0x30",
            "    mvi l,0x40",
            "    mov a,c",
            "    mov a,b",
            "    ani a,0x40",
            "    nei a,0",
            "    jmp {fn}_addr_ready",
            "    mov a,h",
            "    adi a,0x01",
            "    mov h,a",
            "@{fn}_addr_ready",
            "    aci h,0",
            "    dcr b",
            "    jre {fn}_erase_row_loop",
            "@{fn}_erase_col_step",
            "    mov a,d",
            "    adi a,0x03",
            "    add a,l",
            "    mov l,a",
            "    aci h,0",
            "    mvi a,0x20",
            "    stax (hl)",
            "    ret",
        ],
        "scv_set_hw_sprite": [
            "    mov a,({fn}__arg_id)",
            "    add a,a",
            "    add a,a",
            "    mov l,a",
            "    mov a,({fn}__arg_id)",
            "    ani a,0x40",
            "    eqi a,0",
            "    jmp {fn}_id_hi",
            "    mvi h,0x32",
            "    jmp {fn}_id_ready",
            "@{fn}_id_hi",
            "    mvi h,0x33",
            "@{fn}_id_ready",
            "    mov a,({fn}__arg_y)",
            "    staxi (hl)",
            "    mov a,({fn}__arg_colour)",
            "    staxi (hl)",
            "    mov a,({fn}__arg_x)",
            "    staxi (hl)",
            "    mov a,({fn}__arg_pattern)",
            "    ani a,0x3F",
            "    mvi b,0x40",
            "    ora a,b",
            "    stax (hl)",
            "    ret",
        ],
        "scv_set_hw_sprite_raw": [
            "    mov a,({fn}__arg_id)",
            "    add a,a",
            "    add a,a",
            "    mov l,a",
            "    mov a,({fn}__arg_id)",
            "    ani a,0x40",
            "    eqi a,0",
            "    jmp {fn}_id_hi",
            "    mvi h,0x32",
            "    jmp {fn}_id_ready",
            "@{fn}_id_hi",
            "    mvi h,0x33",
            "@{fn}_id_ready",
            "    mov a,({fn}__arg_y)",
            "    staxi (hl)",
            "    mov a,({fn}__arg_colour)",
            "    staxi (hl)",
            "    mov a,({fn}__arg_x)",
            "    staxi (hl)",
            "    mov a,({fn}__arg_pattern)",
            "    ani a,0x7F",
            "    stax (hl)",
            "    ret",
        ],
        "scv_hide_hw_sprite": [
            "    mov a,({fn}__arg_id)",
            "    add a,a",
            "    add a,a",
            "    mov l,a",
            "    mov a,({fn}__arg_id)",
            "    ani a,0x40",
            "    eqi a,0",
            "    jmp {fn}_id_hi",
            "    mvi h,0x32",
            "    jmp {fn}_id_ready",
            "@{fn}_id_hi",
            "    mvi h,0x33",
            "@{fn}_id_ready",
            "    mvi a,0x00",
            "    staxi (hl)",
            "    staxi (hl)",
            "    staxi (hl)",
            "    stax (hl)",
            "    ret",
        ],
        "scv_set_hw_sprite_pos": [
            "    mov a,({fn}__arg_id)",
            "    add a,a",
            "    add a,a",
            "    mov l,a",
            "    mov a,({fn}__arg_id)",
            "    ani a,0x40",
            "    eqi a,0",
            "    jmp {fn}_id_hi",
            "    mvi h,0x32",
            "    jmp {fn}_id_ready",
            "@{fn}_id_hi",
            "    mvi h,0x33",
            "@{fn}_id_ready",
            "    mov a,({fn}__arg_y)",
            "    staxi (hl)",
            "    inx hl",
            "    mov a,({fn}__arg_x)",
            "    stax (hl)",
            "    ret",
        ],
        "scv_set_hw_sprite_pattern": [
            "    mov a,({fn}__arg_id)",
            "    add a,a",
            "    add a,a",
            "    mov l,a",
            "    mov a,({fn}__arg_id)",
            "    ani a,0x40",
            "    eqi a,0",
            "    jmp {fn}_id_hi",
            "    mvi h,0x32",
            "    jmp {fn}_id_ready",
            "@{fn}_id_hi",
            "    mvi h,0x33",
            "@{fn}_id_ready",
            "    inx hl",
            "    inx hl",
            "    inx hl",
            "    mov a,({fn}__arg_pattern)",
            "    ani a,0x7F",
            "    stax (hl)",
            "    ret",
        ],
        "scv_set_hw_sprite_colour": [
            "    mov a,({fn}__arg_id)",
            "    add a,a",
            "    add a,a",
            "    mov l,a",
            "    mov a,({fn}__arg_id)",
            "    ani a,0x40",
            "    eqi a,0",
            "    jmp {fn}_id_hi",
            "    mvi h,0x32",
            "    jmp {fn}_id_ready",
            "@{fn}_id_hi",
            "    mvi h,0x33",
            "@{fn}_id_ready",
            "    inx hl",
            "    mov a,({fn}__arg_colour)",
            "    stax (hl)",
            "    ret",
        ],
        "scv_set_hw_sprite_frame": [
            "    mov a,({fn}__arg_base_pattern)",
            "    mov b,a",
            "    mov a,({fn}__arg_frame)",
            "    add a,b",
            "    mov c,a",
            "    mov a,c",
            "    ani a,0x7F",
            "    mov c,a",
            "    mov a,({fn}__arg_id)",
            "    add a,a",
            "    add a,a",
            "    mov l,a",
            "    mov a,({fn}__arg_id)",
            "    ani a,0x40",
            "    eqi a,0",
            "    jmp {fn}_id_hi",
            "    mvi h,0x32",
            "    jmp {fn}_id_ready",
            "@{fn}_id_hi",
            "    mvi h,0x33",
            "@{fn}_id_ready",
            "    inx hl",
            "    inx hl",
            "    inx hl",
            "    mov a,c",
            "    stax (hl)",
            "    ret",
        ],
        "scv_set_hw_sprite_anim": [
            "    mov a,({fn}__arg_base_pattern)",
            "    mov b,a",
            "    mov a,({fn}__arg_frame)",
            "    add a,b",
            "    mov c,a",
            "    mov a,c",
            "    ani a,0x3F",
            "    mvi b,0x40",
            "    ora a,b",
            "    mov c,a",
            "    mov a,({fn}__arg_id)",
            "    add a,a",
            "    add a,a",
            "    mov l,a",
            "    mov a,({fn}__arg_id)",
            "    ani a,0x40",
            "    eqi a,0",
            "    jmp {fn}_id_hi",
            "    mvi h,0x32",
            "    jmp {fn}_id_ready",
            "@{fn}_id_hi",
            "    mvi h,0x33",
            "@{fn}_id_ready",
            "    mov a,({fn}__arg_y)",
            "    staxi (hl)",
            "    mov a,({fn}__arg_colour)",
            "    staxi (hl)",
            "    mov a,({fn}__arg_x)",
            "    staxi (hl)",
            "    mov a,c",
            "    stax (hl)",
            "    ret",
        ],
        "scv_set_hw_sprite_mode": [
            "    mov a,({fn}__arg_use_64_sprite_mode)",
            "    ani a,0x01",
            "    add a,a",
            "    add a,a",
            "    mvi b,0xF0",
            "    ora a,b",
            "    lxi hl,0x3400",
            "    stax (hl)",
            "    ret",
        ],
        "scv_move_hw_sprite_left": [
            "    mov a,({fn}__arg_id)",
            "    add a,a",
            "    add a,a",
            "    mov l,a",
            "    mov a,({fn}__arg_id)",
            "    ani a,0x40",
            "    eqi a,0",
            "    jmp {fn}_id_hi",
            "    mvi h,0x32",
            "    jmp {fn}_id_ready",
            "@{fn}_id_hi",
            "    mvi h,0x33",
            "@{fn}_id_ready",
            "    inx hl",
            "    inx hl",
            "    ldax (hl)",
            "    mov b,a",
            "    mov a,({fn}__arg_min_x)",
            "    mov c,a",
            "    mov a,c",
            "    sub a,b",
            "    skc",
            "    jmp {fn}_no_move",
            "    mov a,({fn}__arg_step)",
            "    mov c,a",
            "    mov a,b",
            "    sub a,c",
            "    stax (hl)",
            "@{fn}_no_move",
            "    ret",
        ],
        "scv_move_hw_sprite_right": [
            "    mov a,({fn}__arg_id)",
            "    add a,a",
            "    add a,a",
            "    mov l,a",
            "    mov a,({fn}__arg_id)",
            "    ani a,0x40",
            "    eqi a,0",
            "    jmp {fn}_id_hi",
            "    mvi h,0x32",
            "    jmp {fn}_id_ready",
            "@{fn}_id_hi",
            "    mvi h,0x33",
            "@{fn}_id_ready",
            "    inx hl",
            "    inx hl",
            "    ldax (hl)",
            "    mov b,a",
            "    mov a,({fn}__arg_max_x)",
            "    mov c,a",
            "    mov a,b",
            "    sub a,c",
            "    sknc",
            "    jr {fn}_do_move",
            "    jmp {fn}_no_move",
            "@{fn}_do_move",
            "    mov a,({fn}__arg_step)",
            "    add a,b",
            "    stax (hl)",
            "@{fn}_no_move",
            "    ret",
        ],
        "scv_move_hw_sprite_up": [
            "    mov a,({fn}__arg_id)",
            "    add a,a",
            "    add a,a",
            "    mov l,a",
            "    mov a,({fn}__arg_id)",
            "    ani a,0x40",
            "    eqi a,0",
            "    jmp {fn}_id_hi",
            "    mvi h,0x32",
            "    jmp {fn}_id_ready",
            "@{fn}_id_hi",
            "    mvi h,0x33",
            "@{fn}_id_ready",
            "    ldax (hl)",
            "    mov b,a",
            "    mov a,({fn}__arg_min_y)",
            "    mov c,a",
            "    mov a,c",
            "    sub a,b",
            "    skc",
            "    jmp {fn}_no_move",
            "    mov a,({fn}__arg_step)",
            "    mov c,a",
            "    mov a,b",
            "    sub a,c",
            "    stax (hl)",
            "@{fn}_no_move",
            "    ret",
        ],
        "scv_move_hw_sprite_down": [
            "    mov a,({fn}__arg_id)",
            "    add a,a",
            "    add a,a",
            "    mov l,a",
            "    mov a,({fn}__arg_id)",
            "    ani a,0x40",
            "    eqi a,0",
            "    jmp {fn}_id_hi",
            "    mvi h,0x32",
            "    jmp {fn}_id_ready",
            "@{fn}_id_hi",
            "    mvi h,0x33",
            "@{fn}_id_ready",
            "    ldax (hl)",
            "    mov b,a",
            "    mov a,({fn}__arg_max_y)",
            "    mov c,a",
            "    mov a,b",
            "    sub a,c",
            "    sknc",
            "    jr {fn}_do_move",
            "    jmp {fn}_no_move",
            "@{fn}_do_move",
            "    mov a,({fn}__arg_step)",
            "    add a,b",
            "    stax (hl)",
            "@{fn}_no_move",
            "    ret",
        ],
        "scv_get_hw_sprite_y": [
            "    mov a,({fn}__arg_id)",
            "    add a,a",
            "    add a,a",
            "    mov l,a",
            "    mov a,({fn}__arg_id)",
            "    ani a,0x40",
            "    eqi a,0",
            "    jmp {fn}_id_hi",
            "    mvi h,0x32",
            "    jmp {fn}_id_ready",
            "@{fn}_id_hi",
            "    mvi h,0x33",
            "@{fn}_id_ready",
            "    ldax (hl)",
            "    ret",
        ],
        "scv_set_vdc_regs": [
            "    lxi hl,0x3400",
            "    mov a,({fn}__arg_r0)",
            "    staxi (hl)",
            "    mov a,({fn}__arg_r1)",
            "    staxi (hl)",
            "    mov a,({fn}__arg_r2)",
            "    staxi (hl)",
            "    mov a,({fn}__arg_r3)",
            "    stax (hl)",
            "    ret",
        ],
        "scv_bios_clear_text_vram": [
            "    call 0x0A1B",
            "    ret",
        ],
        "scv_bios_clear_pattern_vram": [
            "    call 0x0A4A",
            "    ret",
        ],
        "scv_bios_clear_hw_sprites": [
            "    call 0x0A28",
            "    ret",
        ],
        "scv_bios_add16_hi": [
            "    mov a,({fn}__arg_de_hi)",
            "    mov d,a",
            "    mov a,({fn}__arg_de_lo)",
            "    mov e,a",
            "    mov a,({fn}__arg_hl_hi)",
            "    mov h,a",
            "    mov a,({fn}__arg_hl_lo)",
            "    mov l,a",
            "    calt 0x9A",
            "    mov a,d",
            "    ret",
        ],
        "scv_bios_sub16_hi": [
            "    mov a,({fn}__arg_de_hi)",
            "    mov d,a",
            "    mov a,({fn}__arg_de_lo)",
            "    mov e,a",
            "    mov a,({fn}__arg_hl_hi)",
            "    mov h,a",
            "    mov a,({fn}__arg_hl_lo)",
            "    mov l,a",
            "    calt 0x9C",
            "    mov a,d",
            "    ret",
        ],
        "scv_read_pad1": [
            "    mvi a,0xFD",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    mov (scv_pad1_state),a",
            "    ret",
        ],
        "scv_read_pad2": [
            "    mvi a,0xFE",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    mov (scv_pad2_state),a",
            "    ret",
        ],
        "scv_read_input_scan": [
            "    mov a,({fn}__arg_pa_mask)",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    ret",
        ],
        "scv_read_keypad_number": [
            "    mvi a,0xFD",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    mov (scv_pad1_state),a",
            "    mvi a,0xFE",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    mov (scv_pad2_state),a",
            "    mvi a,0xFB",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    ani a,0x80",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_f7_bit6",
            "    mvi a,1",
            "    ret",
            "@{fn}_f7_bit6",
            "    mvi a,0xF7",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    ani a,0x40",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_f7_bit7",
            "    mvi a,2",
            "    ret",
            "@{fn}_f7_bit7",
            "    mvi a,0xF7",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    ani a,0x80",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_ee_bit6",
            "    mvi a,3",
            "    ret",
            "@{fn}_ee_bit6",
            "    mvi a,0xEE",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    ani a,0x40",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_ee_bit7",
            "    mvi a,4",
            "    ret",
            "@{fn}_ee_bit7",
            "    mvi a,0xEE",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    ani a,0x80",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_df_bit6",
            "    mvi a,5",
            "    ret",
            "@{fn}_df_bit6",
            "    mvi a,0xDF",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    ani a,0x40",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_df_bit7",
            "    mvi a,6",
            "    ret",
            "@{fn}_df_bit7",
            "    mvi a,0xDF",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    ani a,0x80",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_bf_bit6",
            "    mvi a,7",
            "    ret",
            "@{fn}_bf_bit6",
            "    mvi a,0xBF",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    ani a,0x40",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_bf_bit7",
            "    mvi a,8",
            "    ret",
            "@{fn}_bf_bit7",
            "    mvi a,0xBF",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    ani a,0x80",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_fb_bit6",
            "    mvi a,9",
            "    ret",
            "@{fn}_fb_bit6",
            "    mvi a,0xFB",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    ani a,0x40",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_7f_bit6",
            "    mvi a,10",
            "    ret",
            "@{fn}_7f_bit6",
            "    mvi a,0x7F",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    ani a,0x40",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_7f_bit7",
            "    mvi a,11",
            "    ret",
            "@{fn}_7f_bit7",
            "    mvi a,0x7F",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    ani a,0x80",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_none",
            "    mvi a,12",
            "    ret",
            "@{fn}_none",
            "    mvi a,0",
            "    ret",
        ],
        "scv_read_keypad_char": [
            "    mvi a,0xFD",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    mov (scv_pad1_state),a",
            "    mvi a,0xFE",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    mov (scv_pad2_state),a",
            "    mvi a,0xFB",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    ani a,0x80",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_f7_bit6",
            "    mvi a,0x31",
            "    ret",
            "@{fn}_f7_bit6",
            "    mvi a,0xF7",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    ani a,0x40",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_f7_bit7",
            "    mvi a,0x32",
            "    ret",
            "@{fn}_f7_bit7",
            "    mvi a,0xF7",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    ani a,0x80",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_ee_bit6",
            "    mvi a,0x33",
            "    ret",
            "@{fn}_ee_bit6",
            "    mvi a,0xEE",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    ani a,0x40",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_ee_bit7",
            "    mvi a,0x34",
            "    ret",
            "@{fn}_ee_bit7",
            "    mvi a,0xEE",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    ani a,0x80",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_df_bit6",
            "    mvi a,0x35",
            "    ret",
            "@{fn}_df_bit6",
            "    mvi a,0xDF",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    ani a,0x40",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_df_bit7",
            "    mvi a,0x36",
            "    ret",
            "@{fn}_df_bit7",
            "    mvi a,0xDF",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    ani a,0x80",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_bf_bit6",
            "    mvi a,0x37",
            "    ret",
            "@{fn}_bf_bit6",
            "    mvi a,0xBF",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    ani a,0x40",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_bf_bit7",
            "    mvi a,0x38",
            "    ret",
            "@{fn}_bf_bit7",
            "    mvi a,0xBF",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    ani a,0x80",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_fb_bit6",
            "    mvi a,0x39",
            "    ret",
            "@{fn}_fb_bit6",
            "    mvi a,0xFB",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    ani a,0x40",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_7f_bit6",
            "    mvi a,0x30",
            "    ret",
            "@{fn}_7f_bit6",
            "    mvi a,0x7F",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    ani a,0x40",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_7f_bit7",
            "    mvi a,0x43",
            "    ret",
            "@{fn}_7f_bit7",
            "    mvi a,0x7F",
            "    mov pa,a",
            "    nop",
            "    mov a,pb",
            "    mov a,pb",
            "    ani a,0x80",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_none",
            "    mvi a,0x45",
            "    ret",
            "@{fn}_none",
            "    mvi a,0x00",
            "    ret",
        ],
        "scv_stop_sound": [
            "    lxi hl,0x3600",
            "    di",
            "    mvi b,0xFF",
            "@{fn}_wv1",
            "    skit f2",
            "    jr {fn}_wv1_wait",
            "    jmp {fn}_wv1_done",
            "@{fn}_wv1_wait",
            "    dcr b",
            "    jre {fn}_wv1",
            "    jmp {fn}_wv1_done",
            "@{fn}_wv1_done",
            "    skit f1",
            "    nop",
            "    mvix (hl),0x00",
            "    ei",
            "    ret",
        ],
        "scv_play_tone_raw": [
            "    lxi hl,0x3600",
            "    di",
            "    mvi b,0xFF",
            "@{fn}_wv1",
            "    skit f2",
            "    jr {fn}_wv1_wait",
            "    jmp {fn}_wv1_done",
            "@{fn}_wv1_wait",
            "    dcr b",
            "    jre {fn}_wv1",
            "    jmp {fn}_wv1_done",
            "@{fn}_wv1_done",
            "    skit f1",
            "    nop",
            "    mvi a,0x02",
            "    stax (hl)",
            "    mvi b,0xFF",
            "@{fn}_wf0",
            "    skit f1",
            "    jr {fn}_wf0_wait",
            "    jmp {fn}_wf0_done",
            "@{fn}_wf0_wait",
            "    dcr b",
            "    jre {fn}_wf0",
            "    jmp {fn}_wf0_done",
            "@{fn}_wf0_done",
            "    mov a,({fn}__arg_p1)",
            "    stax (hl)",
            "    mvi b,0xFF",
            "@{fn}_wf1",
            "    skit f1",
            "    jr {fn}_wf1_wait",
            "    jmp {fn}_wf1_done",
            "@{fn}_wf1_wait",
            "    dcr b",
            "    jre {fn}_wf1",
            "    jmp {fn}_wf1_done",
            "@{fn}_wf1_done",
            "    mov a,({fn}__arg_p2)",
            "    stax (hl)",
            "    mvi b,0xFF",
            "@{fn}_wf2",
            "    skit f1",
            "    jr {fn}_wf2_wait",
            "    jmp {fn}_wf2_done",
            "@{fn}_wf2_wait",
            "    dcr b",
            "    jre {fn}_wf2",
            "    jmp {fn}_wf2_done",
            "@{fn}_wf2_done",
            "    mov a,({fn}__arg_p3)",
            "    stax (hl)",
            "    mvi b,0xFF",
            "@{fn}_wv2",
            "    skit f2",
            "    jr {fn}_wv2_wait",
            "    jmp {fn}_wv2_done",
            "@{fn}_wv2_wait",
            "    dcr b",
            "    jre {fn}_wv2",
            "    jmp {fn}_wv2_done",
            "@{fn}_wv2_done",
            "    ei",
            "    ret",
        ],
        "scv_play_tone_packet": [
            "    lxi hl,0x3600",
            "    di",
            "    mvi b,0xFF",
            "@{fn}_wv1",
            "    skit f2",
            "    jr {fn}_wv1_wait",
            "    jmp {fn}_wv1_done",
            "@{fn}_wv1_wait",
            "    dcr b",
            "    jre {fn}_wv1",
            "    jmp {fn}_wv1_done",
            "@{fn}_wv1_done",
            "    skit f1",
            "    nop",
            "    mvi a,0x02",
            "    stax (hl)",
            "    mvi b,0xFF",
            "@{fn}_wf0",
            "    skit f1",
            "    jr {fn}_wf0_wait",
            "    jmp {fn}_wf0_done",
            "@{fn}_wf0_wait",
            "    dcr b",
            "    jre {fn}_wf0",
            "    jmp {fn}_wf0_done",
            "@{fn}_wf0_done",
            "    mvi a,0xA0",
            "    stax (hl)",
            "    mvi b,0xFF",
            "@{fn}_wf1",
            "    skit f1",
            "    jr {fn}_wf1_wait",
            "    jmp {fn}_wf1_done",
            "@{fn}_wf1_wait",
            "    dcr b",
            "    jre {fn}_wf1",
            "    jmp {fn}_wf1_done",
            "@{fn}_wf1_done",
            "    mov a,({fn}__arg_pitch)",
            "    stax (hl)",
            "    mvi b,0xFF",
            "@{fn}_wf2",
            "    skit f1",
            "    jr {fn}_wf2_wait",
            "    jmp {fn}_wf2_done",
            "@{fn}_wf2_wait",
            "    dcr b",
            "    jre {fn}_wf2",
            "    jmp {fn}_wf2_done",
            "@{fn}_wf2_done",
            "    mov a,({fn}__arg_param)",
            "    eqi a,0",
            "    skz",
            "    mvi a,0x10",
            "    stax (hl)",
            "    mvi b,0xFF",
            "@{fn}_wv2",
            "    skit f2",
            "    jr {fn}_wv2_wait",
            "    jmp {fn}_wv2_done",
            "@{fn}_wv2_wait",
            "    dcr b",
            "    jre {fn}_wv2",
            "    jmp {fn}_wv2_done",
            "@{fn}_wv2_done",
            "    ei",
            "    ret",
        ],
        "scv_check_collision": [
            "    mov a,({fn}__arg_id_a)",
            "    add a,a",
            "    add a,a",
            "    adi a,0x80",
            "    mov l,a",
            "    mvi h,0xFF",
            "    ldaxi (hl)",
            "    mov b,a",
            "    inx hl",
            "    ldaxi (hl)",
            "    mov c,a",
            "    ldax (hl)",
            "    nei a,0",
            "    jre {fn}_no_collision",
            "    mov a,({fn}__arg_id_b)",
            "    add a,a",
            "    add a,a",
            "    adi a,0x80",
            "    mov l,a",
            "    mvi h,0xFF",
            "    ldaxi (hl)",
            "    mov d,a",
            "    inx hl",
            "    ldaxi (hl)",
            "    mov e,a",
            "    ldax (hl)",
            "    nei a,0",
            "    jre {fn}_no_collision",
            "    mov a,b",
            "    mov h,a",
            "    mov a,c",
            "    mov l,a",
            "    mov a,e",
            "    sub a,l",
            "    skc",
            "    jmp {fn}_x_b_ge_a",
            "    mov a,l",
            "    sub a,e",
            "@{fn}_x_b_ge_a",
            "    mvi b,0x10",
            "    sub a,b",
            "    skc",
            "    jmp {fn}_no_collision",
            "    mov a,d",
            "    sub a,h",
            "    skc",
            "    jmp {fn}_y_b_ge_a",
            "    mov a,h",
            "    sub a,d",
            "@{fn}_y_b_ge_a",
            "    mvi b,0x10",
            "    sub a,b",
            "    skc",
            "    jmp {fn}_no_collision",
            "    mvi a,0x01",
            "    mov (scv_collision_result),a",
            "    ret",
            "@{fn}_no_collision",
            "    mvi a,0x00",
            "    mov (scv_collision_result),a",
            "    ret",
        ],
        "scv_start_timer": [
            "    mov a,({fn}__arg_count)",
            "    mov tm0,a",
            "    mvi a,0x01",  # Set TM1 to 1 instead of 0
            "    mov tm1,a",
            "    stm",
            "    ret",
        ],
        "scv_timer_expired": [
            "    skit ft",
            "    jmp {fn}_not_expired",
            "    mvi a,0x01",
            "    ret",
            "@{fn}_not_expired",
            "    mvi a,0x00",
            "    ret",
        ],
        "scv_wait_vblank": [
            "@{fn}_wait_clear",
            "    sknit f2",
            "    jr {fn}_wait_clear",
            "@{fn}_wait_set",
            "    skit f2",
            "    jr {fn}_wait_set",
            "    ret",
        ],
    }

    for _fn, _mask in PAD_BOOL_HELPERS.items():
        SCV_API_PARAMS[_fn] = ["pad_state"]
        SCV_API_IMPLS[_fn] = [
            "    mov a,({fn}__arg_pad_state)",
            f"    ani a,0x{_mask:02X}",
            "    eqi a,0",
            "    jmp {fn}_not_pressed",
            "    jmp {fn}_pressed",
            "@{fn}_not_pressed",
            "    mvi a,0x00",
            "    ret",
            "@{fn}_pressed",
            "    mvi a,0x01",
            "    ret",
        ]

    def __init__(self, strict: bool = True, ram_base: int = 0xFF80) -> None:
        self.strict = strict
        self.ram_base = ram_base
        self.lines: List[str] = []
        self.data_symbols: List[str] = []
        self.symbol_values: Dict[str, int] = {}
        self.global_data_symbols: List[str] = []
        self.global_symbol_offsets: Dict[str, int] = {}
        self.frame_data_symbols: Dict[str, List[str]] = {}
        self.frame_symbol_offsets: Dict[str, Dict[str, int]] = {}
        self.function_calls: Dict[str, Set[str]] = {}
        self.global_size_total = 0
        self.frame_size_total = 0
        self.frame_sizes_by_function: Dict[str, int] = {}
        self.user_global_scalar_names: Set[str] = set()
        self.user_global_array_aliases: Set[str] = set()
        self.user_global_struct_aliases: Set[str] = set()
        self.globals: Set[str] = set()
        self.current_fn: Optional[FunctionContext] = None
        self.function_params: Dict[str, List[str]] = {}
        self.signed_param_names_by_function: Dict[str, Set[str]] = {}
        self.signed_returning_functions: Set[str] = set()
        self.defined_functions: Set[str] = set()
        self.extern_functions: Set[str] = set()
        self.label_counter = 0
        self.loop_end_labels: List[str] = []
        self.source_path: Optional[Path] = None
        self.asset_directives: List[AssetDirective] = []
        self.asset_functions: Dict[str, AssetFunction] = {}
        self.asset_bulk_functions: Dict[str, List[str]] = {}
        self.sound_assets: List[SoundAsset] = []
        self.rom_constants: Dict[str, int] = {}
        self.rom_data_blocks: List[RomDataBlock] = []
        self.rom_array_labels: Dict[str, str] = {}
        self.rom_array_lengths: Dict[str, int] = {}
        self.rom_array_dims: Dict[str, List[int]] = {}  # For multi-dimensional arrays
        self.rom_array_values: Dict[str, List[int]] = {}
        self.ram_array_labels: Dict[str, str] = {}
        self.ram_array_lengths: Dict[str, int] = {}
        self.ram_array_byte_lengths: Dict[str, int] = {}
        self.ram_array_element_sizes: Dict[str, int] = {}
        self.ram_array_struct_types: Dict[str, str] = {}
        self.signed_symbols: Set[str] = set()
        self.signed_ram_arrays: Set[str] = set()
        self.signed_rom_arrays: Set[str] = set()
        self.struct_defs: Dict[str, List[str]] = {}
        self.struct_sizes: Dict[str, int] = {}  # Track struct sizes for array[i].field access
        self.struct_field_offsets: Dict[str, Dict[str, int]] = {}  # Track field offsets within structs
        self.struct_instances: Dict[str, Dict[str, str]] = {}
        self.expr_tmp_depth = 0
        self.cart_profile = "flat32"
        self.pending_function_bank: Optional[int] = None
        self.function_bank_hints: Dict[str, int] = {}
        self.rom_bank_hints: Dict[str, int] = {}
        self.function_wrapper_labels: Dict[str, str] = {}
        self.function_body_labels: Dict[str, str] = {}
        self.function_end_labels: Dict[str, str] = {}

    def convert(self, source: str, source_path: Optional[Path] = None) -> str:
        self.source_path = source_path
        self.data_symbols = []
        self.symbol_values = {}
        self.global_data_symbols = []
        self.global_symbol_offsets = {}
        self.frame_data_symbols = {}
        self.frame_symbol_offsets = {}
        self.function_calls = {}
        self.global_size_total = 0
        self.frame_size_total = 0
        self.frame_sizes_by_function = {}
        self.user_global_scalar_names = set()
        self.user_global_array_aliases = set()
        self.user_global_struct_aliases = set()
        self.asset_directives = []
        self.asset_functions = {}
        self.asset_bulk_functions = {}
        self.sound_assets = []
        self.rom_constants = {}
        self.rom_data_blocks = []
        self.rom_array_labels = {}
        self.rom_array_lengths = {}
        self.rom_array_dims = {}
        self.rom_array_values = {}
        self.ram_array_labels = {}
        self.ram_array_lengths = {}
        self.ram_array_byte_lengths = {}
        self.ram_array_element_sizes = {}
        self.ram_array_struct_types = {}
        self.signed_symbols = set()
        self.signed_ram_arrays = set()
        self.signed_rom_arrays = set()
        self.struct_defs = {}
        self.struct_sizes = {}
        self.struct_field_offsets = {}
        self.struct_instances = {}
        self.expr_tmp_depth = 0
        self.cart_profile = "flat32"
        self.pending_function_bank = None
        self.function_bank_hints = {}
        self.rom_bank_hints = {}
        self.function_wrapper_labels = {}
        self.function_body_labels = {}
        self.function_end_labels = {}
        self.function_params = {}
        self.signed_param_names_by_function = {}
        self.signed_returning_functions = set()
        self.defined_functions = set()
        self.extern_functions = set()
        parser = c_parser.CParser()
        ast = parser.parse(
            self._sanitize_source(source, current_path=self.source_path, include_stack=set())
        )

        self.lines = [
            "require 'scv'",
            "location(0x8000, 0xFFFF)",
            "section{\"rom\", org=0x8000}",
            "    dc.b 'H'",
            "",
            "__SYMBOL_TABLE__",
            "",
        ]

        for ext in ast.ext:
            if isinstance(ext, c_ast.Decl) and not isinstance(ext.type, c_ast.FuncDecl):
                self._declare_global(ext)

        self._collect_function_signatures(ast)
        self._validate_cart_metadata_targets()
        self._collect_function_calls(ast)
        self._register_asset_function_signatures()

        self.lines.extend(
            [
                "@main",
                "    di",
                f"    lxi sp,0x{self.STACK_INIT:04X}",
                "    ei",
                "    calt 0x8C",
                "    lxi hl,0x3400",
                "    mvi a,0xF4",
                "    staxi (hl)",
                "    mvi a,0x00",
                "    staxi (hl)",
                "    staxi (hl)",
                "    mvi a,0xF1",
                "    stax (hl)",
                "    call fn_main",
                "@halt_loop",
                "    jr halt_loop",
                "",
            ]
        )

        saw_main = False
        for ext in ast.ext:
            if isinstance(ext, c_ast.FuncDef):
                if ext.decl.name == "main":
                    saw_main = True
                self._emit_function(ext)

        if not saw_main:
            self.lines.extend(
                [
                    "@fn_main",
                    "    ret",
                    "",
                ]
            )

        self._emit_extern_stubs()
        self._emit_asset_data()
        self._emit("")
        self._emit("writebin(filename .. '.bin')")
        self._finalize_symbol_layout()
        self._insert_symbol_table()

        return "\n".join(self.lines) + "\n"

    def _register_asset_function_signatures(self) -> None:
        for function_name in self.asset_functions:
            self.function_params[function_name] = ["pattern_slot"]

    def _collect_function_signatures(self, ast: c_ast.FileAST) -> None:
        self.function_params = {}
        self.signed_param_names_by_function = {}
        self.signed_returning_functions = set()
        defined: Set[str] = set()

        # First pass: collect definitions (FuncDef nodes)
        for ext in ast.ext:
            if not isinstance(ext, c_ast.FuncDef):
                continue
            defined.add(ext.decl.name)
            params: List[str] = []
            signed_params: Set[str] = set()
            decl = ext.decl.type
            if isinstance(decl, c_ast.FuncDecl) and decl.args:
                for param in decl.args.params:
                    if isinstance(param, c_ast.Decl) and param.name:
                        params.append(param.name)
                        if self._decl_is_signed_char(param):
                            signed_params.add(param.name)
            self.function_params[ext.decl.name] = params
            self.signed_param_names_by_function[ext.decl.name] = signed_params
            if self._type_node_is_signed_char(decl.type):
                self.signed_returning_functions.add(ext.decl.name)

        self.defined_functions = set(defined)

        # Second pass: collect prototypes (extern declarations)
        for ext in ast.ext:
            if not isinstance(ext, c_ast.Decl):
                continue
            if not isinstance(ext.type, c_ast.FuncDecl):
                continue
            if ext.name in defined:
                continue
            # SCV API functions already have canonical param names in SCV_API_PARAMS;
            # don't override them with possibly different spellings from the header.
            if ext.name in self.SCV_API_PARAMS:
                continue
            params = []
            signed_params: Set[str] = set()
            if ext.type.args:
                for param in ext.type.args.params:
                    if isinstance(param, c_ast.Decl) and param.name:
                        params.append(param.name)
                        if self._decl_is_signed_char(param):
                            signed_params.add(param.name)
            self.function_params[ext.name] = params
            self.signed_param_names_by_function[ext.name] = signed_params
            if self._type_node_is_signed_char(ext.type.type):
                self.signed_returning_functions.add(ext.name)

    def _collect_function_calls(self, ast: c_ast.FileAST) -> None:
        self.function_calls = {name: set() for name in self.defined_functions}
        for ext in ast.ext:
            if not isinstance(ext, c_ast.FuncDef):
                continue
            caller = ext.decl.name
            if caller not in self.defined_functions:
                continue
            self.function_calls[caller] = self._find_called_user_functions(ext.body)

    def _find_called_user_functions(self, node: c_ast.Node) -> Set[str]:
        calls: Set[str] = set()
        for _, child in node.children():
            if isinstance(child, c_ast.FuncCall) and isinstance(child.name, c_ast.ID):
                callee = self.API_ALIASES.get(child.name.name, child.name.name)
                if callee in self.defined_functions:
                    calls.add(callee)
            calls.update(self._find_called_user_functions(child))
        return calls

    def _emit_extern_stubs(self) -> None:
        if not self.extern_functions:
            return

        if "scv_print_string" in self.extern_functions:
            self.extern_functions.add("scv_print_char")
        if "scv_print_char" in self.extern_functions:
            if "scv_print_char" not in self.function_params:
                self.function_params["scv_print_char"] = self.SCV_API_PARAMS["scv_print_char"]
        if "scv_random_range" in self.extern_functions:
            self.extern_functions.add("scv_random_u8")
            if "scv_random_u8" not in self.function_params:
                self.function_params["scv_random_u8"] = self.SCV_API_PARAMS["scv_random_u8"]

        self._emit("-- *** stubs for extern functions — replace with real implementations ***")
        self._emit("")
        for fn in sorted(self.extern_functions):
            params = self.function_params.get(fn, [])
            for p in params:
                slot = self._alloc_symbol(self._arg_symbol_name(fn, p))
                self._emit(f"-- {fn}: arg {p} arrives in ({slot})")

            if fn == "scv_read_pad1":
                self._alloc_symbol("scv_pad1_state")
            elif fn == "scv_read_pad2":
                self._alloc_symbol("scv_pad2_state")
            elif fn == "scv_check_collision":
                self._alloc_symbol("scv_collision_result")
            elif fn == "scv_set_bg_scroll" or fn == "scv_draw_bg_tile_scrolled":
                self._alloc_symbol("scv_bg_scroll_x")
                self._alloc_symbol("scv_bg_scroll_y")
            elif fn == "sprintf":
                self._alloc_symbol("sprintf__tmp_count")
                self._alloc_symbol("sprintf__tmp_rem")
                self._alloc_symbol("sprintf__tmp_hundreds")
                self._alloc_symbol("sprintf__tmp_tens")
            elif fn == "scv_cart_select_bank" or fn == "scv_cart_restore_bank":
                for symbol_name in self._get_cart_runtime_symbols():
                    self._alloc_symbol(symbol_name)
            elif fn == "scv_random_seed" or fn == "scv_random_u8" or fn == "scv_random_range":
                self._alloc_symbol("scv_random__state")

            self._emit(f"@fn_{fn}")
            asset_fn = self.asset_functions.get(fn)
            bulk_asset_frames = self.asset_bulk_functions.get(fn)
            sound_asset = next((s for s in self.sound_assets if s.play_fn == fn), None)
            if fn == "scv_cart_select_bank" or fn == "scv_cart_restore_bank":
                impl = self._build_cart_hook_impl(fn)
            elif asset_fn is not None:
                impl = self._build_asset_loader_impl(asset_fn)
            elif bulk_asset_frames is not None:
                impl = self._build_asset_bulk_loader_impl(fn, bulk_asset_frames)
            elif sound_asset is not None:
                impl = self._build_sound_play_impl(fn, sound_asset)
            else:
                impl = self.SCV_API_IMPLS.get(fn)
            if impl is not None:
                for line in impl:
                    self._emit(self._format_impl_line(fn, line))
            else:
                self._emit(f"    -- TODO implement {fn}")
                self._emit("    ret")
            self._emit("")

    def _emit_asset_data(self) -> None:
        if not self.asset_directives:
            pass
        else:
            self._emit("-- PNG asset data")
            self._emit("")
            for directive in self.asset_directives:
                self._emit(
                    f"-- {directive.kind} {directive.name} from {directive.source_path.as_posix()}"
                )
                for frame in directive.frames:
                    self._emit(f"@{frame.symbol_name}")
                    for offset in range(0, len(frame.bytes_out), 16):
                        chunk = frame.bytes_out[offset : offset + 16]
                        rendered = ", ".join(self._fmt_imm(value) for value in chunk)
                        self._emit(f"    dc.b {rendered}")
                    self._emit("")

        if self.sound_assets:
            self._emit("-- Sound asset data")
            self._emit("")
            for asset in self.sound_assets:
                self._emit(f"-- sound {asset.kind} {asset.name}")
                self._emit(f"@{asset.data_label}")
                rendered = ", ".join(self._fmt_imm(b) for b in asset.rom_bytes)
                self._emit(f"    dc.b {rendered}")
                self._emit("")

        if self.rom_data_blocks:
            self._emit("-- C const/static const ROM data")
            self._emit("")
            for block in self.rom_data_blocks:
                self._emit(f"-- {block.alias_name}")
                self._emit(f"@{block.label}")
                for offset in range(0, len(block.data), 16):
                    chunk = block.data[offset : offset + 16]
                    rendered = ", ".join(self._fmt_imm(v) for v in chunk)
                    self._emit(f"    dc.b {rendered}")
                self._emit("")

    def _build_asset_loader_impl(self, asset_fn: AssetFunction) -> List[str]:
        function_name = asset_fn.function_name
        frame_label = asset_fn.frame.symbol_name
        arg_slot = self._arg_symbol_name(function_name, "pattern_slot")
        byte_count = len(asset_fn.frame.bytes_out)
        byte_count_imm = self._fmt_imm(byte_count)
        if asset_fn.pattern_mode == "raw":
            base_hi = "0x20"
            slot_mask = "0x7F"
        elif asset_fn.pattern_mode in {"background", "bg_char"}:
            base_hi = "0x20"
            slot_mask = "0x3F"
        else:
            base_hi = "0x28"
            slot_mask = "0x3F"
        return [
            f"    lxi hl,{frame_label}",
            f"    mvi d,{base_hi}",
            "    mvi e,0x00",
            f"    mov a,({arg_slot})",
            f"    ani a,{slot_mask}",
            "    mov b,a",
            f"@{function_name}_slot_loop",
            "    mov a,b",
            "    nei a,0",
            f"    jr {function_name}_slot_done",
            f"    mvi a,{byte_count_imm}",
            "    add a,e",
            "    mov e,a",
            "    aci d,0",
            "    dcr b",
            f"    jre {function_name}_slot_loop",
            f"@{function_name}_slot_done",
            f"    mvi b,{byte_count_imm}",
            f"@{function_name}_copy_loop",
            "    ldaxi (hl)",
            "    stax (de)",
            "    inx de",
            "    dcr b",
            f"    jre {function_name}_copy_loop",
            "    ret",
        ]

    def _build_asset_bulk_loader_impl(
        self, function_name: str, frame_loader_names: List[str]
    ) -> List[str]:
        arg_slot = self._arg_symbol_name(function_name, "pattern_slot")
        base_slot = self._alloc_symbol("scv_asset__tmp_base_slot")
        lines: List[str] = []
        lines.extend(
            [
                f"    mov a,({arg_slot})",
                f"    mov ({base_slot}),a",
            ]
        )
        for index, frame_loader in enumerate(frame_loader_names):
            lines.extend(
                [
                    f"    mov a,({base_slot})",
                    f"    adi a,{self._fmt_imm(index)}",
                    "    mov (scv_asset__arg_pattern_slot),a",
                    f"    call fn_{frame_loader}",
                ]
            )
        lines.append("    ret")
        return lines

    def _build_sound_play_impl(self, function_name: str, asset: SoundAsset) -> List[str]:
        """Build an unrolled play routine that reads all bytes from ROM via DE.

        Correct uPD1771C protocol (from SCV reference code):
          - Sync: wait f2 (VBlank), skit f1 + nop (drain any stale f1)
          - All bytes except last: WRITE byte -> wait f1 (chip ack)
          - Last byte:             WRITE byte -> wait f2 (final ack)
        """
        n = len(asset.rom_bytes)  # total bytes including cmd
        lines: List[str] = [
            f"    lxi de,{asset.data_label}",
            "    lxi hl,0x3600",
            "    di",
            "    mvi b,0xFF",
            f"@{function_name}_wv1",
            "    skit f2",
            f"    jr {function_name}_wv1_wait",
            f"    jmp {function_name}_wv1_done",
            f"@{function_name}_wv1_wait",
            "    dcr b",
            f"    jre {function_name}_wv1",
            f"    jmp {function_name}_wv1_done",
            f"@{function_name}_wv1_done",
            "    skit f1",   # drain any stale f1 — skips nop if f1 set
            "    nop",
        ]
        # All bytes except last: write THEN wait f1
        for i in range(n - 1):
            lines += [
                "    ldax (de)",
                "    stax (hl)",
                "    inx de",
                "    mvi b,0xFF",
                f"@{function_name}_wf{i}",
                "    skit f1",
                f"    jr {function_name}_wf{i}_wait",
                f"    jmp {function_name}_wf{i}_done",
                f"@{function_name}_wf{i}_wait",
                "    dcr b",
                f"    jre {function_name}_wf{i}",
                f"    jmp {function_name}_wf{i}_done",
                f"@{function_name}_wf{i}_done",
            ]
        # Last byte: write THEN wait f2
        lines += [
            "    ldax (de)",
            "    stax (hl)",
            "    mvi b,0xFF",
            f"@{function_name}_wv2",
            "    skit f2",
            f"    jr {function_name}_wv2_wait",
            f"    jmp {function_name}_wv2_done",
            f"@{function_name}_wv2_wait",
            "    dcr b",
            f"    jre {function_name}_wv2",
            f"    jmp {function_name}_wv2_done",
            f"@{function_name}_wv2_done",
            "    ei",
            "    ret",
        ]
        return lines

    def _sanitize_source(
        self,
        source: str,
        *,
        current_path: Optional[Path] = None,
        include_stack: Optional[Set[Path]] = None,
    ) -> str:
        source = re.sub(r"//.*?$", "", source, flags=re.MULTILINE)
        source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)

        if include_stack is None:
            include_stack = set()

        filtered: List[str] = []
        for line in source.splitlines():
            stripped = line.strip()
            self._maybe_bind_pending_function_bank(stripped)
            if stripped.startswith("#"):
                if stripped.startswith("#pragma scv_asset sound"):
                    self._parse_sound_directive(stripped)
                    continue
                if stripped.startswith("#pragma scv_asset"):
                    self._parse_asset_directive(stripped)
                    continue
                if stripped.startswith("#pragma scv_cart_profile"):
                    self._parse_cart_profile_directive(stripped)
                    continue
                if stripped.startswith("#pragma scv_bank_data"):
                    self._parse_bank_data_directive(stripped)
                    continue
                if stripped.startswith("#pragma scv_bank"):
                    self._parse_bank_function_directive(stripped)
                    continue
                if stripped.startswith("#include"):
                    include_match = re.fullmatch(r'#include\s+"([^"]+)"', stripped)
                    if include_match:
                        include_raw = include_match.group(1)
                        if include_raw.endswith(".c") or include_raw.endswith(".h"):
                            if current_path is None:
                                raise ConversionError(
                                    f"#include requires a source path context: {stripped}"
                                )
                            include_path = (current_path.parent / include_raw).resolve()
                            if not include_path.exists():
                                raise ConversionError(
                                    f"Included file not found: {include_raw}"
                                )
                            if include_path in include_stack:
                                raise ConversionError(
                                    f"Recursive include detected for: {include_raw}"
                                )
                            include_stack.add(include_path)
                            include_source = include_path.read_text(encoding="utf-8")
                            # Headers may contain include guards; relax strict
                            # mode so those directives are silently skipped
                            prev_strict = self.strict
                            if include_raw.endswith(".h"):
                                self.strict = False
                            expanded = self._sanitize_source(
                                include_source,
                                current_path=include_path,
                                include_stack=include_stack,
                            )
                            self.strict = prev_strict
                            include_stack.remove(include_path)
                            if expanded:
                                filtered.append(expanded)
                    continue
                if self.strict:
                    raise ConversionError(
                        f"Preprocessor directive not supported in strict mode: {stripped}"
                    )
                continue
            filtered.append(line)

        return "\n".join(filtered)

    def _parse_bank_id(self, raw_bank: str, directive_name: str) -> int:
        try:
            bank_id = int(raw_bank, 0)
        except ValueError as exc:
            raise ConversionError(f"Invalid {directive_name} bank id: {raw_bank}") from exc
        if bank_id < 0:
            raise ConversionError(f"Invalid {directive_name} bank id: {raw_bank}")
        return bank_id

    def _parse_cart_profile_directive(self, line: str) -> None:
        match = re.fullmatch(r"#pragma\s+scv_cart_profile\s+([A-Za-z0-9_]+)\s*", line)
        if not match:
            raise ConversionError(f"Invalid SCV cart profile directive: {line}")
        profile = match.group(1)
        if profile not in self.CART_PROFILES:
            supported = ", ".join(sorted(self.CART_PROFILES))
            raise ConversionError(
                f"Unsupported SCV cart profile '{profile}'. Supported profiles: {supported}"
            )
        self.cart_profile = profile

    def _parse_bank_function_directive(self, line: str) -> None:
        match = re.fullmatch(r"#pragma\s+scv_bank\s+([^\s]+)\s*", line)
        if not match:
            raise ConversionError(f"Invalid SCV bank directive: {line}")
        self.pending_function_bank = self._parse_bank_id(match.group(1), "scv_bank")

    def _parse_bank_data_directive(self, line: str) -> None:
        match = re.fullmatch(
            r"#pragma\s+scv_bank_data(?:\(([^\)]+)\)|\s+([^\s]+))\s+([A-Za-z_][A-Za-z0-9_]*)\s*",
            line,
        )
        if not match:
            raise ConversionError(f"Invalid SCV bank data directive: {line}")
        raw_bank = match.group(1) or match.group(2)
        name = match.group(3)
        self.rom_bank_hints[name] = self._parse_bank_id(raw_bank, "scv_bank_data")

    def _maybe_bind_pending_function_bank(self, stripped_line: str) -> None:
        if self.pending_function_bank is None:
            return
        if not stripped_line or stripped_line.startswith("#"):
            return
        if stripped_line in {"{", "}"}:
            return

        match = re.fullmatch(
            r"(?:[A-Za-z_][A-Za-z0-9_\s\*]*\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\([^;=]*\)\s*(?:\{|)$",
            stripped_line,
        )
        if not match or stripped_line.endswith(";"):
            return

        fn_name = match.group(1)
        if fn_name in {"if", "while", "return", "switch", "for"}:
            return

        self.function_bank_hints[fn_name] = self.pending_function_bank
        self.pending_function_bank = None

    def _validate_bank_assignment(self, bank_id: int, target_name: str) -> None:
        bank_count = int(self.CART_PROFILES[self.cart_profile]["bank_count"])
        if bank_id >= bank_count:
            raise ConversionError(
                f"Bank assignment {bank_id} for '{target_name}' exceeds cart profile '{self.cart_profile}' capacity ({bank_count} banks)"
            )

    def _validate_cart_metadata_targets(self) -> None:
        for fn_name, bank_id in self.function_bank_hints.items():
            if fn_name not in self.defined_functions:
                raise ConversionError(
                    f"SCV bank directive references unknown function '{fn_name}'"
                )
            self._validate_bank_assignment(bank_id, fn_name)

        for alias_name, bank_id in self.rom_bank_hints.items():
            if alias_name not in self.rom_array_labels:
                raise ConversionError(
                    f"SCV bank data directive references unknown ROM array '{alias_name}'"
                )
            self._validate_bank_assignment(bank_id, alias_name)

    def has_cart_metadata(self) -> bool:
        return (
            self.cart_profile != "flat32"
            or bool(self.function_bank_hints)
            or bool(self.rom_bank_hints)
        )

    def get_function_bank(self, fn_name: str) -> int:
        return self.function_bank_hints.get(fn_name, 0)

    def get_banked_call_edges(self) -> List[Dict[str, object]]:
        edges: List[Dict[str, object]] = []
        for caller in sorted(self.function_calls):
            caller_bank = self.get_function_bank(caller)
            for callee in sorted(self.function_calls[caller]):
                if callee not in self.defined_functions:
                    continue
                callee_bank = self.get_function_bank(callee)
                if caller_bank == 0 and callee_bank == 0:
                    continue
                edges.append(
                    {
                        "caller": caller,
                        "caller_bank": caller_bank,
                        "callee": callee,
                        "callee_bank": callee_bank,
                    }
                )
        return edges

    def get_function_trampolines(self) -> List[Dict[str, object]]:
        trampolines: List[Dict[str, object]] = []
        for fn_name in sorted(self.function_bank_hints):
            bank_id = self.function_bank_hints[fn_name]
            if bank_id == 0:
                continue
            trampolines.append(
                {
                    "function": fn_name,
                    "bank": bank_id,
                    "wrapper_label": self.function_wrapper_labels.get(fn_name, f"fn_{fn_name}"),
                    "body_label": self.function_body_labels.get(fn_name, f"fn_{fn_name}__bank_body"),
                    "end_label": self.function_end_labels.get(fn_name, f"fn_{fn_name}_end"),
                    "hook_backend": self.get_cart_hook_backend_name(),
                }
            )
        return trampolines

    def get_trampoline_call_edges(self) -> List[Dict[str, object]]:
        return [
            edge
            for edge in self.get_banked_call_edges()
            if edge["caller_bank"] == 0 and edge["callee_bank"] != 0
        ]

    def get_illegal_banked_call_edges(self) -> List[Dict[str, object]]:
        return [
            edge
            for edge in self.get_banked_call_edges()
            if edge["caller_bank"] != 0
        ]

    def get_cart_hook_backend_name(self) -> str:
        return str(self.CART_PROFILES[self.cart_profile]["hook_backend"])

    def get_cart_metadata(self) -> Dict[str, object]:
        profile_info = self.CART_PROFILES[self.cart_profile]
        return {
            "version": 1,
            "profile": self.cart_profile,
            "bank_count": int(profile_info["bank_count"]),
            "layout": str(profile_info["layout"]),
            "supports_bank_switch": bool(profile_info["supports_bank_switch"]),
            "hook_backend": self.get_cart_hook_backend_name(),
            "status": "metadata-only",
            "notes": [
                "Code generation remains flat ROM; bank assignments are emitted as planning metadata only.",
                "Executable bank packaging is still incomplete; emitted trampolines describe the intended call ABI.",
            ],
            "functions": [
                {"name": fn_name, "bank": self.function_bank_hints.get(fn_name, 0)}
                for fn_name in sorted(self.defined_functions)
            ],
            "rom_data": [
                {
                    "name": alias_name,
                    "bank": self.rom_bank_hints.get(alias_name, 0),
                    "size": self.rom_array_lengths[alias_name],
                }
                for alias_name in sorted(self.rom_array_labels)
            ],
            "explicit_function_banks": dict(sorted(self.function_bank_hints.items())),
            "explicit_rom_banks": dict(sorted(self.rom_bank_hints.items())),
            "trampolines": self.get_function_trampolines(),
            "trampoline_call_edges": self.get_trampoline_call_edges(),
            "illegal_banked_call_edges": self.get_illegal_banked_call_edges(),
            "banked_call_edges": self.get_banked_call_edges(),
        }

    def get_cart_bank_sizes(self) -> List[int]:
        return list(self.CART_BANK_SIZES[self.cart_profile])

    def _get_cart_backend_shadow_symbol(self) -> Optional[str]:
        if self.cart_profile == "flat32":
            return None
        return f"scv_cart__{self.cart_profile}_shadow_bank"

    def _get_cart_runtime_symbols(self) -> List[str]:
        symbols = ["scv_cart__current_bank", "scv_cart__saved_bank"]
        shadow_symbol = self._get_cart_backend_shadow_symbol()
        if shadow_symbol is not None:
            symbols.append(shadow_symbol)
        return symbols

    def _build_cart_hook_impl(self, fn_name: str) -> List[str]:
        backend_name = self.get_cart_hook_backend_name()
        bank_count = int(self.CART_PROFILES[self.cart_profile]["bank_count"])
        shadow_symbol = self._get_cart_backend_shadow_symbol()
        bank_mask = self._fmt_imm((bank_count - 1) & 0xFF)

        if backend_name == "flat32-fixed":
            if fn_name == "scv_cart_select_bank":
                return [
                    "    mvi a,0x00",
                    "    mov (scv_cart__saved_bank),a",
                    "    mov (scv_cart__current_bank),a",
                    "    ret",
                ]
            return [
                "    mvi a,0x00",
                "    mov (scv_cart__current_bank),a",
                "    ret",
            ]

        if shadow_symbol is None:
            raise ConversionError(f"Cart hook backend '{backend_name}' requires a shadow bank symbol")

        if fn_name == "scv_cart_select_bank":
            return [
                f"    -- cart hook backend: {backend_name}",
                "    mov a,(scv_cart__current_bank)",
                "    mov (scv_cart__saved_bank),a",
                "    mov a,({fn}__arg_bank_id)",
                f"    ani a,{bank_mask}",
                f"    mov ({shadow_symbol}),a",
                "    mov (scv_cart__current_bank),a",
                "    ret",
            ]

        return [
            f"    -- cart hook backend: {backend_name}",
            "    mov a,(scv_cart__saved_bank)",
            f"    mov ({shadow_symbol}),a",
            "    mov (scv_cart__current_bank),a",
            "    ret",
        ]

    def _parse_sound_directive(self, line: str) -> None:
        # #pragma scv_asset sound tone name p0 p1 p2 p3
        # #pragma scv_asset sound noise name p0..p9
        match = re.fullmatch(
            r"#pragma\s+scv_asset\s+sound\s+(tone|noise)\s+([A-Za-z_][A-Za-z0-9_]*)\s+(.+)",
            line,
        )
        if not match:
            raise ConversionError(f"Invalid SCV sound asset directive: {line}")
        sound_type, name, params_str = match.groups()
        params = [int(p, 0) for p in params_str.split()]
        if sound_type == "tone" and len(params) != 4:
            raise ConversionError(
                f"Sound asset '{name}' (tone) requires exactly 4 params, got {len(params)}"
            )
        if sound_type == "noise" and len(params) != 10:
            raise ConversionError(
                f"Sound asset '{name}' (noise) requires exactly 10 params, got {len(params)}"
            )
        cmd = 0x02 if sound_type == "tone" else 0x01
        # ROM layout: cmd byte, then all params
        rom_bytes = [cmd] + params
        data_label = f"scv_asset_{name}_data"
        play_fn = f"scv_asset_{name}_play"
        asset = SoundAsset(
            kind=sound_type,
            name=name,
            data_label=data_label,
            play_fn=play_fn,
            rom_bytes=rom_bytes,
        )
        self.sound_assets.append(asset)
        self.function_params[play_fn] = []  # no RAM args
        self.extern_functions.add(play_fn)

    def _parse_asset_directive(self, line: str) -> None:
        match = re.fullmatch(
            r'#pragma\s+scv_asset\s+(sprite|spritesheet|background|backgroundsheet)\s+([A-Za-z_][A-Za-z0-9_]*)\s+"([^"]+)"(?:\s+(\d+)\s+(\d+))?\s*',
            line,
        )
        if not match:
            raise ConversionError(f"Invalid SCV asset directive: {line}")

        kind, name, raw_path, raw_width, raw_height = match.groups()
        if self.source_path is None:
            raise ConversionError("SCV asset directives require a source path")

        asset_path = (self.source_path.parent / raw_path).resolve()
        if kind in {"sprite", "background"}:
            frame_width = 16
            frame_height = 16
        else:
            if raw_width is None or raw_height is None:
                raise ConversionError(
                    f"Spritesheet asset {name} requires frame width and height"
                )
            frame_width = int(raw_width, 10)
            frame_height = int(raw_height, 10)

        try:
            frames = load_png_asset_frames(
                asset_path,
                name=name,
                kind=kind,
                frame_width=frame_width,
                frame_height=frame_height,
            )
        except PngAssetError as exc:
            raise ConversionError(str(exc)) from exc

        self.asset_directives.append(
            AssetDirective(
                kind=kind,
                name=name,
                source_path=asset_path,
                frames=frames,
            )
        )
        frame_loader_names: List[str] = []
        is_background_asset = kind in {"background", "backgroundsheet"}
        for frame in frames:
            function_name = frame.loader_name
            frame_loader_names.append(function_name)
            pattern_mode = "background"
            if is_background_asset and len(frame.bytes_out) == 16:
                pattern_mode = "bg_char"
            elif not is_background_asset:
                pattern_mode = "sprite"
            self.asset_functions[function_name] = AssetFunction(
                function_name=function_name,
                frame=frame,
                pattern_mode=pattern_mode,
            )
            self.function_params[function_name] = ["pattern_slot"]
            self.extern_functions.add(function_name)

            if not is_background_asset:
                raw_function_name = f"{frame.loader_name}_raw"
                self.asset_functions[raw_function_name] = AssetFunction(
                    function_name=raw_function_name,
                    frame=frame,
                    pattern_mode="raw",
                )
                self.function_params[raw_function_name] = ["pattern_slot"]
                self.extern_functions.add(raw_function_name)

        if kind in {"spritesheet", "backgroundsheet"}:
            bulk_loader_name = f"scv_asset_{name}_load_all"
            self.asset_bulk_functions[bulk_loader_name] = frame_loader_names
            self.function_params[bulk_loader_name] = ["pattern_slot"]

    def _new_label(self, prefix: str) -> str:
        self.label_counter += 1
        return f"{prefix}_{self.label_counter}"

    def _arg_symbol_name(self, fn_name: str, param_name: str) -> str:
        # Asset loaders are often emitted in large batches; share one caller arg slot
        # for their single pattern_slot parameter to avoid RAM symbol explosion.
        if fn_name.startswith("scv_asset_") and param_name == "pattern_slot":
            return "scv_asset__arg_pattern_slot"

        # Share slots by argument position for most SCV APIs.
        api_params = self.SCV_API_PARAMS.get(fn_name)
        if (
            api_params is not None
            and fn_name not in self.NON_SHARED_API_ARG_FUNCTIONS
            and param_name in api_params
        ):
            return f"scv_api__arg_{api_params.index(param_name)}"

        return f"{fn_name}__arg_{param_name}"

    def _format_impl_line(self, fn_name: str, line: str) -> str:
        rendered = line.format(fn=fn_name)
        for param_name in self.function_params.get(fn_name, []):
            default_sym = f"{fn_name}__arg_{param_name}"
            mapped_sym = self._arg_symbol_name(fn_name, param_name)
            if mapped_sym != default_sym:
                rendered = rendered.replace(default_sym, mapped_sym)
        return rendered

    def _emit(self, line: str = "") -> None:
        self.lines.append(line)

    def _emit_add_a_to_hl(self) -> None:
        self._emit("    add a,l")
        self._emit("    mov l,a")
        self._emit("    aci h,0")

    def _emit_mul_a_by_const(self, factor: int) -> None:
        if factor < 0 or factor > 0xFF:
            raise ConversionError(f"Unsupported constant multiply factor {factor}")
        if factor == 0:
            self._emit("    mvi a,0x00")
            return
        if factor == 1:
            return

        self._emit("    mov b,a")
        first_term = True
        for bit in range(8):
            if (factor & (1 << bit)) == 0:
                continue
            self._emit("    mov a,b")
            for _ in range(bit):
                self._emit("    add a,a")
            if first_term:
                self._emit("    mov d,a")
                first_term = False
            else:
                self._emit("    add a,d")
                self._emit("    mov d,a")
        self._emit("    mov a,d")

    def _unsupported(self, node: c_ast.Node, message: str) -> None:
        if self.strict:
            coord = getattr(node, "coord", "unknown")
            raise ConversionError(f"{message} at {coord}")
        self._emit(f"    -- TODO unsupported: {message}")

    def _alloc_symbol(self, name: str, init: int = 0) -> str:
        owner_fn = self._symbol_owner_function(name)
        if owner_fn is None:
            if name not in self.global_symbol_offsets:
                self.global_symbol_offsets[name] = len(self.global_symbol_offsets)
                self.global_data_symbols.append(name)
            return name

        frame_offsets = self.frame_symbol_offsets.setdefault(owner_fn, {})
        if name not in frame_offsets:
            frame_offsets[name] = len(frame_offsets)
            self.frame_data_symbols.setdefault(owner_fn, []).append(name)
        return name

    def _symbol_owner_function(self, name: str) -> Optional[str]:
        if "__" not in name:
            return None
        prefix = name.split("__", 1)[0]
        if prefix in self.defined_functions:
            return prefix
        return None

    def _alloc_temp_symbol(self, name: str) -> str:
        if self.current_fn is None:
            return self._alloc_symbol(name)
        return self._alloc_symbol(f"{self.current_fn.name}__{name}")

    def _finalize_symbol_layout(self) -> None:
        self.global_size_total = len(self.global_data_symbols)
        frame_sizes = {
            fn: len(self.frame_data_symbols.get(fn, []))
            for fn in self.defined_functions
        }
        self.frame_sizes_by_function = dict(frame_sizes)

        callers: Dict[str, Set[str]] = {fn: set() for fn in self.defined_functions}
        for caller, callees in self.function_calls.items():
            for callee in callees:
                if callee in callers:
                    callers[callee].add(caller)

        memo: Dict[str, int] = {}
        visiting: Set[str] = set()

        def prefix_size(fn: str) -> int:
            if fn in memo:
                return memo[fn]
            if fn in visiting:
                raise ConversionError(
                    "Recursive user-defined function calls are not supported by the current RAM frame allocator"
                )
            visiting.add(fn)
            best = 0
            for caller in callers.get(fn, set()):
                best = max(best, prefix_size(caller) + frame_sizes.get(caller, 0))
            visiting.remove(fn)
            memo[fn] = best
            return best

        frame_bases: Dict[str, int] = {}
        frame_area = 0
        for fn in sorted(self.defined_functions):
            prefix = prefix_size(fn)
            frame_bases[fn] = self.global_size_total + prefix
            frame_area = max(frame_area, prefix + frame_sizes.get(fn, 0))

        total_ram = self.global_size_total + frame_area
        if total_ram == 0:
            ram_top = self.ram_base - 1
        else:
            ram_top = self.ram_base + total_ram - 1
        if ram_top >= self.STACK_INIT:
            raise ConversionError(
                f"RAM symbol overflow: top address 0x{ram_top:04X} collides with stack at 0x{self.STACK_INIT:04X}. "
                "Reduce symbols, lower --ram-base, or adjust stack init."
            )

        self.frame_size_total = frame_area
        self.symbol_values = {}
        self.data_symbols = []

        for index, sym in enumerate(self.global_data_symbols):
            self.symbol_values[sym] = self.ram_base + index
            self.data_symbols.append(sym)

        for fn in sorted(self.defined_functions, key=lambda item: (frame_bases[item], item)):
            base_addr = self.ram_base + frame_bases[fn]
            for sym in self.frame_data_symbols.get(fn, []):
                offset = self.frame_symbol_offsets[fn][sym]
                self.symbol_values[sym] = base_addr + offset
                self.data_symbols.append(sym)

    def _declare_global(self, decl: c_ast.Decl) -> None:
        self._ensure_known_types_from_decl(decl)

        if decl.name is None:
            return

        # extern variable declarations are forward declarations, not definitions
        is_extern = "extern" in (decl.storage or [])
        if is_extern:
            return

        if decl.name in self.globals:
            raise ConversionError(f"Duplicate global declaration: {decl.name}")

        self.globals.add(decl.name)

        is_const = self._is_const_decl(decl)
        is_static = "static" in (decl.storage or [])
        if is_static and not is_const:
            coord = getattr(decl, "coord", "unknown")
            raise ConversionError(
                f"Writable static global '{decl.name}' is not supported at {coord}. "
                "Use const/static const for ROM data or a normal mutable variable for RAM."
            )

        if isinstance(decl.type, c_ast.ArrayDecl):
            if is_const:
                values = self._eval_const_array_u8(decl, decl.init)
                dims = self._extract_array_dims(decl.type)
                self._register_rom_data_block(decl.name, values, dims)
                if self._decl_is_signed_char(decl):
                    self.signed_rom_arrays.add(decl.name)
                return

            if decl.init is not None:
                coord = getattr(decl, "coord", "unknown")
                raise ConversionError(
                    f"Mutable global array '{decl.name}' initializer is not supported at {coord}. "
                    "Declare the buffer without initializer and fill it at runtime."
                )

            if decl.type.dim is None:
                coord = getattr(decl, "coord", "unknown")
                raise ConversionError(
                    f"Mutable global array '{decl.name}' requires an explicit size at {coord}"
                )

            length = self._eval_const_u8(decl.type.dim)
            struct_type = self._extract_struct_type_from_decl(decl)
            if struct_type is not None:
                struct_name = struct_type.name
                if struct_name is None:
                    coord = getattr(decl, "coord", "unknown")
                    raise ConversionError(
                        f"Anonymous struct array '{decl.name}' is not supported at {coord}"
                    )
                struct_size = self.struct_sizes.get(struct_name)
                if struct_size is None:
                    self._compute_struct_layout(struct_name, struct_type)
                    struct_size = self.struct_sizes.get(struct_name)
                if struct_size is None:
                    coord = getattr(decl, "coord", "unknown")
                    raise ConversionError(
                        f"Could not determine struct size for '{struct_name}' at {coord}"
                    )
                self._alloc_ram_array(decl.name, length, struct_size, struct_name)
                self.user_global_array_aliases.add(decl.name)
            else:
                self._alloc_ram_array(decl.name, length)
                self.user_global_array_aliases.add(decl.name)
            if self._decl_is_signed_char(decl):
                self.signed_ram_arrays.add(decl.name)
            return

        struct_type = self._extract_struct_type_from_decl(decl)
        if struct_type is not None:
            fields = self._flatten_struct_fields(struct_type)
            self._alloc_struct_instance(decl.name, fields)
            self.user_global_struct_aliases.add(decl.name)
            return

        if not isinstance(decl.type, c_ast.TypeDecl):
            self._unsupported(decl, "Only scalar global declarations are supported")
            return

        if is_const:
            if decl.init is None:
                coord = getattr(decl, "coord", "unknown")
                raise ConversionError(
                    f"const global '{decl.name}' requires an initializer at {coord}"
                )
            self.rom_constants[decl.name] = self._eval_const_u8(decl.init)
            if self._decl_is_signed_char(decl):
                self.signed_symbols.add(decl.name)
            return

        self._alloc_symbol(decl.name)
        if self._decl_is_signed_char(decl):
            self.signed_symbols.add(decl.name)
        self.user_global_scalar_names.add(decl.name)

    def _insert_symbol_table(self) -> None:
        symbol_lines: List[str] = []
        if self.data_symbols:
            symbol_lines.append("-- auto-allocated RAM symbols")
            for sym in self.data_symbols:
                symbol_lines.append(f"local {sym} = 0x{self.symbol_values[sym]:04X}")
        else:
            symbol_lines.append("-- no RAM symbols allocated")

        if self.rom_constants:
            symbol_lines.append("")
            symbol_lines.append("-- ROM constants (encoded as immediates)")
            for name in sorted(self.rom_constants):
                symbol_lines.append(f"-- const {name} = {self._fmt_imm(self.rom_constants[name])}")

        if self.rom_data_blocks:
            symbol_lines.append("")
            symbol_lines.append("-- ROM data blocks (const/static const arrays)")
            for block in self.rom_data_blocks:
                symbol_lines.append(
                    f"-- {block.alias_name} -> @{block.label} ({len(block.data)} bytes)"
                )

        out: List[str] = []
        for line in self.lines:
            if line == "__SYMBOL_TABLE__":
                out.extend(symbol_lines)
            else:
                out.append(line)
        self.lines = out

    def _resolve_symbol(self, name: str) -> str:
        if self.current_fn and f"{self.current_fn.name}__{name}" in self.struct_instances:
            raise ConversionError(f"Struct variable '{name}' requires field access (use {name}.field)")
        if name in self.struct_instances:
            raise ConversionError(f"Struct variable '{name}' requires field access (use {name}.field)")
        if self.current_fn and f"{self.current_fn.name}__{name}" in self.rom_constants:
            return f"{self.current_fn.name}__{name}"
        if name in self.rom_constants:
            return name
        if self.current_fn and name in self.current_fn.param_symbols:
            return self.current_fn.param_symbols[name]
        if name in self.symbol_values:
            return name
        if self.current_fn:
            frame_name = f"{self.current_fn.name}__{name}"
            if frame_name in self.frame_symbol_offsets.get(self.current_fn.name, {}):
                return frame_name
        if name in self.globals:
            return self._alloc_symbol(name)
        if self.current_fn:
            local_name = f"{self.current_fn.name}__{name}"
            return self._alloc_symbol(local_name)
        raise ConversionError(f"Unknown symbol: {name}")

    def _eval_const_u8(self, expr: c_ast.Node) -> int:
        if isinstance(expr, c_ast.Constant) and expr.type in {"int", "char"}:
            if expr.type == "int":
                raw = int(expr.value, 0)
            else:
                text = expr.value
                if len(text) < 2 or text[0] != "'" or text[-1] != "'":
                    coord = getattr(expr, "coord", "unknown")
                    raise ConversionError(f"Unsupported char literal {text} at {coord}")
                inner = text[1:-1]
                decoded = bytes(inner, "utf-8").decode("unicode_escape")
                if len(decoded) != 1:
                    coord = getattr(expr, "coord", "unknown")
                    raise ConversionError(
                        f"Only single-byte char literals are supported ({text}) at {coord}"
                    )
                raw = ord(decoded)
            if not (0 <= raw <= 255):
                coord = getattr(expr, "coord", "unknown")
                raise ConversionError(
                    f"Constant {raw} (0x{raw:X}) exceeds 8-bit range at {coord}"
                )
            return raw

        if isinstance(expr, c_ast.UnaryOp) and expr.op in {"+", "-"}:
            v = self._eval_const_u8(expr.expr)
            if expr.op == "+":
                return v
            return (-v) & 0xFF

        if isinstance(expr, c_ast.ID):
            resolved = self._resolve_symbol(expr.name)
            if resolved in self.rom_constants:
                return self.rom_constants[resolved]

        if isinstance(expr, c_ast.BinaryOp):
            left = self._eval_const_u8(expr.left)
            right = self._eval_const_u8(expr.right)
            op = expr.op

            if op == "+":
                return (left + right) & 0xFF
            if op == "-":
                return (left - right) & 0xFF
            if op == "*":
                return (left * right) & 0xFF
            if op == "&":
                return left & right
            if op == "|":
                return left | right
            if op == "^":
                return left ^ right
            if op == "<<":
                return (left << (right & 0x07)) & 0xFF
            if op == ">>":
                return (left >> (right & 0x07)) & 0xFF
            if op == "==":
                return 1 if left == right else 0
            if op == "!=":
                return 1 if left != right else 0
            if op == "<":
                return 1 if left < right else 0
            if op == ">":
                return 1 if left > right else 0
            if op == "<=":
                return 1 if left <= right else 0
            if op == ">=":
                return 1 if left >= right else 0
            if op == "&&":
                return 1 if (left != 0 and right != 0) else 0
            if op == "||":
                return 1 if (left != 0 or right != 0) else 0

        coord = getattr(expr, "coord", "unknown")
        raise ConversionError(
            f"Initializer must be an 8-bit constant expression at {coord}"
        )

    def _is_const_decl(self, decl: c_ast.Decl) -> bool:
        if "const" in (decl.quals or []):
            return True
        t = decl.type
        while t is not None:
            quals = getattr(t, "quals", None)
            if quals and "const" in quals:
                return True
            t = getattr(t, "type", None)
        return False

    def _eval_const_array_u8(self, decl: c_ast.Decl, init: Optional[c_ast.Node]) -> List[int]:
        if not isinstance(decl.type, c_ast.ArrayDecl):
            coord = getattr(decl, "coord", "unknown")
            raise ConversionError(f"Expected array declaration at {coord}")

        dims: List[Optional[int]] = []
        t = decl.type
        while isinstance(t, c_ast.ArrayDecl):
            if t.dim is None:
                dims.append(None)
            else:
                dims.append(self._eval_const_u8(t.dim))
            t = t.type

        expected_len: Optional[int] = None
        if dims and all(dim is not None for dim in dims):
            total = 1
            for dim in dims:
                assert dim is not None
                total *= dim
            expected_len = total

        if init is None:
            coord = getattr(decl, "coord", "unknown")
            raise ConversionError(
                f"const array '{decl.name}' requires an initializer at {coord}"
            )

        values: List[int]
        if isinstance(init, c_ast.InitList):
            if dims and all(isinstance(d, int) for d in dims):
                values = self._flatten_const_array_init_for_dims_u8(init, dims)
            else:
                values = self._flatten_const_array_init_u8(init)
        elif isinstance(init, c_ast.Constant) and init.type == "string":
            raw = init.value
            if len(raw) < 2 or raw[0] != '"' or raw[-1] != '"':
                coord = getattr(init, "coord", "unknown")
                raise ConversionError(f"Unsupported string literal {raw} at {coord}")
            decoded = bytes(raw[1:-1], "utf-8").decode("unicode_escape")
            values = [ord(ch) & 0xFF for ch in decoded]
            values.append(0)
        else:
            coord = getattr(init, "coord", "unknown")
            raise ConversionError(
                f"Array initializer for '{decl.name}' must be {{...}} or string literal at {coord}"
            )

        if expected_len is not None:
            if len(values) > expected_len:
                coord = getattr(init, "coord", "unknown")
                raise ConversionError(
                    f"Array initializer for '{decl.name}' has {len(values)} bytes but size is {expected_len} at {coord}"
                )
            if len(values) < expected_len:
                values.extend([0] * (expected_len - len(values)))

        return values

    def _flatten_const_array_init_u8(self, init: c_ast.InitList) -> List[int]:
        values: List[int] = []
        for expr in (init.exprs or []):
            if isinstance(expr, c_ast.InitList):
                values.extend(self._flatten_const_array_init_u8(expr))
            else:
                values.append(self._eval_const_u8(expr))
        return values

    def _flatten_const_array_init_for_dims_u8(self, init: c_ast.InitList, dims: List[int]) -> List[int]:
        """Flatten const array initializer honoring dimensions and C string rules.

        Supports forms like:
          const unsigned char table[12][14] = { "...", "..." };
        by expanding each row to exactly 14 bytes with zero padding when needed.
        """
        if not dims:
            return self._flatten_const_array_init_u8(init)

        def decode_string(expr: c_ast.Constant) -> List[int]:
            raw = expr.value
            coord = getattr(expr, "coord", "unknown")
            if len(raw) < 2 or raw[0] != '"' or raw[-1] != '"':
                raise ConversionError(f"Unsupported string literal {raw} at {coord}")
            decoded = bytes(raw[1:-1], "utf-8").decode("unicode_escape")
            return [ord(ch) & 0xFF for ch in decoded]

        def dim_product(ds: List[int]) -> int:
            total = 1
            for d in ds:
                total *= d
            return total

        def flatten_node(node: c_ast.Node, shape: List[int]) -> List[int]:
            coord = getattr(node, "coord", "unknown")
            if len(shape) == 1:
                width = shape[0]
                if not isinstance(width, int):
                    raise ConversionError(
                        f"Array row width must be an integer constant, got {width!r} at {coord}"
                    )
                if isinstance(node, c_ast.Constant) and node.type == "string":
                    vals = decode_string(node)
                    if len(vals) > width:
                        raise ConversionError(
                            f"String initializer has {len(vals)} bytes but row size is {width} at {coord}"
                        )
                    return vals + ([0] * (width - len(vals)))
                if isinstance(node, c_ast.InitList):
                    vals: List[int] = []
                    for expr in node.exprs or []:
                        if isinstance(expr, c_ast.Constant) and expr.type == "string":
                            vals.extend(decode_string(expr))
                        elif isinstance(expr, c_ast.InitList):
                            vals.extend(self._flatten_const_array_init_u8(expr))
                        else:
                            vals.append(self._eval_const_u8(expr))
                    if len(vals) > width:
                        raise ConversionError(
                            f"Array initializer row has {len(vals)} bytes but row size is {width} at {coord}"
                        )
                    return vals + ([0] * (width - len(vals)))
                # Scalar for 1D row element
                return [self._eval_const_u8(node)]

            if not isinstance(node, c_ast.InitList):
                raise ConversionError(f"Expected '{{...}}' initializer at {coord}")

            outer = shape[0]
            tail = shape[1:]
            row_size = dim_product(tail)
            rows: List[int] = []
            exprs = node.exprs or []
            if len(exprs) > outer:
                raise ConversionError(
                    f"Array initializer has {len(exprs)} rows but size is {outer} at {coord}"
                )
            for expr in exprs:
                row_vals = flatten_node(expr, tail)
                if len(row_vals) != row_size:
                    if len(row_vals) > row_size:
                        raise ConversionError(
                            f"Array initializer row has {len(row_vals)} bytes but expected {row_size} at {coord}"
                        )
                    row_vals = row_vals + ([0] * (row_size - len(row_vals)))
                rows.extend(row_vals)
            missing = outer - len(exprs)
            if missing > 0:
                rows.extend([0] * (missing * row_size))
            return rows

        return flatten_node(init, dims)

    def _register_rom_data_block(self, alias_name: str, values: List[int], dims: Optional[List[int]] = None) -> None:
        label = f"{alias_name}__rom"
        self.rom_data_blocks.append(
            RomDataBlock(alias_name=alias_name, label=label, data=values)
        )
        self.rom_array_labels[alias_name] = label
        self.rom_array_lengths[alias_name] = len(values)
        if dims is not None:
            self.rom_array_dims[alias_name] = dims
        self.rom_array_values[alias_name] = list(values)

    def _alloc_ram_array(
        self,
        alias_name: str,
        length: int,
        element_size: int = 1,
        struct_type_name: Optional[str] = None,
    ) -> None:
        if length <= 0:
            raise ConversionError(f"RAM array '{alias_name}' must have size > 0")
        if element_size <= 0:
            raise ConversionError(f"RAM array '{alias_name}' element size must have size > 0")
        if alias_name in self.ram_array_labels:
            return
        total_bytes = length * element_size
        base_symbol = self._alloc_symbol(f"{alias_name}__ram_0")
        for idx in range(1, total_bytes):
            self._alloc_symbol(f"{alias_name}__ram_{idx}")
        self.ram_array_labels[alias_name] = base_symbol
        self.ram_array_lengths[alias_name] = length
        self.ram_array_byte_lengths[alias_name] = total_bytes
        self.ram_array_element_sizes[alias_name] = element_size
        if struct_type_name is not None:
            self.ram_array_struct_types[alias_name] = struct_type_name

    def _extract_array_dims(self, array_decl: c_ast.ArrayDecl) -> List[int]:
        """Extract array dimensions from nested ArrayDecl nodes."""
        dims: List[int] = []
        t = array_decl
        while isinstance(t, c_ast.ArrayDecl):
            if t.dim is not None:
                dims.append(self._eval_const_u8(t.dim))
            t = t.type
        return dims

    def _register_enum(self, enum_node: c_ast.Enum) -> None:
        if enum_node.values is None:
            return
        current = 0
        for enumerator in enum_node.values.enumerators:
            if enumerator.value is not None:
                current = self._eval_const_u8(enumerator.value)
            self.rom_constants[enumerator.name] = current & 0xFF
            current = (current + 1) & 0xFF

    def _register_struct(self, struct_node: c_ast.Struct) -> None:
        if struct_node.name is None or struct_node.decls is None:
            return
        self.struct_defs[struct_node.name] = self._flatten_struct_fields(struct_node)
        # Also compute struct size and field offsets
        self._compute_struct_layout(struct_node.name, struct_node)

    def _flatten_struct_fields(self, struct_node: c_ast.Struct, prefix: str = "") -> List[str]:
        if struct_node.decls is None:
            if struct_node.name and struct_node.name in self.struct_defs:
                return [prefix + f for f in self.struct_defs[struct_node.name]]
            coord = getattr(struct_node, "coord", "unknown")
            raise ConversionError(
                f"Incomplete/unknown struct type '{struct_node.name}' at {coord}"
            )

        fields: List[str] = []
        for field in struct_node.decls:
            if field.name is None:
                coord = getattr(field, "coord", "unknown")
                raise ConversionError(f"Unnamed struct field at {coord}")
            field_prefix = prefix + field.name
            if isinstance(field.type, c_ast.TypeDecl):
                ftype = field.type.type
                if isinstance(ftype, c_ast.Struct):
                    if ftype.decls is not None and ftype.name is not None:
                        self.struct_defs[ftype.name] = self._flatten_struct_fields(ftype)
                    nested = self._flatten_struct_fields(ftype, field_prefix + "__")
                    fields.extend(nested)
                else:
                    if isinstance(ftype, c_ast.Enum):
                        self._register_enum(ftype)
                    fields.append(field_prefix)
            else:
                coord = getattr(field, "coord", "unknown")
                raise ConversionError(
                    f"Only scalar or nested-struct fields are supported ('{field.name}') at {coord}"
                )
        return fields

    def _compute_struct_layout(self, struct_name: str, struct_node: c_ast.Struct) -> None:
        """Compute struct size and field offsets for array[index].field access."""
        if struct_node.decls is None:
            return
        
        offset = 0
        field_offsets: Dict[str, int] = {}
        
        for field in struct_node.decls:
            if field.name is None:
                continue
            size = self._sizeof_field(field)
            field_offsets[field.name] = offset
            offset += size
        
        self.struct_sizes[struct_name] = offset
        self.struct_field_offsets[struct_name] = field_offsets
    
    def _sizeof_field(self, field: c_ast.Decl) -> int:
        """Compute the size in bytes of a struct field."""
        # Simple type sizes - assumes 8-bit CPU with 16-bit ints
        type_node = field.type
        
        # Unwrap TypeDecl
        while isinstance(type_node, c_ast.TypeDecl):
            type_node = type_node.type
        
        # Handle IdentifierType (basic types like char, int, unsigned char, etc.)
        if isinstance(type_node, c_ast.IdentifierType):
            typename = " ".join(type_node.names)
            if "char" in typename:
                return 1
            elif "int" in typename:
                return 2  # 16-bit int for 8-bit CPU
            else:
                return 1  # Default to 1 byte
        
        # Handle Struct fields
        if isinstance(type_node, c_ast.Struct):
            if type_node.name and type_node.name in self.struct_sizes:
                return self.struct_sizes[type_node.name]
            # If we haven't computed it yet, compute it now
            if type_node.name and type_node.decls is not None:
                self._compute_struct_layout(type_node.name, type_node)
                return self.struct_sizes.get(type_node.name, 1)
            return 1  # Unknown size defaults to 1
        
        return 1  # Default size

    def _ensure_known_types_from_decl(self, decl: c_ast.Decl) -> None:
        t: Optional[c_ast.Node] = decl.type
        while t is not None:
            if isinstance(t, c_ast.TypeDecl):
                if isinstance(t.type, c_ast.Enum):
                    self._register_enum(t.type)
                elif isinstance(t.type, c_ast.Struct):
                    self._register_struct(t.type)
            elif isinstance(t, c_ast.Enum):
                self._register_enum(t)
            elif isinstance(t, c_ast.Struct):
                self._register_struct(t)
            t = getattr(t, "type", None)

    def _extract_struct_type_from_decl(self, decl: c_ast.Decl) -> Optional[c_ast.Struct]:
        t: Optional[c_ast.Node] = decl.type
        while t is not None:
            if isinstance(t, c_ast.TypeDecl) and isinstance(t.type, c_ast.Struct):
                return t.type
            t = getattr(t, "type", None)
        return None

    def _type_node_is_signed_char(self, type_node: Optional[c_ast.Node]) -> bool:
        t = type_node
        while t is not None:
            if isinstance(t, c_ast.TypeDecl):
                t = t.type
                continue
            if isinstance(t, c_ast.ArrayDecl):
                t = t.type
                continue
            break

        if not isinstance(t, c_ast.IdentifierType):
            return False

        names = set(t.names)
        return "signed" in names and "char" in names and "unsigned" not in names

    def _decl_is_signed_char(self, decl: c_ast.Decl) -> bool:
        return self._type_node_is_signed_char(decl.type)

    def _alloc_struct_instance(self, alias: str, fields: List[str]) -> None:
        mapping: Dict[str, str] = {}
        for field in fields:
            sym = self._alloc_symbol(f"{alias}__{field}")
            mapping[field] = sym
        self.struct_instances[alias] = mapping

    def _split_struct_ref(self, struct_ref: c_ast.StructRef) -> Tuple[str, str]:
        if struct_ref.type != '.':
            self._unsupported(struct_ref, "Only '.' struct access is supported")
            return "", ""
        if not isinstance(struct_ref.field, c_ast.ID):
            self._unsupported(struct_ref, "Only named struct fields are supported")
            return "", ""

        field_name = struct_ref.field.name
        if isinstance(struct_ref.name, c_ast.ID):
            return struct_ref.name.name, field_name
        if isinstance(struct_ref.name, c_ast.StructRef):
            base, path = self._split_struct_ref(struct_ref.name)
            return base, f"{path}__{field_name}"

        self._unsupported(struct_ref, "Array-indexed struct field access (e.g., actors[i].field) not yet supported - use temporary variables instead")
        return "", ""

    def _resolve_struct_field_symbol(self, struct_ref: c_ast.StructRef) -> str:
        base, field = self._split_struct_ref(struct_ref)
        alias: Optional[str] = None
        if self.current_fn is not None:
            scoped = f"{self.current_fn.name}__{base}"
            if scoped in self.struct_instances:
                alias = scoped
        if alias is None and base in self.struct_instances:
            alias = base
        if alias is None:
            coord = getattr(struct_ref, "coord", "unknown")
            raise ConversionError(f"Unknown struct variable '{base}' at {coord}")

        mapping = self.struct_instances[alias]
        if field not in mapping:
            coord = getattr(struct_ref, "coord", "unknown")
            raise ConversionError(
                f"Struct '{base}' has no field '{field}' at {coord}"
            )
        return mapping[field]

    def _resolve_rom_array_alias(self, name: str) -> Optional[str]:
        if self.current_fn is not None:
            scoped = f"{self.current_fn.name}__{name}"
            if scoped in self.rom_array_labels:
                return scoped
        if name in self.rom_array_labels:
            return name
        return None

    def _resolve_ram_array_alias(self, name: str) -> Optional[str]:
        if self.current_fn is not None:
            scoped = f"{self.current_fn.name}__{name}"
            if scoped in self.ram_array_labels:
                return scoped
        if name in self.ram_array_labels:
            return name
        return None

    def _expr_is_signed_char(self, expr: c_ast.Node) -> bool:
        if isinstance(expr, c_ast.ID):
            try:
                sym = self._resolve_symbol(expr.name)
            except ConversionError:
                return False
            return sym in self.signed_symbols

        if isinstance(expr, c_ast.ArrayRef):
            if isinstance(expr.name, c_ast.ID):
                ram_alias = self._resolve_ram_array_alias(expr.name.name)
                if ram_alias is not None:
                    return ram_alias in self.signed_ram_arrays
                rom_alias = self._resolve_rom_array_alias(expr.name.name)
                if rom_alias is not None:
                    return rom_alias in self.signed_rom_arrays
            return False

        if isinstance(expr, c_ast.StructRef):
            try:
                sym = self._resolve_struct_field_symbol(expr)
            except ConversionError:
                return False
            return sym in self.signed_symbols

        if isinstance(expr, c_ast.UnaryOp):
            if expr.op == "-":
                return True
            if expr.op in {"+", "p++", "p--", "*"}:
                return self._expr_is_signed_char(expr.expr)
            return False

        if isinstance(expr, c_ast.BinaryOp):
            if expr.op in {"+", "-", "*", "&", "|", "^", "<<", ">>"}:
                return self._expr_is_signed_char(expr.left) or self._expr_is_signed_char(expr.right)
            return False

        if isinstance(expr, c_ast.FuncCall):
            if not isinstance(expr.name, c_ast.ID):
                return False
            callee = self.API_ALIASES.get(expr.name.name, expr.name.name)
            return callee in self.signed_returning_functions

        return False

    def _emit_function(self, func: c_ast.FuncDef) -> None:
        fn_name = func.decl.name
        fn = f"fn_{fn_name}"
        fn_bank = self.get_function_bank(fn_name)
        body_label = fn if fn_bank == 0 else f"{fn}__bank_body"
        end_label = self._new_label(f"{fn}_end")
        self.function_wrapper_labels[fn_name] = fn
        self.function_body_labels[fn_name] = body_label
        self.function_end_labels[fn_name] = end_label
        param_symbols: Dict[str, str] = {}
        for param_name in self.function_params.get(fn_name, []):
            slot = self._alloc_symbol(self._arg_symbol_name(fn_name, param_name))
            param_symbols[param_name] = slot
            if param_name in self.signed_param_names_by_function.get(fn_name, set()):
                self.signed_symbols.add(slot)

        self.current_fn = FunctionContext(
            name=fn_name,
            end_label=end_label,
            param_symbols=param_symbols,
        )

        if fn_bank != 0:
            self.extern_functions.add("scv_cart_select_bank")
            self.extern_functions.add("scv_cart_restore_bank")
            if "scv_cart_select_bank" not in self.function_params:
                self.function_params["scv_cart_select_bank"] = self.SCV_API_PARAMS["scv_cart_select_bank"]
            if "scv_cart_restore_bank" not in self.function_params:
                self.function_params["scv_cart_restore_bank"] = self.SCV_API_PARAMS["scv_cart_restore_bank"]

            bank_slot = self._alloc_symbol(self._arg_symbol_name("scv_cart_select_bank", "bank_id"))
            self._emit(f"@{fn}")
            self._emit(f"    mvi a,{self._fmt_imm(fn_bank)}")
            self._emit(f"    mov ({bank_slot}),a")
            self._emit("    call fn_scv_cart_select_bank")
            self._emit(f"    call {body_label}")
            self._emit("    call fn_scv_cart_restore_bank")
            self._emit("    ret")
            self._emit("")

        self._emit(f"@{body_label}")

        if self.current_fn.param_symbols:
            self._emit("    -- args are preloaded by caller")
            for param_name, sym in self.current_fn.param_symbols.items():
                self._emit(f"    -- {param_name} -> ({sym})")

        self._emit_stmt(func.body)
        self._emit(f"@{end_label}")
        self._emit("    ret")
        self._emit("")

        self.current_fn = None

    def _emit_stmt(self, node: c_ast.Node) -> None:
        if isinstance(node, c_ast.Compound):
            for item in node.block_items or []:
                self._emit_stmt(item)
            return

        if isinstance(node, c_ast.DeclList):
            for decl in node.decls:
                self._emit_stmt(decl)
            return

        if isinstance(node, c_ast.Decl):
            self._emit_decl(node)
            return

        if isinstance(node, c_ast.Assignment):
            self._emit_assignment(node)
            return

        if isinstance(node, c_ast.Return):
            if node.expr is not None:
                self._emit_expr_to_a(node.expr)
            if self.current_fn:
                self._emit(f"    jmp {self.current_fn.end_label}")
            else:
                self._emit("    ret")
            return

        if isinstance(node, c_ast.FuncCall):
            self._emit_call(node)
            return

        if isinstance(node, c_ast.If):
            self._emit_if(node)
            return

        if isinstance(node, c_ast.While):
            self._emit_while(node)
            return

        if isinstance(node, c_ast.For):
            self._emit_for(node)
            return

        if isinstance(node, c_ast.Break):
            if not self.loop_end_labels:
                self._unsupported(node, "break outside loop")
                return
            self._emit(f"    jmp {self.loop_end_labels[-1]}")
            return

        if isinstance(node, c_ast.UnaryOp):
            # Unary ops as statements (e.g., `!x;` or `-y;`) - just evaluate and discard
            self._emit_expr_to_a(node)
            return

        self._unsupported(node, f"Statement type {type(node).__name__}")

    def _emit_decl(self, decl: c_ast.Decl) -> None:
        self._ensure_known_types_from_decl(decl)

        if decl.name is None:
            return

        is_const = self._is_const_decl(decl)
        is_static = "static" in (decl.storage or [])
        if is_static and not is_const:
            coord = getattr(decl, "coord", "unknown")
            raise ConversionError(
                f"Writable static local '{decl.name}' is not supported at {coord}. "
                "Use static const for ROM data or a normal local for RAM."
            )

        if isinstance(decl.type, c_ast.ArrayDecl):
            if self.current_fn is None:
                coord = getattr(decl, "coord", "unknown")
                raise ConversionError(
                    f"array declaration '{decl.name}' outside function at {coord}"
                )

            scoped_alias = f"{self.current_fn.name}__{decl.name}"
            if is_const:
                values = self._eval_const_array_u8(decl, decl.init)
                self._register_rom_data_block(scoped_alias, values)
                if self._decl_is_signed_char(decl):
                    self.signed_rom_arrays.add(scoped_alias)
                return

            if decl.init is not None:
                coord = getattr(decl, "coord", "unknown")
                raise ConversionError(
                    f"Mutable local array '{decl.name}' initializer is not supported at {coord}. "
                    "Declare the buffer without initializer and fill it at runtime."
                )

            if decl.type.dim is None:
                coord = getattr(decl, "coord", "unknown")
                raise ConversionError(
                    f"Mutable local array '{decl.name}' requires an explicit size at {coord}"
                )

            length = self._eval_const_u8(decl.type.dim)
            struct_type = self._extract_struct_type_from_decl(decl)
            if struct_type is not None:
                struct_name = struct_type.name
                if struct_name is None:
                    coord = getattr(decl, "coord", "unknown")
                    raise ConversionError(
                        f"Anonymous struct array '{decl.name}' is not supported at {coord}"
                    )
                struct_size = self.struct_sizes.get(struct_name)
                if struct_size is None:
                    self._compute_struct_layout(struct_name, struct_type)
                    struct_size = self.struct_sizes.get(struct_name)
                if struct_size is None:
                    coord = getattr(decl, "coord", "unknown")
                    raise ConversionError(
                        f"Could not determine struct size for '{struct_name}' at {coord}"
                    )
                self._alloc_ram_array(scoped_alias, length, struct_size, struct_name)
            else:
                self._alloc_ram_array(scoped_alias, length)
            if self._decl_is_signed_char(decl):
                self.signed_ram_arrays.add(scoped_alias)
            return

        struct_type = self._extract_struct_type_from_decl(decl)
        if struct_type is not None:
            if self.current_fn is None:
                coord = getattr(decl, "coord", "unknown")
                raise ConversionError(f"Local struct declaration outside function at {coord}")
            scoped_alias = f"{self.current_fn.name}__{decl.name}"
            fields = self._flatten_struct_fields(struct_type)
            self._alloc_struct_instance(scoped_alias, fields)
            return

        if is_const:
            if self.current_fn is None:
                coord = getattr(decl, "coord", "unknown")
                raise ConversionError(
                    f"const declaration '{decl.name}' outside function should be global at {coord}"
                )
            scoped_name = f"{self.current_fn.name}__{decl.name}"
            if decl.init is None:
                coord = getattr(decl, "coord", "unknown")
                raise ConversionError(
                    f"const local '{decl.name}' requires an initializer at {coord}"
                )
            self.rom_constants[scoped_name] = self._eval_const_u8(decl.init)
            if self._decl_is_signed_char(decl):
                self.signed_symbols.add(scoped_name)
            return

        sym = self._resolve_symbol(decl.name)
        if self._decl_is_signed_char(decl):
            self.signed_symbols.add(sym)
        if decl.init is not None:
            self._emit_expr_to_a(decl.init)
            self._emit(f"    mov ({sym}),a")

    def _emit_assignment(self, assign: c_ast.Assignment) -> None:
        if assign.op != "=":
            self._unsupported(assign, f"Assignment operator {assign.op}")
            return

        if isinstance(assign.lvalue, c_ast.ID):
            lvalue_name = assign.lvalue.name
            if self.current_fn and f"{self.current_fn.name}__{lvalue_name}" in self.rom_constants:
                coord = getattr(assign, "coord", "unknown")
                raise ConversionError(
                    f"Cannot assign to const local '{lvalue_name}' at {coord}"
                )
            if lvalue_name in self.rom_constants:
                coord = getattr(assign, "coord", "unknown")
                raise ConversionError(
                    f"Cannot assign to const global '{lvalue_name}' at {coord}"
                )
            target = self._resolve_symbol(assign.lvalue.name)
        elif isinstance(assign.lvalue, c_ast.StructRef):
            # Handle both direct and array-indexed struct field assignment
            if isinstance(assign.lvalue.name, c_ast.ArrayRef):
                # Array-indexed: actors[i].field = value
                # Emit the assignment with dynamic address computation
                self._emit_expr_to_a(assign.rvalue)
                self._emit("    mov c,a")  # c = value to store
                # Now compute address and store
                self._emit_struct_field_store(assign.lvalue, "c")
                return
            else:
                # Direct struct field: actor.field = value
                target = self._resolve_struct_field_symbol(assign.lvalue)
        elif isinstance(assign.lvalue, c_ast.ArrayRef):
            if not isinstance(assign.lvalue.name, c_ast.ID):
                self._unsupported(assign, "Only direct RAM array assignment is supported")
                return
            ram_alias = self._resolve_ram_array_alias(assign.lvalue.name.name)
            if ram_alias is None:
                coord = getattr(assign, "coord", "unknown")
                raise ConversionError(
                    f"Array '{assign.lvalue.name.name}' is not a mutable RAM array at {coord}"
                )
            self._emit_expr_to_a(assign.rvalue)
            self._emit("    mov c,a")
            self._emit_ram_array_store(ram_alias, assign.lvalue.subscript, "c")
            return
        else:
            self._unsupported(assign, "Only direct variable or struct.field assignment is supported")
            return

        self._emit_expr_to_a(assign.rvalue)
        self._emit(f"    mov ({target}),a")

    def _emit_if(self, node: c_ast.If) -> None:
        else_label = self._new_label("if_else")
        end_label = self._new_label("if_end")
        true_label = self._new_label("if_true")

        self._emit_expr_to_a(node.cond)
        # Skip-safe branch: if cond != 0, jump near to true label, else jump far to else.
        self._emit("    eqi a,0")
        self._emit(f"    jr {true_label}")
        self._emit(f"    jmp {else_label}")

        self._emit(f"@{true_label}")

        self._emit_stmt(node.iftrue)
        self._emit(f"    jmp {end_label}")

        self._emit(f"@{else_label}")
        if node.iffalse is not None:
            self._emit_stmt(node.iffalse)
        self._emit(f"@{end_label}")

    def _emit_while(self, node: c_ast.While) -> None:
        start_label = self._new_label("while_start")
        end_label = self._new_label("while_end")
        body_label = self._new_label("while_body")

        self._emit(f"@{start_label}")
        self._emit_expr_to_a(node.cond)
        # Skip-safe branch: if cond != 0, enter body; else break.
        self._emit("    eqi a,0")
        self._emit(f"    jr {body_label}")
        self._emit(f"    jmp {end_label}")
        self._emit(f"@{body_label}")
        self.loop_end_labels.append(end_label)
        try:
            self._emit_stmt(node.stmt)
        finally:
            self.loop_end_labels.pop()
        self._emit(f"    jmp {start_label}")
        self._emit(f"@{end_label}")

    def _emit_for(self, node: c_ast.For) -> None:
        start_label = self._new_label("for_start")
        end_label = self._new_label("for_end")
        body_label = self._new_label("for_body")

        # Execute init statement if present
        if node.init is not None:
            self._emit_stmt(node.init)

        self._emit(f"@{start_label}")
        # Evaluate condition if present; if not present, loop is infinite (must use break)
        if node.cond is not None:
            self._emit_expr_to_a(node.cond)
            # Skip-safe branch: if cond != 0, enter body; else break.
            self._emit("    eqi a,0")
            self._emit(f"    jr {body_label}")
            self._emit(f"    jmp {end_label}")
        self._emit(f"@{body_label}")
        self.loop_end_labels.append(end_label)
        try:
            self._emit_stmt(node.stmt)
        finally:
            self.loop_end_labels.pop()
        # Execute next statement if present
        if node.next is not None:
            self._emit_stmt(node.next)
        self._emit(f"    jmp {start_label}")
        self._emit(f"@{end_label}")

    def _emit_condition(self, expr: c_ast.Node) -> None:
        # Evaluates expression and sets skip condition based on zero/non-zero.
        self._emit_expr_to_a(expr)
        self._emit("    eqi a,0")

    def _emit_call(self, call: c_ast.FuncCall) -> None:
        if not isinstance(call.name, c_ast.ID):
            self._unsupported(call, "Only direct function calls are supported")
            return

        callee = self.API_ALIASES.get(call.name.name, call.name.name)
        params = self.function_params.get(callee)
        args = list(call.args.exprs) if call.args and call.args.exprs else []

        if callee != "scv_print_string":
            if callee in self.asset_functions or callee in self.asset_bulk_functions:
                self.extern_functions.add(callee)
            elif callee in self.function_params and callee not in self.defined_functions:
                self.extern_functions.add(callee)

            if params is None and (callee in self.asset_functions or callee in self.asset_bulk_functions):
                params = ["pattern_slot"]
                self.function_params[callee] = params
                self.extern_functions.add(callee)
            if params is None and callee in self.SCV_API_PARAMS:
                params = self.SCV_API_PARAMS[callee]
                self.function_params[callee] = params
                self.extern_functions.add(callee)

        if callee == "scv_print_string":
            if len(args) != 3:
                raise ConversionError(
                    f"Call arity mismatch for {callee}: expected 3, got {len(args)}"
                )

            def emit_rom_row_pointer_to_de(row_expr: c_ast.ArrayRef) -> bool:
                def emit_hl_to_de() -> None:
                    self._emit("    mov a,h")
                    self._emit("    mov d,a")
                    self._emit("    mov a,l")
                    self._emit("    mov e,a")

                if not isinstance(row_expr.name, c_ast.ID):
                    return False

                alias = self._resolve_rom_array_alias(row_expr.name.name)
                if alias is None:
                    return False

                dims = self.rom_array_dims.get(alias, [])
                if len(dims) < 2:
                    return False

                row_width = dims[1]
                label = self.rom_array_labels[alias]

                const_row_idx: Optional[int] = None
                try:
                    const_row_idx = self._eval_const_u8(row_expr.subscript)
                except ConversionError:
                    const_row_idx = None

                if const_row_idx is not None:
                    row_offset = const_row_idx * row_width
                    self._emit(f"    lxi hl,{label}")
                    if row_offset != 0:
                        self._emit(f"    mvi a,{self._fmt_imm(row_offset & 0xFF)}")
                        self._emit_add_a_to_hl()
                    emit_hl_to_de()
                    return True

                self._emit_expr_to_a(row_expr.subscript)
                if row_width == 1:
                    pass
                elif row_width == 10:
                    self._emit("    mov b,a")
                    self._emit("    add a,a")
                    self._emit("    add a,a")
                    self._emit("    add a,a")
                    self._emit("    mov c,a")
                    self._emit("    mov a,b")
                    self._emit("    add a,a")
                    self._emit("    add a,c")
                elif row_width == 16:
                    self._emit("    add a,a")
                    self._emit("    add a,a")
                    self._emit("    add a,a")
                    self._emit("    add a,a")
                else:
                    self._emit("    mov c,a")
                    self._emit(f"    mvi b,{self._fmt_imm(row_width)}")
                    self._emit("    mvi d,0")
                    mul_loop = self._new_label("print_string_row_mul")
                    self._emit(f"@{mul_loop}")
                    self._emit("    mov a,d")
                    self._emit("    add a,c")
                    self._emit("    mov d,a")
                    self._emit("    dcr b")
                    self._emit(f"    jre {mul_loop}")
                    self._emit("    mov a,d")

                self._emit(f"    lxi hl,{label}")
                self._emit_add_a_to_hl()
                emit_hl_to_de()
                return True

            inline_values: Optional[List[int]] = None

            if isinstance(args[2], c_ast.Constant) and args[2].type == "string":
                raw = args[2].value
                if len(raw) < 2 or raw[0] != '"' or raw[-1] != '"':
                    coord = getattr(args[2], "coord", "unknown")
                    raise ConversionError(f"Unsupported string literal {raw} at {coord}")

                decoded = bytes(raw[1:-1], "utf-8").decode("unicode_escape")
                inline_values = [ord(ch) & 0xFF for ch in decoded]
            elif isinstance(args[2], c_ast.ID):
                rom_alias = self._resolve_rom_array_alias(args[2].name)
                if rom_alias is not None:
                    values = self.rom_array_values[rom_alias]
                    inline_values = []
                    for v in values:
                        if v == 0:
                            break
                        inline_values.append(v & 0xFF)
                        if len(inline_values) >= 0x20:
                            break

            if inline_values is not None:
                self._emit_expr_to_a(args[0])
                src_slot_x = self._alloc_symbol("scv_api__arg_0")
                self._emit(f"    mov ({src_slot_x}),a")

                self._emit_expr_to_a(args[1])
                src_slot_y = self._alloc_symbol("scv_api__arg_1")
                self._emit(f"    mov ({src_slot_y}),a")

            else:
                self._emit_expr_to_a(args[0])
                src_slot_x = self._alloc_symbol(self._arg_symbol_name(callee, "x"))
                self._emit(f"    mov ({src_slot_x}),a")

                self._emit_expr_to_a(args[1])
                src_slot_y = self._alloc_symbol(self._arg_symbol_name(callee, "y"))
                self._emit(f"    mov ({src_slot_y}),a")

            def emit_inline_chars(values: List[int], src_slot_x: str, src_slot_y: str) -> None:
                self.extern_functions.add("scv_print_char")
                dst_slot_x = self._alloc_symbol(self._arg_symbol_name("scv_print_char", "x"))
                dst_slot_y = self._alloc_symbol(self._arg_symbol_name("scv_print_char", "y"))
                slot_ch = self._alloc_symbol(self._arg_symbol_name("scv_print_char", "ch"))

                for value in values:
                    self._emit(f"    mov a,({src_slot_x})")
                    self._emit(f"    mov ({dst_slot_x}),a")
                    self._emit(f"    mov a,({src_slot_y})")
                    self._emit(f"    mov ({dst_slot_y}),a")
                    self._emit(f"    mvi a,{self._fmt_imm(value)}")
                    self._emit(f"    mov ({slot_ch}),a")
                    self._emit("    call fn_scv_print_char")
                    self._emit(f"    mov a,({src_slot_x})")
                    self._emit("    adi a,0x01")
                    self._emit(f"    mov ({src_slot_x}),a")

            # Inline literal strings and ROM-backed const arrays as direct
            # scv_print_char calls. This avoids reliance on volatile DE across
            # runtime string loops and avoids reserving dedicated print_string
            # arg bytes in RAM when no runtime helper call is needed.
            if inline_values is not None:
                emit_inline_chars(inline_values, src_slot_x, src_slot_y)
                return

            rom_label: Optional[str] = None
            ram_label: Optional[str] = None
            emitted_pointer = False

            if isinstance(args[2], c_ast.ID):
                alias = self._resolve_rom_array_alias(args[2].name)
                if alias is not None:
                    rom_label = self.rom_array_labels[alias]
                if rom_label is None:
                    ram_alias = self._resolve_ram_array_alias(args[2].name)
                    if ram_alias is not None:
                        ram_label = self.ram_array_labels[ram_alias]
            elif isinstance(args[2], c_ast.ArrayRef):
                emitted_pointer = emit_rom_row_pointer_to_de(args[2])

            if not emitted_pointer and rom_label is None and ram_label is None:
                coord = getattr(args[2], "coord", "unknown")
                raise ConversionError(
                    f"scv_print_string third argument must be a ROM or RAM array identifier or string literal at {coord}"
                )

            if emitted_pointer:
                pass
            elif rom_label is not None:
                self._emit(f"    lxi de,{rom_label}")
            else:
                self._emit(f"    lxi de,{ram_label}")

            # Only reserve runtime scv_print_string support when we actually emit a call.
            if params is None:
                params = self.SCV_API_PARAMS[callee]
                self.function_params[callee] = params
            self.extern_functions.add(callee)

            self._emit(f"    call fn_{callee}")
            return

        if callee == "scv_vram_copy":
            if len(args) != 4:
                raise ConversionError(
                    f"Call arity mismatch for {callee}: expected 4, got {len(args)}"
                )

            addr_hi = self._alloc_symbol(self._arg_symbol_name(callee, "addr_hi"))
            addr_lo = self._alloc_symbol(self._arg_symbol_name(callee, "addr_lo"))
            byte_count = self._alloc_symbol(self._arg_symbol_name(callee, "byte_count"))

            self._emit_expr_to_a(args[0])
            self._emit(f"    mov ({addr_hi}),a")
            self._emit_expr_to_a(args[1])
            self._emit(f"    mov ({addr_lo}),a")

            if not isinstance(args[2], c_ast.ID):
                coord = getattr(args[2], "coord", "unknown")
                raise ConversionError(
                    f"scv_vram_copy source must be a ROM or RAM array identifier at {coord}"
                )

            src_alias = args[2].name
            rom_alias = self._resolve_rom_array_alias(src_alias)
            ram_alias = self._resolve_ram_array_alias(src_alias)
            if rom_alias is None and ram_alias is None:
                coord = getattr(args[2], "coord", "unknown")
                raise ConversionError(
                    f"scv_vram_copy source '{src_alias}' must be a ROM or RAM array identifier at {coord}"
                )

            self._emit_expr_to_a(args[3])
            self._emit(f"    mov ({byte_count}),a")

            if rom_alias is not None:
                self._emit(f"    lxi de,{self.rom_array_labels[rom_alias]}")
            else:
                self._emit(f"    lxi de,{self.ram_array_labels[ram_alias]}")

            if params is None:
                params = self.SCV_API_PARAMS[callee]
                self.function_params[callee] = params
            self.extern_functions.add(callee)
            self._emit(f"    call fn_{callee}")
            return

        if callee in {
            "scv_load_bg_array",
            "scv_load_bg_sprite_array",
            "scv_patch_bg_column_right",
            "scv_patch_bg_column_left",
            "scv_patch_bg_row_top",
            "scv_patch_bg_row_bottom",
        }:
            if len(args) != 3:
                raise ConversionError(
                    f"Call arity mismatch for {callee}: expected 3, got {len(args)}"
                )

            first_param_name = self.SCV_API_PARAMS[callee][0]
            second_param_name = self.SCV_API_PARAMS[callee][1]
            slot_pattern = self._alloc_symbol(self._arg_symbol_name(callee, first_param_name))
            slot_count = self._alloc_symbol(self._arg_symbol_name(callee, second_param_name))

            source_index = 1
            count_index = 2
            if callee in {
                "scv_patch_bg_column_right",
                "scv_patch_bg_column_left",
                "scv_patch_bg_row_top",
                "scv_patch_bg_row_bottom",
            }:
                source_index = 2
                count_index = 1

            self._emit_expr_to_a(args[0])
            self._emit(f"    mov ({slot_pattern}),a")

            self._emit_expr_to_a(args[count_index])
            self._emit(f"    mov ({slot_count}),a")

            if not isinstance(args[source_index], c_ast.ID):
                coord = getattr(args[source_index], "coord", "unknown")
                raise ConversionError(
                    f"{callee} source must be a ROM or RAM array identifier at {coord}"
                )

            src_alias = args[source_index].name
            rom_alias = self._resolve_rom_array_alias(src_alias)
            ram_alias = self._resolve_ram_array_alias(src_alias)
            if rom_alias is None and ram_alias is None:
                coord = getattr(args[source_index], "coord", "unknown")
                raise ConversionError(
                    f"{callee} source '{src_alias}' must be a ROM or RAM array identifier at {coord}"
                )

            if rom_alias is not None:
                self._emit(f"    lxi de,{self.rom_array_labels[rom_alias]}")
            else:
                self._emit(f"    lxi de,{self.ram_array_labels[ram_alias]}")

            if params is None:
                params = self.SCV_API_PARAMS[callee]
                self.function_params[callee] = params
            self.extern_functions.add(callee)
            self._emit(f"    call fn_{callee}")
            return

        if callee in {"scv_map_extract_column", "scv_map_extract_row"}:
            if len(args) != 6:
                raise ConversionError(
                    f"Call arity mismatch for {callee}: expected 6, got {len(args)}"
                )

            if not isinstance(args[0], c_ast.ID):
                coord = getattr(args[0], "coord", "unknown")
                raise ConversionError(
                    f"{callee} destination must be a RAM array identifier at {coord}"
                )

            dst_alias = self._resolve_ram_array_alias(args[0].name)
            if dst_alias is None:
                coord = getattr(args[0], "coord", "unknown")
                raise ConversionError(
                    f"{callee} destination must be a RAM array identifier at {coord}"
                )

            if not isinstance(args[1], c_ast.ID):
                coord = getattr(args[1], "coord", "unknown")
                raise ConversionError(
                    f"{callee} source must be a ROM or RAM array identifier at {coord}"
                )

            src_alias = args[1].name
            rom_alias = self._resolve_rom_array_alias(src_alias)
            ram_alias = self._resolve_ram_array_alias(src_alias)
            if rom_alias is None and ram_alias is None:
                coord = getattr(args[1], "coord", "unknown")
                raise ConversionError(
                    f"{callee} source '{src_alias}' must be a ROM or RAM array identifier at {coord}"
                )

            map_width_slot = self._alloc_symbol(self._arg_symbol_name(callee, "map_width"))
            map_x_slot = self._alloc_symbol(self._arg_symbol_name(callee, "map_x"))
            map_y_slot = self._alloc_symbol(self._arg_symbol_name(callee, "map_y"))
            count_slot = self._alloc_symbol(self._arg_symbol_name(callee, "count"))

            self._emit_expr_to_a(args[2])
            self._emit(f"    mov ({map_width_slot}),a")
            self._emit_expr_to_a(args[3])
            self._emit(f"    mov ({map_x_slot}),a")
            self._emit_expr_to_a(args[4])
            self._emit(f"    mov ({map_y_slot}),a")
            self._emit_expr_to_a(args[5])
            self._emit(f"    mov ({count_slot}),a")

            self._emit(f"    lxi hl,{self.ram_array_labels[dst_alias]}")
            if rom_alias is not None:
                self._emit(f"    lxi de,{self.rom_array_labels[rom_alias]}")
            else:
                self._emit(f"    lxi de,{self.ram_array_labels[ram_alias]}")

            if params is None:
                params = self.SCV_API_PARAMS[callee]
                self.function_params[callee] = params
            self.extern_functions.add(callee)
            self._emit(f"    call fn_{callee}")
            return

        if callee == "strlen":
            if len(args) != 1:
                raise ConversionError(
                    f"Call arity mismatch for {callee}: expected 1, got {len(args)}"
                )

            if not isinstance(args[0], c_ast.ID):
                coord = getattr(args[0], "coord", "unknown")
                raise ConversionError(
                    f"strlen argument must be a ROM or RAM array identifier at {coord}"
                )

            rom_alias = self._resolve_rom_array_alias(args[0].name)
            if rom_alias is not None:
                values = self.rom_array_values[rom_alias]
                length = 0
                while length < len(values) and values[length] != 0:
                    length += 1
                self._emit(f"    mvi a,{self._fmt_imm(length)}")
                return

            ram_alias = self._resolve_ram_array_alias(args[0].name)
            if ram_alias is not None:
                self._emit(f"    lxi de,{self.ram_array_labels[ram_alias]}")
                self._emit("    call fn_strlen")
                return

            coord = getattr(args[0], "coord", "unknown")
            raise ConversionError(
                f"strlen argument must be a ROM or RAM array identifier at {coord}"
            )

        if callee == "sprintf":
            if len(args) != 3:
                raise ConversionError(
                    f"Call arity mismatch for {callee}: expected 3, got {len(args)}"
                )

            if not isinstance(args[0], c_ast.ID):
                coord = getattr(args[0], "coord", "unknown")
                raise ConversionError(
                    f"sprintf destination must be a RAM array identifier at {coord}"
                )

            dst_alias = self._resolve_ram_array_alias(args[0].name)
            if dst_alias is None:
                coord = getattr(args[0], "coord", "unknown")
                raise ConversionError(
                    f"sprintf destination must be a RAM array identifier at {coord}"
                )

            if not isinstance(args[1], c_ast.ID):
                coord = getattr(args[1], "coord", "unknown")
                raise ConversionError(
                    f"sprintf format must be a ROM or RAM array identifier at {coord}"
                )

            fmt_label: Optional[str] = None
            fmt_rom_alias = self._resolve_rom_array_alias(args[1].name)
            if fmt_rom_alias is not None:
                fmt_label = self.rom_array_labels[fmt_rom_alias]
            if fmt_label is None:
                fmt_ram_alias = self._resolve_ram_array_alias(args[1].name)
                if fmt_ram_alias is not None:
                    fmt_label = self.ram_array_labels[fmt_ram_alias]

            if fmt_label is None:
                coord = getattr(args[1], "coord", "unknown")
                raise ConversionError(
                    f"sprintf format must be a ROM or RAM array identifier at {coord}"
                )

            self._emit_expr_to_a(args[2])
            value_slot = self._alloc_symbol(self._arg_symbol_name(callee, "value"))
            self._emit(f"    mov ({value_slot}),a")
            self._emit(f"    lxi de,{self.ram_array_labels[dst_alias]}")
            self._emit(f"    lxi hl,{fmt_label}")
            self._emit("    call fn_sprintf")
            return

        if params is not None and len(args) != len(params):
            raise ConversionError(
                f"Call arity mismatch for {callee}: expected {len(params)}, got {len(args)}"
            )

        for idx, arg in enumerate(args):
            self._emit_expr_to_a(arg)
            if params is not None:
                slot = self._alloc_symbol(self._arg_symbol_name(callee, params[idx]))
                self._emit(f"    mov ({slot}),a")
            else:
                slot = self._alloc_symbol(f"{callee}__arg_arg{idx}")
                self._emit("    -- external/unknown callee argument slot")
                self._emit(f"    mov ({slot}),a")

        self._emit(f"    call fn_{callee}")

    def _emit_expr_to_a(self, expr: c_ast.Node) -> None:
        if isinstance(expr, c_ast.Constant) and expr.type in {"int", "char"}:
            if expr.type == "int":
                raw = int(expr.value, 0)
            else:
                text = expr.value
                if len(text) < 2 or text[0] != "'" or text[-1] != "'":
                    coord = getattr(expr, "coord", "unknown")
                    raise ConversionError(f"Unsupported char literal {text} at {coord}")
                inner = text[1:-1]
                decoded = bytes(inner, "utf-8").decode("unicode_escape")
                if len(decoded) != 1:
                    coord = getattr(expr, "coord", "unknown")
                    raise ConversionError(
                        f"Only single-byte char literals are supported ({text}) at {coord}"
                    )
                raw = ord(decoded)
            if not (0 <= raw <= 255):
                coord = getattr(expr, "coord", "unknown")
                raise ConversionError(
                    f"Integer constant {raw} (0x{raw:X}) exceeds 8-bit range at {coord}.\n"
                    f"  Use an 8-bit offset instead of a full 16-bit address.\n"
                    f"  Example: split into base (defined in the asm stub) + 8-bit offset."
                )
            self._emit(f"    mvi a,{self._fmt_imm(raw)}")
            return

        if isinstance(expr, c_ast.ID):
            sym = self._resolve_symbol(expr.name)
            if sym in self.rom_constants:
                self._emit(f"    mvi a,{self._fmt_imm(self.rom_constants[sym])}")
            else:
                self._emit(f"    mov a,({sym})")
            return

        if isinstance(expr, c_ast.StructRef):
            self._emit_struct_field_to_a(expr)
            return

        if isinstance(expr, c_ast.ArrayRef):
            self._emit_array_ref_to_a(expr)
            return

        if isinstance(expr, c_ast.UnaryOp):
            self._emit_unary(expr)
            return

        if isinstance(expr, c_ast.BinaryOp):
            self._emit_binary(expr)
            return

        if isinstance(expr, c_ast.FuncCall):
            self._emit_call(expr)
            return

        self._unsupported(expr, f"Expression type {type(expr).__name__}")

    def _emit_array_ref_to_a(self, expr: c_ast.ArrayRef) -> None:
        # Handle multi-dimensional arrays: arr[i][j] where arr[i] is an ArrayRef
        if isinstance(expr.name, c_ast.ArrayRef):
            # Multi-dimensional array access: evaluate outer array first
            outer_expr = expr.name  # This is arr[i]
            inner_subscript = expr.subscript  # This is j in arr[i][j]
            
            # Get the array name and validate
            if not isinstance(outer_expr.name, c_ast.ID):
                self._unsupported(expr, "Nested array indexing only supports direct array variables")
                return
            
            base_name = outer_expr.name.name
            alias = self._resolve_rom_array_alias(base_name)
            if alias is None:
                coord = getattr(expr, "coord", "unknown")
                raise ConversionError(
                    f"Array '{base_name}' is not a const/static const ROM array at {coord}"
                )
            
            label = self.rom_array_labels[alias]
            dims = self.rom_array_dims.get(alias, [])
            
            if not dims or len(dims) < 2:
                self._unsupported(expr, "Multi-dimensional array must have defined dimensions")
                return
            
            row_width = dims[1]  # For arr[rows][cols], cols is the row width/stride
            
            # For 2D arrays stored row-major: offset = outer_idx * row_width + inner_idx
            # Evaluate outer index
            self._emit_expr_to_a(outer_expr.subscript)
            self._emit("    mov b,a")  # b = outer index

            # Multiply outer index by row width; result ends up in a.
            self._emit("    mov a,b")
            self._emit_mul_a_by_const(row_width)

            # Add inner index
            const_inner_idx: Optional[int] = None
            try:
                const_inner_idx = self._eval_const_u8(inner_subscript)
            except ConversionError:
                const_inner_idx = None

            if const_inner_idx is not None:
                # Inner index is constant — result of multiply is still in a.
                if const_inner_idx != 0:
                    self._emit(f"    adi a,{self._fmt_imm(const_inner_idx)}")
                self._emit(f"    lxi hl,{label}")
                self._emit_add_a_to_hl()
                self._emit("    ldax (hl)")
                return
            else:
                # Both indices are runtime.
                # Stash outer_idx * row_width in a RAM temp before calling _emit_expr_to_a,
                # because that call may clobber registers b/c/d.
                row_tmp = self._alloc_temp_symbol("arith__2d_row_offset")
                self._emit(f"    mov ({row_tmp}),a")
                self._emit_expr_to_a(inner_subscript)
                self._emit("    mov c,a")  # c = inner index
                self._emit(f"    mov a,({row_tmp})")  # a = outer_idx * row_width
                self._emit("    add a,c")  # a = total offset
                self._emit(f"    lxi hl,{label}")
                self._emit_add_a_to_hl()
                self._emit("    ldax (hl)")
                return
        
        # Single-dimensional array access
        if not isinstance(expr.name, c_ast.ID):
            self._unsupported(expr, "Only direct array variable indexing is supported")
            return

        alias = self._resolve_rom_array_alias(expr.name.name)
        ram_alias = None
        if alias is None:
            ram_alias = self._resolve_ram_array_alias(expr.name.name)
        if alias is None and ram_alias is None:
            coord = getattr(expr, "coord", "unknown")
            raise ConversionError(
                f"Array '{expr.name.name}' is not a supported ROM or RAM array at {coord}"
            )

        if alias is not None:
            label = self.rom_array_labels[alias]
            arr_len = self.rom_array_lengths[alias]
            is_rom = True
        else:
            label = self.ram_array_labels[ram_alias]
            arr_len = self.ram_array_lengths[ram_alias]
            is_rom = False

        const_idx: Optional[int] = None
        try:
            const_idx = self._eval_const_u8(expr.subscript)
        except ConversionError:
            const_idx = None

        if const_idx is not None:
            if const_idx >= arr_len:
                coord = getattr(expr, "coord", "unknown")
                raise ConversionError(
                    f"Array index {const_idx} out of bounds for '{expr.name.name}' (size {arr_len}) at {coord}"
                )
            self._emit(f"    lxi hl,{label}")
            if const_idx != 0:
                self._emit(f"    mvi a,{self._fmt_imm(const_idx)}")
                self._emit_add_a_to_hl()
            self._emit("    ldax (hl)")
            return

        self._emit_expr_to_a(expr.subscript)
        self._emit("    mov b,a")
        self._emit(f"    lxi hl,{label}")
        self._emit("    mov a,b")
        self._emit_add_a_to_hl()
        self._emit("    ldax (hl)")

    def _get_array_struct_size(self, array_alias: str, array_name: str) -> int:
        """Get the struct size for an array-of-structs."""
        struct_name = self.ram_array_struct_types.get(array_alias)
        if struct_name is not None and struct_name in self.struct_sizes:
            return self.struct_sizes[struct_name]
        element_size = self.ram_array_element_sizes.get(array_alias)
        if element_size is not None:
            return element_size
        coord = getattr(self.current_fn, "name", "global") if self.current_fn is not None else "global"
        raise ConversionError(f"Could not determine struct size for RAM array '{array_name}' in {coord}")

    def _get_struct_field_offset(self, struct_name: str, field_name: str) -> int:
        """Get the offset of a field within a struct."""
        if struct_name in self.struct_field_offsets and field_name in self.struct_field_offsets[struct_name]:
            return self.struct_field_offsets[struct_name][field_name]
        raise ConversionError(f"Unknown field '{field_name}' on struct '{struct_name}'")

    def _emit_ram_array_store(self, array_alias: str, subscript: c_ast.Node, value_register: str = "a") -> None:
        array_base = self.ram_array_labels[array_alias]

        if value_register != "a":
            self._emit(f"    mov a,{value_register}")
        self._emit("    mov c,a")

        const_idx: Optional[int] = None
        try:
            const_idx = self._eval_const_u8(subscript)
        except ConversionError:
            const_idx = None

        if const_idx is not None:
            self._emit(f"    lxi hl,{array_base}")
            if const_idx != 0:
                self._emit(f"    mvi a,{self._fmt_imm(const_idx)}")
                self._emit_add_a_to_hl()
            self._emit("    mov a,c")
            self._emit("    stax (hl)")
            return

        self._emit_expr_to_a(subscript)
        self._emit("    mov b,a")
        self._emit(f"    lxi hl,{array_base}")
        self._emit("    mov a,b")
        self._emit_add_a_to_hl()
        self._emit("    mov a,c")
        self._emit("    stax (hl)")

    def _emit_struct_field_store(self, struct_ref: c_ast.StructRef, value_register: str = "a") -> None:
        """Emit code to store a value from a register into an array-indexed struct field.
        
        Args:
            struct_ref: The StructRef node (e.g., actors[i].field)
            value_register: The register containing the value ("a" or "c")
        """
        if not isinstance(struct_ref.name, c_ast.ArrayRef):
            self._unsupported(struct_ref, "Store only for array-indexed struct fields")
            return
        
        if not isinstance(struct_ref.field, c_ast.ID):
            self._unsupported(struct_ref, "Only named struct fields are supported")
            return
        
        array_ref = struct_ref.name
        field_name = struct_ref.field.name
        
        if not isinstance(array_ref.name, c_ast.ID):
            self._unsupported(struct_ref, "Only direct array variables in struct field access")
            return
        
        array_name = array_ref.name.name
        array_alias = self._resolve_ram_array_alias(array_name)
        if array_alias is None:
            coord = getattr(struct_ref, "coord", "unknown")
            raise ConversionError(f"Array '{array_name}' not found at {coord}")
        
        array_base = self.ram_array_labels[array_alias]
        struct_type_name = self.ram_array_struct_types.get(array_alias, array_name)
        struct_size = self._get_array_struct_size(array_alias, array_name)
        field_offset = self._get_struct_field_offset(struct_type_name, field_name)
        
        # Save value register if needed
        if value_register != "a":
            self._emit(f"    mov a,{value_register}")
        
        # Compute offset from index
        self._emit_expr_to_a(array_ref.subscript)  # a = index
        
        if struct_size == 1:
            self._emit("    mov b,a")
        elif struct_size == 2:
            self._emit("    add a,a")  # a *= 2
            self._emit("    mov b,a")
        elif struct_size == 4:
            self._emit("    add a,a")  # a *= 2
            self._emit("    add a,a")  # a *= 4
            self._emit("    mov b,a")
        else:
            # General multiply using d as accumulator
            self._emit("    mov c,a")  # c = index (multiplier)
            self._emit(f"    mvi b,{self._fmt_imm(struct_size)}")  # b = struct_size (counter)
            self._emit("    mvi d,0")  # d = accumulator
            mul_loop = self._new_label("struct_mul_loop")
            self._emit(f"@{mul_loop}")
            self._emit("    mov a,d")  # a = accumulator
            self._emit("    add a,c")  # a += index
            self._emit("    mov d,a")  # d = new accumulator
            self._emit("    dcr b")  # b--
            self._emit(f"    jre {mul_loop}")  # jump if b != 0
            self._emit("    mov a,d")  # a = result from d
            self._emit("    mov b,a")  # b = result
        
        # Prepare value for store
        self._emit(f"    mvi a,{self._fmt_imm(field_offset)}")
        self._emit("    add a,b")  # a = field_offset + index_offset
        self._emit(f"    lxi hl,{array_base}")
        self._emit_add_a_to_hl()
        
        # Restore value and store
        if value_register == "a":
            # Need to save a first since we used it for address computation
            self._unsupported(struct_ref, "Value must be in register c for store operations")
        else:
            self._emit(f"    mov a,{value_register}")
            self._emit("    stax (hl)")

    def _emit_unary(self, unary: c_ast.UnaryOp) -> None:
        if unary.op == "+":
            self._emit_expr_to_a(unary.expr)
            return

        if unary.op == "-":
            self._emit_expr_to_a(unary.expr)
            self._emit("    mov b,a")
            self._emit("    mvi a,0x00")
            self._emit("    sub a,b")
            return

        if unary.op == "!":
            true_label = self._new_label("not_true")
            end_label = self._new_label("not_end")
            false_label = self._new_label("not_false")
            self._emit_expr_to_a(unary.expr)
            self._emit("    eqi a,0")
            self._emit(f"    jr {false_label}")
            self._emit(f"    jmp {true_label}")
            self._emit(f"@{false_label}")
            self._emit("    mvi a,0x00")
            self._emit(f"    jmp {end_label}")
            self._emit(f"@{true_label}")
            self._emit("    mvi a,0x01")
            self._emit(f"@{end_label}")
            return

        if unary.op == "*":
            self._emit_deref_to_a(unary.expr)
            return

        if unary.op == "p++":  # postfix ++: variable++
            # For simplicity, treat as prefix ++ (return incremented value, not original)
            if not isinstance(unary.expr, c_ast.ID):
                self._unsupported(unary, "Postfix ++ only supports simple variables")
                return
            var = self._resolve_symbol(unary.expr.name)
            self._emit(f"    mov a,({var})")
            self._emit("    mov b,a")
            self._emit("    inc a")
            self._emit(f"    mov ({var}),a")
            # Return incremented value
            return

        if unary.op == "p--":  # postfix --: variable--
            # For simplicity, treat as prefix --
            if not isinstance(unary.expr, c_ast.ID):
                self._unsupported(unary, "Postfix -- only supports simple variables")
                return
            var = self._resolve_symbol(unary.expr.name)
            self._emit(f"    mov a,({var})")
            self._emit("    mov b,a")
            self._emit("    mov a,0xFF")
            self._emit("    add a,b")  # a = 0xFF + b = b - 1
            self._emit(f"    mov ({var}),a")
            # Return decremented value
            return

        self._unsupported(unary, f"Unary operator {unary.op}")

    def _emit_deref_to_a(self, expr: c_ast.Node) -> None:
        # Supported subset: *(rom_array + idx) or *(idx + rom_array)
        if not isinstance(expr, c_ast.BinaryOp) or expr.op != "+":
            self._unsupported(expr, "Only *(const_array + index) dereference is supported")
            return

        arr_name: Optional[str] = None
        idx_expr: Optional[c_ast.Node] = None
        if isinstance(expr.left, c_ast.ID):
            alias = self._resolve_rom_array_alias(expr.left.name)
            if alias is not None:
                arr_name = alias
                idx_expr = expr.right
        if arr_name is None and isinstance(expr.right, c_ast.ID):
            alias = self._resolve_rom_array_alias(expr.right.name)
            if alias is not None:
                arr_name = alias
                idx_expr = expr.left

        if arr_name is None or idx_expr is None:
            self._unsupported(expr, "Dereference base must be a const/static const ROM array")
            return

        label = self.rom_array_labels[arr_name]
        arr_len = self.rom_array_lengths[arr_name]

        const_idx: Optional[int] = None
        try:
            const_idx = self._eval_const_u8(idx_expr)
        except ConversionError:
            const_idx = None

        if const_idx is not None:
            if const_idx >= arr_len:
                coord = getattr(expr, "coord", "unknown")
                raise ConversionError(
                    f"Array index {const_idx} out of bounds for dereference base '{arr_name}' (size {arr_len}) at {coord}"
                )
            self._emit(f"    lxi hl,{label}")
            if const_idx != 0:
                self._emit(f"    mvi a,{self._fmt_imm(const_idx)}")
                self._emit_add_a_to_hl()
            self._emit("    ldax (hl)")
            return

        self._emit_expr_to_a(idx_expr)
        self._emit("    mov b,a")
        self._emit(f"    lxi hl,{label}")
        self._emit("    mov a,b")
        self._emit_add_a_to_hl()
        self._emit("    ldax (hl)")

    def _emit_binary(self, binary: c_ast.BinaryOp) -> None:
        op = binary.op

        if op in {"+", "-", "&", "|", "^", "*", "<<", ">>"}:
            if op == "*":
                lhs_slot = self._alloc_temp_symbol("arith__tmp0")
                rhs_slot = self._alloc_temp_symbol("arith__tmp1")
                acc_slot = self._alloc_temp_symbol("arith__tmp2")
                loop_label = self._new_label("mul_loop")
                body_label = self._new_label("mul_body")
                done_label = self._new_label("mul_done")

                self._emit_expr_to_a(binary.left)
                self._emit(f"    mov ({lhs_slot}),a")
                self._emit_expr_to_a(binary.right)
                self._emit(f"    mov ({rhs_slot}),a")
                self._emit("    mvi a,0x00")
                self._emit(f"    mov ({acc_slot}),a")

                self._emit(f"@{loop_label}")
                self._emit(f"    mov a,({rhs_slot})")
                self._emit("    eqi a,0")
                self._emit(f"    jr {body_label}")
                self._emit(f"    jmp {done_label}")

                self._emit(f"@{body_label}")
                self._emit(f"    mov a,({acc_slot})")
                self._emit("    mov b,a")
                self._emit(f"    mov a,({lhs_slot})")
                self._emit("    add a,b")
                self._emit(f"    mov ({acc_slot}),a")
                self._emit(f"    mov a,({rhs_slot})")
                self._emit("    adi a,0xFF")
                self._emit(f"    mov ({rhs_slot}),a")
                self._emit(f"    jmp {loop_label}")

                self._emit(f"@{done_label}")
                self._emit(f"    mov a,({acc_slot})")
                return

            if op == "<<":
                self._emit_shift_left(binary.left, binary.right)
                return

            if op == ">>":
                self._emit_shift_right(binary.left, binary.right)
                return

            depth = self.expr_tmp_depth
            self.expr_tmp_depth += 1
            lhs_slot = self._alloc_temp_symbol(f"arith__tmp_expr_{depth * 2}")
            rhs_slot = self._alloc_temp_symbol(f"arith__tmp_expr_{depth * 2 + 1}")

            self._emit_expr_to_a(binary.left)
            self._emit(f"    mov ({lhs_slot}),a")
            self._emit_expr_to_a(binary.right)
            self._emit(f"    mov ({rhs_slot}),a")
            self._emit(f"    mov a,({lhs_slot})")
            self._emit("    mov b,a")
            self._emit(f"    mov a,({rhs_slot})")

            if op == "+":
                self._emit("    add a,b")
            elif op == "-":
                self._emit("    mov c,a")
                self._emit("    mov a,b")
                self._emit("    sub a,c")
            elif op == "&":
                self._emit("    ana a,b")
            elif op == "|":
                self._emit("    ora a,b")
            elif op == "^":
                self._emit("    xra a,b")
            self.expr_tmp_depth -= 1
            return

        if op in {"&&", "||"}:
            self._emit_logical(binary)
            return

        if op in {"==", "!=", "<", ">", "<=", ">="}:
            self._emit_compare(binary)
            return

        self._unsupported(binary, f"Binary operator {op}")

    def _emit_compare(self, binary: c_ast.BinaryOp) -> None:
        true_label = self._new_label("cmp_true")
        false_label = self._new_label("cmp_false")
        end_label = self._new_label("cmp_end")
        check_label = self._new_label("cmp_check")
        depth = self.expr_tmp_depth
        use_signed = self._expr_is_signed_char(binary.left) or self._expr_is_signed_char(binary.right)
        self.expr_tmp_depth += 1
        lhs_slot = self._alloc_temp_symbol(f"arith__tmp_expr_{depth * 2}")
        rhs_slot = self._alloc_temp_symbol(f"arith__tmp_expr_{depth * 2 + 1}")

        self._emit_expr_to_a(binary.left)
        self._emit(f"    mov ({lhs_slot}),a")
        self._emit_expr_to_a(binary.right)
        self._emit(f"    mov ({rhs_slot}),a")
        self._emit(f"    mov a,({lhs_slot})")
        self._emit("    mov b,a")
        self._emit(f"    mov a,({rhs_slot})")
        self._emit("    mov c,a")
        if use_signed:
            self._emit("    mvi a,0x80")
            self._emit("    xra a,b")
            self._emit("    mov b,a")
            self._emit("    mvi a,0x80")
            self._emit("    xra a,c")
            self._emit("    mov c,a")
        self._emit("    mov a,b")
        self._emit("    sub a,c")
        self.expr_tmp_depth -= 1

        op = binary.op
        if op == "==":
            self._emit("    eqi a,0")
            self._emit(f"    jr {false_label}")
            self._emit(f"    jmp {true_label}")
        elif op == "!=":
            self._emit("    nei a,0")
            self._emit(f"    jr {false_label}")
            self._emit(f"    jmp {true_label}")
        elif op == "<":
            self._emit("    skc")
            self._emit(f"    jr {false_label}")
            self._emit(f"    jmp {true_label}")
        elif op == ">":
            self._emit("    skc")
            self._emit(f"    jmp {check_label}")
            self._emit(f"    jmp {false_label}")
            self._emit(f"@{check_label}")
            self._emit("    nei a,0")
            self._emit(f"    jr {false_label}")
            self._emit(f"    jmp {true_label}")
        elif op == "<=":
            self._emit("    skc")
            self._emit(f"    jmp {check_label}")
            self._emit(f"    jr {true_label}")
            self._emit(f"    jmp {true_label}")
            self._emit(f"@{check_label}")
            self._emit("    eqi a,0")
            self._emit(f"    jr {false_label}")
            self._emit(f"    jmp {true_label}")
        elif op == ">=":
            self._emit("    skc")
            self._emit(f"    jr {true_label}")
            self._emit(f"    jmp {false_label}")

        self._emit(f"@{true_label}")
        self._emit("    mvi a,0x01")
        self._emit(f"    jmp {end_label}")
        self._emit(f"@{false_label}")
        self._emit("    mvi a,0x00")
        self._emit(f"@{end_label}")

    def _emit_shift_left(self, left: c_ast.Node, right: c_ast.Node) -> None:
        value_slot = self._alloc_temp_symbol("arith__tmp0")
        count_slot = self._alloc_temp_symbol("arith__tmp1")
        loop_label = self._new_label("shiftl_loop")
        body_label = self._new_label("shiftl_body")
        done_label = self._new_label("shiftl_done")

        self._emit_expr_to_a(left)
        self._emit(f"    mov ({value_slot}),a")
        self._emit_expr_to_a(right)
        self._emit("    ani a,0x07")
        self._emit(f"    mov ({count_slot}),a")

        self._emit(f"@{loop_label}")
        self._emit(f"    mov a,({count_slot})")
        self._emit("    eqi a,0")
        self._emit(f"    jr {body_label}")
        self._emit(f"    jmp {done_label}")

        self._emit(f"@{body_label}")
        self._emit(f"    mov a,({value_slot})")
        self._emit("    add a,a")
        self._emit(f"    mov ({value_slot}),a")
        self._emit(f"    mov a,({count_slot})")
        self._emit("    adi a,0xFF")
        self._emit(f"    mov ({count_slot}),a")
        self._emit(f"    jmp {loop_label}")

        self._emit(f"@{done_label}")
        self._emit(f"    mov a,({value_slot})")

    def _emit_shift_right(self, left: c_ast.Node, right: c_ast.Node) -> None:
        value_slot = self._alloc_temp_symbol("arith__tmp0")
        count_slot = self._alloc_temp_symbol("arith__tmp1")
        quot_slot = self._alloc_temp_symbol("arith__tmp2")
        outer_loop_label = self._new_label("shiftr_outer_loop")
        outer_body_label = self._new_label("shiftr_outer_body")
        outer_done_label = self._new_label("shiftr_outer_done")
        inner_loop_label = self._new_label("shiftr_inner_loop")
        inner_apply_label = self._new_label("shiftr_inner_apply")
        inner_done_label = self._new_label("shiftr_inner_done")

        self._emit_expr_to_a(left)
        self._emit(f"    mov ({value_slot}),a")
        self._emit_expr_to_a(right)
        self._emit("    ani a,0x07")
        self._emit(f"    mov ({count_slot}),a")

        self._emit(f"@{outer_loop_label}")
        self._emit(f"    mov a,({count_slot})")
        self._emit("    eqi a,0")
        self._emit(f"    jr {outer_body_label}")
        self._emit(f"    jmp {outer_done_label}")

        self._emit(f"@{outer_body_label}")
        self._emit("    mvi a,0x00")
        self._emit(f"    mov ({quot_slot}),a")

        self._emit(f"@{inner_loop_label}")
        self._emit(f"    mov a,({value_slot})")
        self._emit("    mvi b,0x02")
        self._emit("    sub a,b")
        self._emit("    skc")
        self._emit(f"    jmp {inner_apply_label}")
        self._emit(f"    jmp {inner_done_label}")

        self._emit(f"@{inner_apply_label}")
        self._emit(f"    mov ({value_slot}),a")
        self._emit(f"    mov a,({quot_slot})")
        self._emit("    adi a,0x01")
        self._emit(f"    mov ({quot_slot}),a")
        self._emit(f"    jmp {inner_loop_label}")

        self._emit(f"@{inner_done_label}")
        self._emit(f"    mov a,({quot_slot})")
        self._emit(f"    mov ({value_slot}),a")
        self._emit(f"    mov a,({count_slot})")
        self._emit("    adi a,0xFF")
        self._emit(f"    mov ({count_slot}),a")
        self._emit(f"    jmp {outer_loop_label}")

        self._emit(f"@{outer_done_label}")
        self._emit(f"    mov a,({value_slot})")

    def _emit_logical(self, binary: c_ast.BinaryOp) -> None:
        eval_right_label = self._new_label("logic_eval_right")
        true_label = self._new_label("logic_true")
        false_label = self._new_label("logic_false")
        end_label = self._new_label("logic_end")

        if binary.op == "&&":
            self._emit_expr_to_a(binary.left)
            self._emit("    nei a,0")
            self._emit(f"    jmp {false_label}")
            self._emit_expr_to_a(binary.right)
            self._emit("    nei a,0")
            self._emit(f"    jmp {false_label}")
            self._emit(f"    jmp {true_label}")
        else:
            self._emit_expr_to_a(binary.left)
            self._emit("    nei a,0")
            self._emit(f"    jmp {eval_right_label}")
            self._emit(f"    jmp {true_label}")
            self._emit(f"@{eval_right_label}")
            self._emit_expr_to_a(binary.right)
            self._emit("    nei a,0")
            self._emit(f"    jmp {false_label}")
            self._emit(f"    jmp {true_label}")

        self._emit(f"@{true_label}")
        self._emit("    mvi a,0x01")
        self._emit(f"    jmp {end_label}")
        self._emit(f"@{false_label}")
        self._emit("    mvi a,0x00")
        self._emit(f"@{end_label}")

    @staticmethod
    def _fmt_imm(value: int) -> str:
        value &= 0xFF
        return f"0x{value:02X}"

    def get_memory_stats(self) -> Dict[str, int]:
        ram_used = self.global_size_total + self.frame_size_total
        if ram_used == 0:
            ram_top = self.ram_base - 1
        else:
            ram_top = self.ram_base + ram_used - 1
        stack_headroom = self.STACK_INIT - (ram_top + 1)
        largest_frame_name = ""
        largest_frame_size = 0
        if self.frame_sizes_by_function:
            largest_frame_name, largest_frame_size = max(
                self.frame_sizes_by_function.items(),
                key=lambda item: (item[1], item[0]),
            )
        return {
            "ram_base": self.ram_base,
            "ram_used": ram_used,
            "ram_top": ram_top,
            "stack_init": self.STACK_INIT,
            "stack_headroom": stack_headroom,
            "global_bytes": self.global_size_total,
            "frame_bytes": self.frame_size_total,
            "largest_frame_size": largest_frame_size,
            "largest_frame_name": largest_frame_name,
        }

    def _is_runtime_internal_symbol(self, sym: str) -> bool:
        return (
            sym.startswith("scv_")
            or sym.startswith("svc_")
            or sym.startswith("sprintf__")
            or sym.startswith("arith__")
            or sym.startswith("scv_api__")
            or sym.startswith("scv_asset__")
            or "__arg_" in sym
        )

    def get_persistent_memory_report_lines(self) -> List[str]:
        categories: List[Tuple[str, List[Tuple[int, str, int]]]] = []
        consumed: Set[str] = set()

        user_arrays: List[Tuple[int, str, int]] = []
        for alias in sorted(self.user_global_array_aliases):
            base_sym = self.ram_array_labels.get(alias)
            if base_sym is None or base_sym not in self.symbol_values:
                continue
            addr = self.symbol_values[base_sym]
            size = self.ram_array_byte_lengths.get(alias, 0)
            user_arrays.append((addr, alias, size))
            consumed.update(sym for sym in self.global_data_symbols if sym.startswith(f"{alias}__ram_"))
        categories.append(("user arrays", user_arrays))

        user_structs: List[Tuple[int, str, int]] = []
        for alias in sorted(self.user_global_struct_aliases):
            mapping = self.struct_instances.get(alias)
            if not mapping:
                continue
            symbols = [sym for sym in mapping.values() if sym in self.symbol_values]
            if not symbols:
                continue
            addr = min(self.symbol_values[sym] for sym in symbols)
            size = len(symbols)
            user_structs.append((addr, alias, size))
            consumed.update(symbols)
        categories.append(("user structs", user_structs))

        user_scalars: List[Tuple[int, str, int]] = []
        runtime_fixed: List[Tuple[int, str, int]] = []
        for sym in self.global_data_symbols:
            if sym in consumed or sym not in self.symbol_values:
                continue
            item = (self.symbol_values[sym], sym, 1)
            if sym in self.user_global_scalar_names and not self._is_runtime_internal_symbol(sym):
                user_scalars.append(item)
            else:
                runtime_fixed.append(item)
        categories.append(("user scalars", sorted(user_scalars)))
        categories.append(("sdk/runtime fixed", sorted(runtime_fixed)))

        lines: List[str] = []
        for label, items in categories:
            if not items:
                continue
            total = sum(size for _, _, size in items)
            lines.append(f"{label} ({total} bytes):")
            for addr, name, size in items:
                lines.append(f"  {name}: {size} byte{'s' if size != 1 else ''} @ 0x{addr:04X}")
        return lines

    @classmethod
    def detect_default_ram_base(
        cls,
        source: str,
        source_path: Optional[Path],
        strict: bool,
    ) -> int:
        detector = cls(strict=strict, ram_base=cls.DEFAULT_RAM_BASE)
        detector.source_path = source_path
        parser = c_parser.CParser()
        sanitized = detector._sanitize_source(
            source,
            current_path=source_path,
            include_stack=set(),
        )
        ast = parser.parse(sanitized)
        if cls._ast_uses_software_sprites(ast):
            return cls.DEFAULT_RAM_BASE
        return cls.RECLAIMED_RAM_BASE

    @classmethod
    def _ast_uses_software_sprites(cls, node: c_ast.Node) -> bool:
        for _, child in node.children():
            if isinstance(child, c_ast.FuncCall):
                name_node = child.name
                if isinstance(name_node, c_ast.ID) and name_node.name in cls.SOFTWARE_SPRITE_APIS:
                    return True
            if cls._ast_uses_software_sprites(child):
                return True
        return False


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert restricted C into l7801/l65 source"
    )
    parser.add_argument("input", help="Path to C source file")
    parser.add_argument("-o", "--output", help="Path to output .l7801 file")
    parser.add_argument(
        "--ram-base",
        default="auto",
        help=(
            "Base RAM address for allocated symbols "
            "(default: auto; uses 0xFFA0 when software-sprite APIs are used, "
            "otherwise reclaims 0xFF80-0xFF9F)"
        ),
    )
    parser.add_argument(
        "--non-strict",
        action="store_true",
        help="Emit TODO comments for unsupported constructs instead of failing",
    )
    parser.add_argument(
        "--validate-cmd",
        help="Optional assembler command used to validate generated output, e.g. '/path/to/l7801'",
    )
    parser.add_argument(
        "--validate-backend",
        choices=["l7801", "asm7801"],
        default="l7801",
        help="Validation backend: external l7801 dump check or in-repo asm7801 assembler (default: l7801)",
    )
    parser.add_argument(
        "--validate-compare-bin",
        help="Optional .bin path for byte-compare when using --validate-backend asm7801",
    )
    parser.add_argument(
        "--warn-headroom",
        default="16",
        help="Warn when RAM/stack headroom is below this byte count (default: 16)",
    )
    parser.add_argument(
        "--cart-metadata-output",
        help="Optional path to write SCV cartridge metadata JSON sidecar",
    )
    parser.add_argument(
        "--emit-cart-package",
        action="store_true",
        help="Assemble the generated .l7801 and emit a cartridge package directory using current banking metadata",
    )
    parser.add_argument(
        "--cart-package-dir",
        help="Optional output directory for emitted cartridge package files",
    )
    return parser.parse_args(argv)


def run_validation(validate_cmd: str, output_file: Path) -> Tuple[int, str]:
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".lua", delete=False) as tf:
        dump_path = Path(tf.name)

    try:
        proc = subprocess.run(
            [validate_cmd, "-d", str(dump_path), str(output_file)],
            capture_output=True,
            text=True,
            check=False,
        )
        merged = (proc.stdout or "") + (proc.stderr or "")

        if proc.returncode != 0:
            return proc.returncode, merged

        try:
            dump_text = dump_path.read_text(encoding="utf-8")
        except OSError:
            return 1, merged + "\nvalidation error: -d dump file was not created"

        last_line = dump_text.rstrip().splitlines()[-1] if dump_text.strip() else ""
        if "writebin" not in last_line:
            error_lines = [
                line for line in dump_text.splitlines()
                if "error" in line.lower()
            ]
            detail = "\n".join(error_lines[:10]) if error_lines else "(no explicit error in dump)"
            return 1, (
                merged
                + f"\nvalidation error: Lua dump does not end with writebin "
                f"-- assembly did not complete successfully\n"
                + f"last dump line: {last_line!r}\n"
                + detail
            )

        return 0, merged
    finally:
        dump_path.unlink(missing_ok=True)


def run_validation_asm7801(output_file: Path, compare_bin: Optional[Path]) -> Tuple[int, str]:
    import tempfile

    asm7801_path = Path(__file__).with_name("asm7801.py")
    if not asm7801_path.exists():
        return 2, f"validation error: asm7801 backend not found at {asm7801_path}"

    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tf:
        assembled_bin = Path(tf.name)

    try:
        cmd = [
            sys.executable,
            str(asm7801_path),
            str(output_file),
            "--assemble-bin",
            str(assembled_bin),
        ]
        if compare_bin is not None:
            cmd.extend(["--compare-bin", str(compare_bin)])

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        merged = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, merged
    finally:
        assembled_bin.unlink(missing_ok=True)


def _assemble_with_asm7801(output_file: Path):
    from asm7801 import assemble_program, parse_program

    text = output_file.read_text(encoding="utf-8")
    program = parse_program(text)
    return assemble_program(program)


def _label_span_from_assembled(assembled, start_label: str, end_label: str) -> Tuple[int, int]:
    labels = assembled.labels
    if start_label not in labels:
        raise ConversionError(f"Packaging label '{start_label}' not found in assembled image")
    if end_label not in labels:
        raise ConversionError(f"Packaging label '{end_label}' not found in assembled image")

    start_addr = labels[start_label]
    end_addr = labels[end_label]
    next_addrs = sorted(addr for addr in labels.values() if addr > end_addr)
    exclusive_end_addr = next_addrs[0] if next_addrs else assembled.origin + len(assembled.image)

    start = start_addr - assembled.origin
    end = exclusive_end_addr - assembled.origin
    if start < 0 or end < start or end > len(assembled.image):
        raise ConversionError(
            f"Invalid assembled label span for {start_label}..{end_label}: start={start} end={end}"
        )
    return start, end


def emit_cart_package(
    emitter: L7801L65Emitter,
    output_file: Path,
    package_dir: Path,
) -> Dict[str, object]:
    assembled = _assemble_with_asm7801(output_file)
    metadata = emitter.get_cart_metadata()
    bank_sizes = emitter.get_cart_bank_sizes()
    banked_call_edges = emitter.get_banked_call_edges()
    trampoline_edges = emitter.get_trampoline_call_edges()
    illegal_banked_edges = emitter.get_illegal_banked_call_edges()

    if illegal_banked_edges:
        edge_descriptions = ", ".join(
            f"{edge['caller']}[bank {edge['caller_bank']}] -> {edge['callee']}[bank {edge['callee_bank']}]"
            for edge in illegal_banked_edges
        )
        raise ConversionError(
            "Current cart packaging cannot place callers that already live in non-zero banks; "
            f"illegal banked call edges: {edge_descriptions}"
        )

    package_dir.mkdir(parents=True, exist_ok=True)

    manifest: Dict[str, object] = {
        "version": 1,
        "profile": metadata["profile"],
        "layout": metadata["layout"],
        "status": "partial-package",
        "bank_sizes": bank_sizes,
        "runtime_origin": assembled.origin,
        "hook_backend": metadata["hook_backend"],
        "bank_files": [],
        "code_placements": [],
        "rom_data_placements": [],
        "unpackaged_functions": [],
        "trampolines": metadata["trampolines"],
        "trampoline_call_edges": trampoline_edges,
        "illegal_banked_call_edges": illegal_banked_edges,
        "banked_call_edges": banked_call_edges,
        "warnings": [],
    }

    bank0_path = package_dir / "bank0_runtime.bin"
    bank0_path.write_bytes(assembled.image)
    manifest["bank_files"].append(
        {
            "bank": 0,
            "path": bank0_path.name,
            "kind": "runtime-flat-image",
            "size": len(assembled.image),
        }
    )

    bank_buffers = [bytearray(size) for size in bank_sizes]
    bank_offsets = [0 for _ in bank_sizes]
    has_packaged_aux_content = False

    for trampoline in metadata["trampolines"]:
        bank_id = int(trampoline["bank"])
        start, end = _label_span_from_assembled(
            assembled,
            str(trampoline["body_label"]),
            str(trampoline["end_label"]),
        )
        payload = assembled.image[start:end]
        bank_size = bank_sizes[bank_id]
        bank_offset = bank_offsets[bank_id]
        if bank_offset + len(payload) > bank_size:
            raise ConversionError(
                f"Bank {bank_id} overflow while packaging function '{trampoline['function']}' ({bank_offset + len(payload)} > {bank_size})"
            )

        bank_buffers[bank_id][bank_offset:bank_offset + len(payload)] = payload
        manifest["code_placements"].append(
            {
                "function": trampoline["function"],
                "bank": bank_id,
                "size": len(payload),
                "flat_image_offset": start,
                "bank_offset": bank_offset,
                "body_label": trampoline["body_label"],
            }
        )
        bank_offsets[bank_id] = bank_offset + len(payload)
        has_packaged_aux_content = True

    for block in emitter.rom_data_blocks:
        bank_id = emitter.rom_bank_hints.get(block.alias_name, 0)
        if bank_id == 0:
            continue

        if block.label not in assembled.labels:
            raise ConversionError(
                f"Unable to package ROM data '{block.alias_name}': label '{block.label}' not found in assembled image"
            )

        start = assembled.labels[block.label] - assembled.origin
        if start < 0:
            raise ConversionError(
                f"Unable to package ROM data '{block.alias_name}': assembled offset underflow"
            )
        end = start + len(block.data)
        if end > len(assembled.image):
            raise ConversionError(
                f"Unable to package ROM data '{block.alias_name}': assembled image slice exceeds image size"
            )

        bank_offset = bank_offsets[bank_id]
        bank_size = bank_sizes[bank_id]
        if bank_offset + len(block.data) > bank_size:
            raise ConversionError(
                f"Bank {bank_id} overflow while packaging ROM data '{block.alias_name}' ({bank_offset + len(block.data)} > {bank_size})"
            )

        payload = assembled.image[start:end]
        bank_buffers[bank_id][bank_offset:bank_offset + len(payload)] = payload
        manifest["rom_data_placements"].append(
            {
                "name": block.alias_name,
                "bank": bank_id,
                "size": len(payload),
                "flat_image_offset": start,
                "bank_offset": bank_offset,
            }
        )
        bank_offsets[bank_id] = bank_offset + len(payload)
        has_packaged_aux_content = True

    for bank_id in range(1, len(bank_sizes)):
        if bank_offsets[bank_id] == 0:
            continue
        has_code = any(placement["bank"] == bank_id for placement in manifest["code_placements"])
        has_data = any(placement["bank"] == bank_id for placement in manifest["rom_data_placements"])
        bank_path = package_dir / f"bank{bank_id}_payload.bin"
        bank_path.write_bytes(bytes(bank_buffers[bank_id][:bank_offsets[bank_id]]))
        manifest["bank_files"].append(
            {
                "bank": bank_id,
                "path": bank_path.name,
                "kind": "bank-payload",
                "size": bank_offsets[bank_id],
                "contains_code": has_code,
                "contains_data": has_data,
            }
        )

    unpackaged_functions = [
        {"name": fn_name, "bank": bank_id}
        for fn_name, bank_id in sorted(emitter.function_bank_hints.items())
        if bank_id != 0 and fn_name not in {placement["function"] for placement in manifest["code_placements"]}
    ]
    manifest["unpackaged_functions"] = unpackaged_functions
    if unpackaged_functions:
        manifest["warnings"].append(
            "Some functions assigned to non-zero banks were not emitted into bank payloads."
        )
    if not has_packaged_aux_content:
        manifest["warnings"].append(
            "No non-zero-bank ROM data blocks were packaged; auxiliary bank payloads are empty or omitted."
        )
    if manifest["code_placements"] and not unpackaged_functions:
        manifest["status"] = "code-and-data-packaged"
    elif not unpackaged_functions and has_packaged_aux_content:
        manifest["status"] = "data-packaged"

    manifest_path = package_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {
        "manifest_path": manifest_path,
        "manifest": manifest,
    }


def main(argv: List[str]) -> int:
    args = parse_args(argv)

    try:
        warn_headroom = int(args.warn_headroom, 0)
    except ValueError:
        print(f"error: invalid --warn-headroom value: {args.warn_headroom}", file=sys.stderr)
        return 2

    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else input_path.with_suffix(".l7801")

    source = input_path.read_text(encoding="utf-8")

    if args.ram_base == "auto":
        try:
            ram_base = L7801L65Emitter.detect_default_ram_base(
                source,
                source_path=input_path,
                strict=not args.non_strict,
            )
        except ConversionError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    else:
        try:
            ram_base = int(args.ram_base, 0)
        except ValueError:
            print(f"error: invalid --ram-base value: {args.ram_base}", file=sys.stderr)
            return 2

    emitter = L7801L65Emitter(strict=not args.non_strict, ram_base=ram_base)

    try:
        output = emitter.convert(source, source_path=input_path)
    except ConversionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    output_path.write_text(output, encoding="utf-8")
    print(f"wrote {output_path}")
    if emitter.has_cart_metadata():
        cart_metadata_path = (
            Path(args.cart_metadata_output)
            if args.cart_metadata_output
            else output_path.with_suffix(".cart.json")
        )
        cart_metadata_path.write_text(
            json.dumps(emitter.get_cart_metadata(), indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {cart_metadata_path}")
        if args.emit_cart_package:
            cart_package_dir = (
                Path(args.cart_package_dir)
                if args.cart_package_dir
                else output_path.with_suffix("")
            )
            try:
                package_result = emit_cart_package(emitter, output_path, cart_package_dir)
            except ConversionError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            print(f"wrote {package_result['manifest_path']}")
    elif args.emit_cart_package:
        print(
            "error: --emit-cart-package requires banking metadata from pragmas or non-flat cart profile",
            file=sys.stderr,
        )
        return 2
    if args.ram_base == "auto":
        if ram_base == L7801L65Emitter.RECLAIMED_RAM_BASE:
            print(
                "memory policy: no software-sprite API calls detected; "
                "reclaiming shadow RAM with ram_base=0xFF80"
            )
        else:
            print(
                "memory policy: software-sprite API calls detected; "
                "reserving shadow RAM with ram_base=0xFFA0"
            )

    stats = emitter.get_memory_stats()
    print(
        "memory: "
        f"ram_base=0x{stats['ram_base']:04X}, "
        f"ram_used={stats['ram_used']} bytes, "
        f"ram_top=0x{stats['ram_top']:04X}, "
        f"stack_init=0x{stats['stack_init']:04X}, "
        f"headroom={stats['stack_headroom']} bytes"
    )
    print(
        "memory breakdown: "
        f"globals={stats['global_bytes']} bytes, "
        f"frame_area={stats['frame_bytes']} bytes, "
        f"largest_frame={stats['largest_frame_size']} bytes"
        + (
            f" ({stats['largest_frame_name']})"
            if stats["largest_frame_name"]
            else ""
        )
    )
    for index, line in enumerate(emitter.get_persistent_memory_report_lines()):
        prefix = "persistent RAM detail: " if index == 0 else ""
        print(f"{prefix}{line}")
    if stats["stack_headroom"] < warn_headroom:
        print(
            "warning: low RAM/stack headroom: "
            f"{stats['stack_headroom']} bytes (threshold {warn_headroom})",
            file=sys.stderr,
        )

    compare_bin_path = Path(args.validate_compare_bin) if args.validate_compare_bin else None
    if args.validate_backend == "asm7801":
        if compare_bin_path is None:
            default_compare = output_path.with_suffix(".bin")
            if default_compare.exists():
                compare_bin_path = default_compare
        code, text = run_validation_asm7801(output_path, compare_bin_path)
        print(f"validation exit code: {code}")
        if text.strip():
            print(text.rstrip())
        return code

    if args.validate_cmd:
        code, text = run_validation(args.validate_cmd, output_path)
        print(f"validation exit code: {code}")
        if text.strip():
            print(text.rstrip())
        return code

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
