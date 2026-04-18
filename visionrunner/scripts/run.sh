#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

SOURCE_FILE=${1:-$ROOT_DIR/src/gridrunner.c}
BUILD_DIR=${BUILD_DIR:-$ROOT_DIR/build}
ROM_NAME=$(basename "$SOURCE_FILE" .c)
ROM_PATH=$BUILD_DIR/$ROM_NAME.bin

"$SCRIPT_DIR/build.sh" "$SOURCE_FILE"

if command -v mame >/dev/null 2>&1; then
    exec mame scv -cart "$ROM_PATH"
fi

if command -v mess >/dev/null 2>&1; then
    exec mess scv -cart "$ROM_PATH"
fi

if [ -n "${SCV_EMULATOR_BIN:-}" ]; then
    exec "$SCV_EMULATOR_BIN" ${SCV_EMULATOR_ARGS:-} "$ROM_PATH"
fi

echo "Built ROM at $ROM_PATH" >&2
echo "No SCV emulator detected. Install MAME or set SCV_EMULATOR_BIN." >&2
exit 1