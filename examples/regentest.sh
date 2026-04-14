#!/usr/bin/env sh
set -eu

PYTHON_BIN=${PYTHON_BIN:-python3}
CONVERTER=../tools/c_to_l7801.py
ASSEMBLER=../tools/asm7801.py

rm -f ./*.bin ./*.l7801

build_demo() {
	input="$1"
	output="${input%.c}.l7801"
	"$PYTHON_BIN" "$CONVERTER" "$input" -o "$output"
	"$PYTHON_BIN" "$ASSEMBLER" "$output"
}

build_demo ./game_demo.c
build_demo ./demo_input_sound.c
build_demo ./demo_music_sequencer.c
build_demo ./demo_sound_effects_keypad.c
build_demo ./demo_bg_array_loader.c
build_demo ./demo_bg_scroll.c
build_demo ./demo_bg_sprite_combo.c
build_demo ./demo_bg_png_tiles.c
build_demo ./demo_bios_wrappers.c
build_demo ./demo_crabscv_migration.c
build_demo ./demo_crab_bg_autogen.c
build_demo ./scv_enum_struct_test.c
build_demo ./scv_nested_struct_test.c
build_demo ./scv_const_array_test.c
build_demo ./scv_const_array_index_test.c
build_demo ./input_probe.c
build_demo ./input_probe_full.c

ls -1 ./*.bin
