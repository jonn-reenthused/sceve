#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

PYTHON_BIN=${PYTHON_BIN:-python3}
SOURCE_FILE=${1:-$ROOT_DIR/src/gridrunner.c}
BUILD_DIR=${BUILD_DIR:-$ROOT_DIR/build}
CONVERTER=$ROOT_DIR/../tools/c_to_l7801.py
ASSEMBLER=$ROOT_DIR/../tools/asm7801.py

if [ ! -f "$SOURCE_FILE" ]; then
    echo "Source file not found: $SOURCE_FILE" >&2
    exit 1
fi

mkdir -p "$BUILD_DIR"

BASE_NAME=$(basename "$SOURCE_FILE" .c)
ASM_FILE=$BUILD_DIR/$BASE_NAME.l7801

"$PYTHON_BIN" "$CONVERTER" "$SOURCE_FILE" -o "$ASM_FILE"
"$PYTHON_BIN" "$ASSEMBLER" "$ASM_FILE"

BIN_FILE=$BUILD_DIR/$BASE_NAME.bin

if [ ! -f "$BIN_FILE" ]; then
    echo "Expected output ROM not found: $BIN_FILE" >&2
    exit 1
fi

echo "Built $BIN_FILE"