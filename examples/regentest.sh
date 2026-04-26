#!/usr/bin/env sh
set -eu

PYTHON_BIN=${PYTHON_BIN:-python3}
CONVERTER=../tools/c_to_l7801.py
ASSEMBLER=../tools/asm7801.py

rm -f ./*.bin ./*.l7801 ./*.cart.json
rm -rf ./demo_banked_regentest

build_demo() {
	input="$1"
	output="${input%.c}.l7801"
	"$PYTHON_BIN" "$CONVERTER" "$input" -o "$output"
	"$PYTHON_BIN" "$ASSEMBLER" "$output"
}

build_banked_demo() {
	input="$1"
	output="${input%.c}.l7801"
	package_dir="${input%.c}"
	"$PYTHON_BIN" "$CONVERTER" "$input" -o "$output" --emit-cart-package
	"$PYTHON_BIN" "$ASSEMBLER" "$output"
	[ -f "${output%.l7801}.cart.json" ]
	[ -f "$package_dir/manifest.json" ]
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
build_banked_demo ./demo_banked_regentest.c

build_banked_demo ./demo_cart_ram.c
build_banked_demo ./demo_cart_ram_battery.c
build_banked_demo ./demo_cart_ram_pragma.c
build_banked_demo ./demo_call_arg_regression.c

ls -1 ./*.bin
