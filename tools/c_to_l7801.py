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

    API_ALIASES: Dict[str, str] = {
        "scv_bios_add16": "scv_bios_add16_hi",
        "scv_bios_sub16": "scv_bios_sub16_hi",
        "svc_bios_add16": "scv_bios_add16_hi",
        "svc_bios_sub16": "scv_bios_sub16_hi",
        "svc_bios_clear_text_vram": "scv_bios_clear_text_vram",
        "svc_bios_clear_pattern_vram": "scv_bios_clear_pattern_vram",
        "svc_bios_clear_hw_sprites": "scv_bios_clear_hw_sprites",
    }

    SCV_API_PARAMS: Dict[str, List[str]] = {
        "strlen": ["str"],
        "sprintf": ["dst", "fmt", "value"],
        "scv_print_char": ["x", "y", "ch"],
        "scv_print_string": ["x", "y", "str"],
        "scv_draw_tile": ["row", "col", "tile_id"],
        "scv_draw_bg_tile": ["row", "col", "tile_id"],
        "scv_set_bg_scroll": ["scroll_x", "scroll_y"],
        "scv_draw_bg_tile_scrolled": ["row", "col", "tile_id"],
        "scv_scroll_bg_right": [],
        "scv_scroll_bg_left": [],
        "scv_scroll_bg_down": [],
        "scv_scroll_bg_up": [],
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
        "scv_stop_sound": [],
        "scv_play_tone_raw": ["p1", "p2", "p3"],
        "scv_play_tone_packet": ["pitch", "param"],
        "scv_check_collision": ["id_a", "id_b"],
        "scv_wait_vblank": [],
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
            "    mov (sprintf__tmp_started),a",
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
            "    mvi a,0x01",
            "    mov (sprintf__tmp_started),a",
            "@{fn}_skip_hundreds",
            "    mov a,(sprintf__tmp_started)",
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
            "    add l,a",
            "    aci h,0",
            "    mov a,({fn}__arg_ch)",
            "    stax (hl)",
            "    ret",
        ],
        "scv_print_string": [
            "    mvi a,0x20",
            "    mov (scv_print_string__tmp_guard),a",
            "@{fn}_loop",
            "    mov a,(scv_print_string__tmp_guard)",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_check_char",
            "    ret",
            "@{fn}_check_char",
            "    ldax (de)",
            "    mov b,a",
            "    eqi a,0",
            "    skz",
            "    jmp {fn}_print_char",
            "    ret",
            "@{fn}_print_char",
            "    mov a,b",
            "    mov (scv_print_char__arg_ch),a",
            "    mov a,({fn}__arg_y)",
            "    mov (scv_print_char__arg_y),a",
            "    mov a,({fn}__arg_x)",
            "    mov (scv_print_char__arg_x),a",
            "    call fn_scv_print_char",
            "    inx de",
            "    mov a,({fn}__arg_x)",
            "    adi a,0x01",
            "    mov ({fn}__arg_x),a",
            "    mov a,(scv_print_string__tmp_guard)",
            "    adi a,0xFF",
            "    mov (scv_print_string__tmp_guard),a",
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
            "    add l,a",
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
            "    add l,a",
            "    aci h,0",
            "    mov a,({fn}__arg_tile_id)",
            "    ani a,0x3F",
            "    stax (hl)",
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
            "    add l,a",
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
            "    add l,a",
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
            "    add l,a",
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
            "    add l,a",
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
            "    add l,a",
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
            "    mvi a,0x32",
            "    aci a,0",
            "    mov h,a",
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
            "    mvi a,0x32",
            "    aci a,0",
            "    mov h,a",
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
            "    mvi a,0x32",
            "    aci a,0",
            "    mov h,a",
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
            "    mvi a,0x32",
            "    aci a,0",
            "    mov h,a",
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
            "    mvi a,0x32",
            "    aci a,0",
            "    mov h,a",
            "    inx hl",
            "    inx hl",
            "    inx hl",
            "    mov a,({fn}__arg_pattern)",
            "    ani a,0x3F",
            "    mvi b,0x40",
            "    ora a,b",
            "    stax (hl)",
            "    ret",
        ],
        "scv_set_hw_sprite_colour": [
            "    mov a,({fn}__arg_id)",
            "    add a,a",
            "    add a,a",
            "    mov l,a",
            "    mvi a,0x32",
            "    aci a,0",
            "    mov h,a",
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
            "    ani a,0x3F",
            "    mvi b,0x40",
            "    ora a,b",
            "    mov c,a",
            "    mov a,({fn}__arg_id)",
            "    add a,a",
            "    add a,a",
            "    mov l,a",
            "    mvi a,0x32",
            "    aci a,0",
            "    mov h,a",
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
            "    mvi a,0x32",
            "    aci a,0",
            "    mov h,a",
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
            "    mvi a,0x32",
            "    aci a,0",
            "    mov h,a",
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
            "    mvi a,0x32",
            "    aci a,0",
            "    mov h,a",
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
            "    mvi a,0x32",
            "    aci a,0",
            "    mov h,a",
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
            "    mvi a,0x32",
            "    aci a,0",
            "    mov h,a",
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
            "    mvi a,0x32",
            "    aci a,0",
            "    mov h,a",
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
            "    ldaxi (hl)",
            "    mov c,a",
            "    inx hl",
            "    ldaxi (hl)",
            "    nei a,0",
            "    jre {fn}_no_collision",
            "    mov a,({fn}__arg_id_b)",
            "    add a,a",
            "    add a,a",
            "    adi a,0x80",
            "    mov l,a",
            "    mvi h,0xFF",
            "    ldaxi (hl)",
            "    eqa a,b",
            "    jre {fn}_no_collision",
            "    ldaxi (hl)",
            "    eqa a,c",
            "    jre {fn}_no_collision",
            "    inx hl",
            "    ldaxi (hl)",
            "    nei a,0",
            "    jre {fn}_no_collision",
            "    mvi a,0x01",
            "    mov (scv_collision_result),a",
            "    ret",
            "@{fn}_no_collision",
            "    mvi a,0x00",
            "    mov (scv_collision_result),a",
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

    def __init__(self, strict: bool = True, ram_base: int = 0xFF80) -> None:
        self.strict = strict
        self.ram_base = ram_base
        self.lines: List[str] = []
        self.data_symbols: List[str] = []
        self.symbol_values: Dict[str, int] = {}
        self.globals: Set[str] = set()
        self.current_fn: Optional[FunctionContext] = None
        self.function_params: Dict[str, List[str]] = {}
        self.defined_functions: Set[str] = set()
        self.extern_functions: Set[str] = set()
        self.label_counter = 0
        self.source_path: Optional[Path] = None
        self.asset_directives: List[AssetDirective] = []
        self.asset_functions: Dict[str, AssetFunction] = {}
        self.asset_bulk_functions: Dict[str, List[str]] = {}
        self.sound_assets: List[SoundAsset] = []
        self.rom_constants: Dict[str, int] = {}
        self.rom_data_blocks: List[RomDataBlock] = []
        self.rom_array_labels: Dict[str, str] = {}
        self.rom_array_lengths: Dict[str, int] = {}
        self.rom_array_values: Dict[str, List[int]] = {}
        self.ram_array_labels: Dict[str, str] = {}
        self.ram_array_lengths: Dict[str, int] = {}
        self.struct_defs: Dict[str, List[str]] = {}
        self.struct_instances: Dict[str, Dict[str, str]] = {}

    def convert(self, source: str, source_path: Optional[Path] = None) -> str:
        self.source_path = source_path
        self.asset_directives = []
        self.asset_functions = {}
        self.asset_bulk_functions = {}
        self.sound_assets = []
        self.rom_constants = {}
        self.rom_data_blocks = []
        self.rom_array_labels = {}
        self.rom_array_lengths = {}
        self.rom_array_values = {}
        self.ram_array_labels = {}
        self.ram_array_lengths = {}
        self.struct_defs = {}
        self.struct_instances = {}
        self.function_params = {}
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
        self._insert_symbol_table()

        return "\n".join(self.lines) + "\n"

    def _register_asset_function_signatures(self) -> None:
        for function_name in self.asset_functions:
            self.function_params[function_name] = ["pattern_slot"]

    def _collect_function_signatures(self, ast: c_ast.FileAST) -> None:
        self.function_params = {}
        defined: Set[str] = set()

        # First pass: collect definitions (FuncDef nodes)
        for ext in ast.ext:
            if not isinstance(ext, c_ast.FuncDef):
                continue
            defined.add(ext.decl.name)
            params: List[str] = []
            decl = ext.decl.type
            if isinstance(decl, c_ast.FuncDecl) and decl.args:
                for param in decl.args.params:
                    if isinstance(param, c_ast.Decl) and param.name:
                        params.append(param.name)
            self.function_params[ext.decl.name] = params

        self.defined_functions = set(defined)

        # Second pass: collect prototypes (extern declarations)
        for ext in ast.ext:
            if not isinstance(ext, c_ast.Decl):
                continue
            if not isinstance(ext.type, c_ast.FuncDecl):
                continue
            if ext.name in defined:
                continue
            params = []
            if ext.type.args:
                for param in ext.type.args.params:
                    if isinstance(param, c_ast.Decl) and param.name:
                        params.append(param.name)
            self.function_params[ext.name] = params

    def _emit_extern_stubs(self) -> None:
        if not self.extern_functions:
            return

        if "scv_print_string" in self.extern_functions:
            self.extern_functions.add("scv_print_char")
            if "scv_print_char" not in self.function_params:
                self.function_params["scv_print_char"] = self.SCV_API_PARAMS["scv_print_char"]

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
                self._alloc_symbol("sprintf__tmp_started")

            self._emit(f"@fn_{fn}")
            asset_fn = self.asset_functions.get(fn)
            bulk_asset_frames = self.asset_bulk_functions.get(fn)
            sound_asset = next((s for s in self.sound_assets if s.play_fn == fn), None)
            if asset_fn is not None:
                impl = self._build_asset_loader_impl(asset_fn)
            elif bulk_asset_frames is not None:
                impl = self._build_asset_bulk_loader_impl(fn, bulk_asset_frames)
            elif sound_asset is not None:
                impl = self._build_sound_play_impl(fn, sound_asset)
            else:
                impl = self.SCV_API_IMPLS.get(fn)
            if impl is not None:
                for line in impl:
                    self._emit(line.format(fn=fn))
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
        if asset_fn.pattern_mode == "raw":
            base_hi = "0x20"
            slot_mask = "0x7F"
        elif asset_fn.pattern_mode == "background":
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
            "    mvi a,0x20",
            "    add e,a",
            "    aci d,0",
            "    dcr b",
            f"    jre {function_name}_slot_loop",
            f"@{function_name}_slot_done",
            "    mvi b,0x20",
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
            if stripped.startswith("#"):
                if stripped.startswith("#pragma scv_asset sound"):
                    self._parse_sound_directive(stripped)
                    continue
                if stripped.startswith("#pragma scv_asset"):
                    self._parse_asset_directive(stripped)
                    continue
                if stripped.startswith("#include"):
                    include_match = re.fullmatch(r'#include\s+"([^"]+)"', stripped)
                    if include_match:
                        include_raw = include_match.group(1)
                        if include_raw.endswith(".c"):
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
                            expanded = self._sanitize_source(
                                include_source,
                                current_path=include_path,
                                include_stack=include_stack,
                            )
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
            self.asset_functions[function_name] = AssetFunction(
                function_name=function_name,
                frame=frame,
                pattern_mode="background" if is_background_asset else "sprite",
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
        return f"{fn_name}__arg_{param_name}"

    def _emit(self, line: str = "") -> None:
        self.lines.append(line)

    def _unsupported(self, node: c_ast.Node, message: str) -> None:
        if self.strict:
            coord = getattr(node, "coord", "unknown")
            raise ConversionError(f"{message} at {coord}")
        self._emit(f"    -- TODO unsupported: {message}")

    def _alloc_symbol(self, name: str, init: int = 0) -> str:
        if name not in self.symbol_values:
            addr = self.ram_base + len(self.symbol_values)
            if addr >= self.STACK_INIT:
                raise ConversionError(
                    f"RAM symbol overflow: {name} would be allocated at 0x{addr:04X}, "
                    f"which collides with stack at 0x{self.STACK_INIT:04X}. "
                    "Lower --ram-base, reduce symbols, or adjust stack init."
                )
            self.symbol_values[name] = addr
            self.data_symbols.append(name)
        return name

    def _declare_global(self, decl: c_ast.Decl) -> None:
        self._ensure_known_types_from_decl(decl)

        if decl.name is None:
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
                self._register_rom_data_block(decl.name, values)
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
            self._alloc_ram_array(decl.name, length)
            return

        struct_type = self._extract_struct_type_from_decl(decl)
        if struct_type is not None:
            fields = self._flatten_struct_fields(struct_type)
            self._alloc_struct_instance(decl.name, fields)
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
            return

        self._alloc_symbol(decl.name)

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

        expected_len: Optional[int] = None
        if decl.type.dim is not None:
            expected_len = self._eval_const_u8(decl.type.dim)

        if init is None:
            coord = getattr(decl, "coord", "unknown")
            raise ConversionError(
                f"const array '{decl.name}' requires an initializer at {coord}"
            )

        values: List[int]
        if isinstance(init, c_ast.InitList):
            values = [self._eval_const_u8(expr) for expr in (init.exprs or [])]
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

    def _register_rom_data_block(self, alias_name: str, values: List[int]) -> None:
        label = f"{alias_name}__rom"
        self.rom_data_blocks.append(
            RomDataBlock(alias_name=alias_name, label=label, data=values)
        )
        self.rom_array_labels[alias_name] = label
        self.rom_array_lengths[alias_name] = len(values)
        self.rom_array_values[alias_name] = list(values)

    def _alloc_ram_array(self, alias_name: str, length: int) -> None:
        if length <= 0:
            raise ConversionError(f"RAM array '{alias_name}' must have size > 0")
        if alias_name in self.ram_array_labels:
            return
        base_symbol = self._alloc_symbol(f"{alias_name}__ram_0")
        for idx in range(1, length):
            self._alloc_symbol(f"{alias_name}__ram_{idx}")
        self.ram_array_labels[alias_name] = base_symbol
        self.ram_array_lengths[alias_name] = length

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

        self._unsupported(struct_ref, "Only direct/chained struct.field access is supported")
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

    def _emit_function(self, func: c_ast.FuncDef) -> None:
        fn_name = func.decl.name
        fn = f"fn_{fn_name}"
        end_label = self._new_label(f"{fn}_end")
        param_symbols: Dict[str, str] = {}
        for param_name in self.function_params.get(fn_name, []):
            slot = self._alloc_symbol(self._arg_symbol_name(fn_name, param_name))
            param_symbols[param_name] = slot

        self.current_fn = FunctionContext(
            name=fn_name,
            end_label=end_label,
            param_symbols=param_symbols,
        )

        self._emit(f"@{fn}")

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
            self._alloc_ram_array(scoped_alias, length)
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
            return

        sym = self._resolve_symbol(decl.name)
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
            target = self._resolve_struct_field_symbol(assign.lvalue)
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
        self._emit_stmt(node.stmt)
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
        args = list(call.args.exprs) if call.args and call.args.exprs else []

        if callee == "scv_print_string":
            if len(args) != 3:
                raise ConversionError(
                    f"Call arity mismatch for {callee}: expected 3, got {len(args)}"
                )

            # Runtime scv_print_string implementation uses this guard symbol.
            self._alloc_symbol("scv_print_string__tmp_guard")

            self._emit_expr_to_a(args[0])
            src_slot_x = self._alloc_symbol(self._arg_symbol_name(callee, "x"))
            self._emit(f"    mov ({src_slot_x}),a")

            self._emit_expr_to_a(args[1])
            src_slot_y = self._alloc_symbol(self._arg_symbol_name(callee, "y"))
            self._emit(f"    mov ({src_slot_y}),a")

            def emit_inline_chars(values: List[int]) -> None:
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
            # runtime string loops.
            if isinstance(args[2], c_ast.Constant) and args[2].type == "string":
                raw = args[2].value
                if len(raw) < 2 or raw[0] != '"' or raw[-1] != '"':
                    coord = getattr(args[2], "coord", "unknown")
                    raise ConversionError(f"Unsupported string literal {raw} at {coord}")

                decoded = bytes(raw[1:-1], "utf-8").decode("unicode_escape")
                emit_inline_chars([ord(ch) & 0xFF for ch in decoded])
                return

            if isinstance(args[2], c_ast.ID):
                rom_alias = self._resolve_rom_array_alias(args[2].name)
                if rom_alias is not None:
                    values = self.rom_array_values[rom_alias]
                    inline_values: List[int] = []
                    for v in values:
                        if v == 0:
                            break
                        inline_values.append(v & 0xFF)
                        if len(inline_values) >= 0x20:
                            break
                    emit_inline_chars(inline_values)
                return

            rom_label: Optional[str] = None
            ram_label: Optional[str] = None

            if isinstance(args[2], c_ast.ID):
                alias = self._resolve_rom_array_alias(args[2].name)
                if alias is not None:
                    rom_label = self.rom_array_labels[alias]
                if rom_label is None:
                    ram_alias = self._resolve_ram_array_alias(args[2].name)
                    if ram_alias is not None:
                        ram_label = self.ram_array_labels[ram_alias]

            if rom_label is None and ram_label is None:
                coord = getattr(args[2], "coord", "unknown")
                raise ConversionError(
                    f"scv_print_string third argument must be a ROM or RAM array identifier or string literal at {coord}"
                )

            if rom_label is not None:
                self._emit(f"    lxi de,{rom_label}")
            else:
                self._emit(f"    lxi de,{ram_label}")
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
            sym = self._resolve_struct_field_symbol(expr)
            if sym in self.rom_constants:
                self._emit(f"    mvi a,{self._fmt_imm(self.rom_constants[sym])}")
            else:
                self._emit(f"    mov a,({sym})")
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
        if not isinstance(expr.name, c_ast.ID):
            self._unsupported(expr, "Only direct array variable indexing is supported")
            return

        alias = self._resolve_rom_array_alias(expr.name.name)
        if alias is None:
            coord = getattr(expr, "coord", "unknown")
            raise ConversionError(
                f"Array '{expr.name.name}' is not a const/static const ROM array at {coord}"
            )

        label = self.rom_array_labels[alias]
        arr_len = self.rom_array_lengths[alias]

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
                self._emit("    add l,a")
                self._emit("    aci h,0")
            self._emit("    ldax (hl)")
            return

        # Runtime index: no static bounds guarantee, perform ROM base + index.
        self._emit_expr_to_a(expr.subscript)
        self._emit("    mov b,a")
        self._emit(f"    lxi hl,{label}")
        self._emit("    mov a,b")
        self._emit("    add l,a")
        self._emit("    aci h,0")
        self._emit("    ldax (hl)")

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
                self._emit("    add l,a")
                self._emit("    aci h,0")
            self._emit("    ldax (hl)")
            return

        self._emit_expr_to_a(idx_expr)
        self._emit("    mov b,a")
        self._emit(f"    lxi hl,{label}")
        self._emit("    mov a,b")
        self._emit("    add l,a")
        self._emit("    aci h,0")
        self._emit("    ldax (hl)")

    def _emit_binary(self, binary: c_ast.BinaryOp) -> None:
        op = binary.op

        if op in {"+", "-", "&", "|", "^", "*", "<<", ">>"}:
            if op == "*":
                lhs_slot = self._alloc_symbol("mul__lhs")
                rhs_slot = self._alloc_symbol("mul__rhs")
                acc_slot = self._alloc_symbol("mul__acc")
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

            self._emit_expr_to_a(binary.left)
            self._emit("    mov b,a")
            self._emit_expr_to_a(binary.right)

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

        self._emit_expr_to_a(binary.left)
        self._emit("    mov b,a")
        self._emit_expr_to_a(binary.right)
        self._emit("    mov c,a")
        self._emit("    mov a,b")
        self._emit("    sub a,c")

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
            # lti-based lowering has shown unreliable behavior for bounds checks in SCV demos.
            # Re-express left < right as (right - left) > 0 and use gti, which is stable.
            self._emit("    mov a,c")
            self._emit("    sub a,b")
            self._emit("    gti a,0")
            self._emit(f"    jr {false_label}")
            self._emit(f"    jmp {true_label}")
        elif op == ">":
            self._emit("    gti a,0")
            self._emit(f"    jr {false_label}")
            self._emit(f"    jmp {true_label}")
        elif op == "<=":
            self._emit("    gti a,0")
            self._emit(f"    jr {true_label}")
            self._emit(f"    jmp {false_label}")
        elif op == ">=":
            self._emit("    lti a,0")
            self._emit(f"    jr {true_label}")
            self._emit(f"    jmp {false_label}")

        self._emit(f"@{true_label}")
        self._emit("    mvi a,0x01")
        self._emit(f"    jmp {end_label}")
        self._emit(f"@{false_label}")
        self._emit("    mvi a,0x00")
        self._emit(f"@{end_label}")

    def _emit_shift_left(self, left: c_ast.Node, right: c_ast.Node) -> None:
        value_slot = self._alloc_symbol("shiftl__value")
        count_slot = self._alloc_symbol("shiftl__count")
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
        value_slot = self._alloc_symbol("shiftr__value")
        count_slot = self._alloc_symbol("shiftr__count")
        quot_slot = self._alloc_symbol("shiftr__quot")
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
        ram_used = len(self.data_symbols)
        if ram_used == 0:
            ram_top = self.ram_base - 1
        else:
            ram_top = self.ram_base + ram_used - 1
        stack_headroom = self.STACK_INIT - (ram_top + 1)
        return {
            "ram_base": self.ram_base,
            "ram_used": ram_used,
            "ram_top": ram_top,
            "stack_init": self.STACK_INIT,
            "stack_headroom": stack_headroom,
        }


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert restricted C into l7801/l65 source"
    )
    parser.add_argument("input", help="Path to C source file")
    parser.add_argument("-o", "--output", help="Path to output .l7801 file")
    parser.add_argument(
        "--ram-base",
        default="0xFFA0",
        help="Base RAM address for allocated symbols (default: 0xFFA0; 0xFF80-0xFF9F reserved for sprite shadow table)",
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
        "--warn-headroom",
        default="16",
        help="Warn when RAM/stack headroom is below this byte count (default: 16)",
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


def main(argv: List[str]) -> int:
    args = parse_args(argv)

    try:
        ram_base = int(args.ram_base, 0)
    except ValueError as exc:
        print(f"error: invalid --ram-base value: {args.ram_base}", file=sys.stderr)
        return 2

    try:
        warn_headroom = int(args.warn_headroom, 0)
    except ValueError:
        print(f"error: invalid --warn-headroom value: {args.warn_headroom}", file=sys.stderr)
        return 2

    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else input_path.with_suffix(".l7801")

    source = input_path.read_text(encoding="utf-8")
    emitter = L7801L65Emitter(strict=not args.non_strict, ram_base=ram_base)

    try:
        output = emitter.convert(source, source_path=input_path)
    except ConversionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    output_path.write_text(output, encoding="utf-8")
    print(f"wrote {output_path}")

    stats = emitter.get_memory_stats()
    print(
        "memory: "
        f"ram_base=0x{stats['ram_base']:04X}, "
        f"ram_used={stats['ram_used']} bytes, "
        f"ram_top=0x{stats['ram_top']:04X}, "
        f"stack_init=0x{stats['stack_init']:04X}, "
        f"headroom={stats['stack_headroom']} bytes"
    )
    if stats["stack_headroom"] < warn_headroom:
        print(
            "warning: low RAM/stack headroom: "
            f"{stats['stack_headroom']} bytes (threshold {warn_headroom})",
            file=sys.stderr,
        )

    if args.validate_cmd:
        code, text = run_validation(args.validate_cmd, output_path)
        print(f"validation exit code: {code}")
        if text.strip():
            print(text.rstrip())
        return code

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
