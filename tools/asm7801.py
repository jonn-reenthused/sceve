#!/usr/bin/env python3
"""Limited 7801 assembler for SCeVe
Johnny Blanchard 20240412

This is the first building block for a repo-owned assembler. It does not
encode machine code yet; instead it parses the narrow source format emitted by
tools/c_to_l7801.py and reports the exact pseudo-ops, labels, locals, data
directives, and instruction mnemonics in use.

Why start here:
  - The current dependency on the external l7801 assembler is a toolchain risk.
  - Our emitted assembly is a small, regular dialect, not arbitrary hand-written
    source.
  - A reliable parser/IR gives us a controlled path toward a subset assembler
    without needing to support the whole uPD7801 ecosystem on day one.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from disasm7801 import PREFIXES, XX


COMMENT_PREFIX = "--"


@dataclass
class RequireStatement:
    module: str
    line_number: int


@dataclass
class SectionStatement:
    raw: str
    line_number: int


@dataclass
class LocationStatement:
    start: int
    end: int
    line_number: int


@dataclass
class LocalStatement:
    name: str
    value: int
    line_number: int


@dataclass
class LabelStatement:
    name: str
    line_number: int


@dataclass
class DataStatement:
    directive: str
    values: List[str]
    line_number: int


@dataclass
class InstructionStatement:
    mnemonic: str
    operands: str
    line_number: int


@dataclass
class WriteBinStatement:
    target_expr: str
    line_number: int


@dataclass
class ParsedProgram:
    requires: List[RequireStatement]
    sections: List[SectionStatement]
    locations: List[LocationStatement]
    locals: List[LocalStatement]
    labels: List[LabelStatement]
    data: List[DataStatement]
    instructions: List[InstructionStatement]
    writebins: List[WriteBinStatement]


@dataclass
class AssembledImage:
    origin: int
    image: bytes
    labels: Dict[str, int]
    locals: Dict[str, int]


REGISTER_INDEX = {
    "v": 0,
    "a": 1,
    "b": 2,
    "c": 3,
    "d": 4,
    "e": 5,
    "h": 6,
    "l": 7,
}


REG_ALU_BASE_LEFT = {
    "ana": 0x08,
    "xra": 0x10,
    "ora": 0x18,
    "addnc": 0x20,
    "gta": 0x28,
    "subnb": 0x30,
    "lta": 0x38,
    "add": 0x40,
    "adc": 0x50,
    "sub": 0x60,
    "nea": 0x68,
    "sbb": 0x70,
    "eqa": 0x78,
}


REG_ALU_BASE_A = {
    "ana": 0x88,
    "xra": 0x90,
    "ora": 0x98,
    "addnc": 0xA0,
    "gta": 0xA8,
    "subnb": 0xB0,
    "lta": 0xB8,
    "add": 0xC0,
    "ona": 0xC8,
    "adc": 0xD0,
    "offa": 0xD8,
    "sub": 0xE0,
    "nea": 0xE8,
    "sbb": 0xF0,
    "eqa": 0xF8,
}


REG_IMM_BASE = {
    "ani": 0x08,
    "gti": 0x28,
    "lti": 0x38,
    "adi": 0x40,
    "aci": 0x50,
    "nei": 0x68,
    "eqi": 0x78,
}


PORT_IMM_BASE = {
    "ani": 0x80,
    "gti": 0xA8,
    "lti": 0xB8,
    "adi": 0xC0,
    "aci": 0xD0,
    "nei": 0xE8,
    "eqi": 0xF8,
}


PORT_INDEX = {
    "pa": 0,
    "pb": 1,
    "pc": 2,
    "mk": 3,
}


PORT_MOV_SUBOPCODE = {
    "pa": 0xC0,
    "pb": 0xC1,
    "pc": 0xC2,
    "mk": 0xC3,
}


DIRECT_A_IMM_OPCODE = {
    "adi": 0x46,
    "ani": 0x07,
    "eqi": 0x77,
    "gti": 0x27,
    "nei": 0x67,
    "lti": 0x37,
    "aci": 0x56,
}


LOCAL_RE = re.compile(r"^local\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(0x[0-9A-Fa-f]+|\d+)\s*$")
LABEL_RE = re.compile(r"^@([A-Za-z0-9_.$]+)\s*$")
LOCATION_RE = re.compile(r"^location\((0x[0-9A-Fa-f]+|\d+),\s*(0x[0-9A-Fa-f]+|\d+)\)\s*$")
REQUIRE_RE = re.compile(r"^require\s+'([^']+)'\s*$")
WRITEBIN_RE = re.compile(r"^writebin\((.+)\)\s*$")
DATA_RE = re.compile(r"^dc\.([A-Za-z]+)\s+(.+)$")
INSTRUCTION_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)\b(?:\s+(.*))?$")


def _parse_int(token: str) -> int:
    return int(token, 0)


def _split_operands(operands: str) -> List[str]:
    if not operands:
        return []
    return [part.strip() for part in operands.split(",")]


def _parse_data_value(token: str) -> int:
    token = token.strip()
    if token.startswith("'") and token.endswith("'") and len(token) >= 3:
        body = token[1:-1]
        if len(body) != 1:
            raise ValueError(f"Only single-character literals are supported in dc.b: {token}")
        return ord(body)
    return int(token, 0) & 0xFF


def _find_exact_opcode(mnemonic: str, operand_pattern: str) -> Optional[Tuple[int, ...]]:
    matches: List[Tuple[int, ...]] = []
    for opcode, entry in enumerate(XX):
        if entry == (mnemonic.upper(), operand_pattern):
            matches.append((opcode,))
    for prefix, table in PREFIXES.items():
        for subopcode, entry in enumerate(table):
            if entry == (mnemonic.upper(), operand_pattern):
                matches.append((prefix, subopcode))
    if not matches:
        return None
    matches.sort(key=lambda item: (len(item), item))
    return matches[0]


def _section_origin(program: ParsedProgram) -> int:
    for section in program.sections:
        match = re.search(r"org\s*=\s*(0x[0-9A-Fa-f]+|\d+)", section.raw)
        if match:
            return int(match.group(1), 0)
    if program.locations:
        return program.locations[0].start
    return 0x8000


def _location_range(program: ParsedProgram) -> Optional[Tuple[int, int]]:
    if program.locations:
        return (program.locations[0].start, program.locations[0].end)
    return None


def _encode_reg_alu(mnemonic: str, left: str, right: str) -> List[int]:
    if right == "a" and left in REGISTER_INDEX and mnemonic in REG_ALU_BASE_LEFT:
        return [0x60, REG_ALU_BASE_LEFT[mnemonic] + REGISTER_INDEX[left]]
    if left == "a" and right in REGISTER_INDEX and mnemonic in REG_ALU_BASE_A:
        return [0x60, REG_ALU_BASE_A[mnemonic] + REGISTER_INDEX[right]]
    raise ValueError(f"Unsupported register ALU form: {mnemonic} {left},{right}")


def _encode_reg_imm(mnemonic: str, reg: str, imm: int) -> List[int]:
    if reg == "a":
        return [DIRECT_A_IMM_OPCODE[mnemonic], imm]
    if reg in REGISTER_INDEX:
        return [0x64, REG_IMM_BASE[mnemonic] + REGISTER_INDEX[reg], imm]
    if reg in PORT_INDEX:
        return [0x64, PORT_IMM_BASE[mnemonic] + PORT_INDEX[reg], imm]
    raise ValueError(f"Unsupported register immediate form: {mnemonic} {reg},{imm:#x}")


def _instruction_size(instruction: InstructionStatement) -> int:
    mnemonic = instruction.mnemonic.lower()
    operands = _split_operands(instruction.operands)

    if mnemonic in {"ret", "nop", "stm"}:
        return 1
    if mnemonic in {"di", "ei"}:
        return 2
    if mnemonic in {"call", "jmp", "lxi"}:
        return 3
    if mnemonic == "calt":
        return 1
    if mnemonic == "jr":
        return 1
    if mnemonic == "jre":
        return 2
    if mnemonic == "stax":
        return 1
    if mnemonic == "staxi":
        return 1
    if mnemonic == "mvix":
        return 2
    if mnemonic == "ldax":
        return 1
    if mnemonic == "ldaxi":
        return 1
    if mnemonic == "skit" or mnemonic == "sknit":
        return 2
    if mnemonic in {"skc", "skz", "sknc", "sknz"}:
        return 2
    if mnemonic == "mov":
        if len(operands) != 2:
            raise ValueError(f"Unexpected mov form on line {instruction.line_number}")
        left, right = operands
        if left.startswith("(") or right.startswith("("):
            return 4
        exact = _find_exact_opcode("MOV", f"{left.upper()},{right.upper()}")
        if exact is None:
            raise ValueError(f"Unsupported MOV form on line {instruction.line_number}: {instruction.operands}")
        return len(exact)
    if mnemonic == "mvi":
        if len(operands) != 2:
            raise ValueError(f"Unexpected mvi form on line {instruction.line_number}")
        reg = operands[0].lower()
        return 3 if reg == "h" and operands[1] == "0" and False else 2
    if mnemonic in {"adi", "ani", "eqi", "gti", "nei", "lti", "aci"}:
        return 2 if operands[0].lower() == "a" else 3
    if mnemonic == "inc":
        return 2
    if mnemonic in {"dcr", "add", "sub", "ana", "xra", "ora", "eqa", "inx"}:
        if mnemonic == "dcr":
            return 1
        if mnemonic == "inx":
            return 1
        return 2
    raise ValueError(f"Unsupported instruction for size calculation on line {instruction.line_number}: {instruction.mnemonic} {instruction.operands}")


def _resolve_value(token: str, symbols: Dict[str, int]) -> int:
    token = token.strip()
    if token in symbols:
        return symbols[token]
    return int(token, 0)


def _encode_relative_short(target: int, instruction_address: int) -> int:
    delta = target - 1 - instruction_address
    if delta < -32 or delta > 32:
        raise ValueError(f"JR target out of range: delta={delta}")
    return 0xC0 + delta if delta >= 0 else (delta & 0xFF)


def _encode_relative_extended(target: int, instruction_address: int) -> Tuple[int, int]:
    delta = target - 2 - instruction_address
    if delta < -128 or delta > 127:
        raise ValueError(f"JRE target out of range: delta={delta}")
    opcode = 0x4E if delta >= 0 else 0x4F
    return opcode, delta & 0xFF


def _encode_instruction(
    instruction: InstructionStatement,
    instruction_address: int,
    symbols: Dict[str, int],
) -> List[int]:
    mnemonic = instruction.mnemonic.lower()
    operands = _split_operands(instruction.operands)

    if mnemonic == "ret":
        return [0x08]
    if mnemonic == "nop":
        return [0x00]
    if mnemonic == "stm":
        return [0x19]
    if mnemonic == "skc":
        return [0x48, 0x0A]
    if mnemonic == "skz":
        return [0x48, 0x0C]
    if mnemonic == "sknc":
        return [0x48, 0x1A]
    if mnemonic == "sknz":
        return [0x48, 0x1C]
    if mnemonic == "di":
        return [0x48, 0x24]
    if mnemonic == "ei":
        return [0x48, 0x20]
    if mnemonic == "call":
        value = _resolve_value(operands[0], symbols)
        return [0x44, value & 0xFF, (value >> 8) & 0xFF]
    if mnemonic == "jmp":
        value = _resolve_value(operands[0], symbols)
        return [0x54, value & 0xFF, (value >> 8) & 0xFF]
    if mnemonic == "lxi":
        reg = operands[0].lower()
        value = _resolve_value(operands[1], symbols)
        opcode = {
            "sp": 0x04,
            "bc": 0x14,
            "de": 0x24,
            "hl": 0x34,
        }[reg]
        return [opcode, value & 0xFF, (value >> 8) & 0xFF]
    if mnemonic == "calt":
        value = _resolve_value(operands[0], symbols)
        if value % 2 != 0 or value < 0x80 or value > 0xFE:
            raise ValueError(f"Invalid CALT vector {value:#x}")
        return [((value >> 1) + 0x40) & 0xFF]
    if mnemonic == "jr":
        target = _resolve_value(operands[0], symbols)
        return [_encode_relative_short(target, instruction_address)]
    if mnemonic == "jre":
        target = _resolve_value(operands[0], symbols)
        opcode, disp = _encode_relative_extended(target, instruction_address)
        return [opcode, disp]
    if mnemonic == "skit":
        interrupt = operands[0].lower()
        sub = {"f0": 0x00, "ft": 0x01, "f1": 0x02, "f2": 0x03, "fs": 0x04}[interrupt]
        return [0x48, sub]
    if mnemonic == "sknit":
        interrupt = operands[0].lower()
        sub = {"f0": 0x10, "ft": 0x11, "f1": 0x12, "f2": 0x13, "fs": 0x14}[interrupt]
        return [0x48, sub]
    if mnemonic == "stax":
        mode = operands[0].strip().lower()
        opcode = {
            "(bc)": 0x39,
            "(de)": 0x3A,
            "(hl)": 0x3B,
        }[mode]
        return [opcode]
    if mnemonic == "staxi":
        mode = operands[0].strip().lower()
        opcode = {
            "(de)": 0x3C,
            "(hl)": 0x3D,
        }[mode]
        return [opcode]
    if mnemonic == "mvix":
        mode = operands[0].strip().lower()
        imm = _resolve_value(operands[1], symbols) & 0xFF
        opcode = {
            "(bc)": 0x49,
            "(de)": 0x4A,
            "(hl)": 0x4B,
        }[mode]
        return [opcode, imm]
    if mnemonic == "ldax":
        mode = operands[0].strip().lower()
        opcode = {
            "(bc)": 0x29,
            "(de)": 0x2A,
            "(hl)": 0x2B,
        }[mode]
        return [opcode]
    if mnemonic == "ldaxi":
        mode = operands[0].strip().lower()
        opcode = {
            "(de)": 0x2C,
            "(hl)": 0x2D,
        }[mode]
        return [opcode]
    if mnemonic == "inc":
        reg = operands[0].lower()
        reg_subopcode = {
            "v": 0x00,
            "a": 0x01,
            "b": 0x02,
            "c": 0x03,
            "d": 0x04,
            "e": 0x05,
            "h": 0x06,
            "l": 0x07,
        }[reg]
        return [0x60, reg_subopcode]
    if mnemonic == "mov":
        left, right = operands[0], operands[1]
        if left.lower() == "a" and right.lower() in PORT_MOV_SUBOPCODE:
            return [0x4C, PORT_MOV_SUBOPCODE[right.lower()]]
        if left.lower() in PORT_MOV_SUBOPCODE and right.lower() == "a":
            return [0x4D, PORT_MOV_SUBOPCODE[left.lower()]]
        if left.startswith("("):
            reg = right.lower()
            address = _resolve_value(left[1:-1], symbols)
            subopcode = {
                "v": 0x78,
                "a": 0x79,
                "b": 0x7A,
                "c": 0x7B,
                "d": 0x7C,
                "e": 0x7D,
                "h": 0x7E,
                "l": 0x7F,
            }[reg]
            return [0x70, subopcode, address & 0xFF, (address >> 8) & 0xFF]
        if right.startswith("("):
            reg = left.lower()
            address = _resolve_value(right[1:-1], symbols)
            subopcode = {
                "v": 0x68,
                "a": 0x69,
                "b": 0x6A,
                "c": 0x6B,
                "d": 0x6C,
                "e": 0x6D,
                "h": 0x6E,
                "l": 0x6F,
            }[reg]
            return [0x70, subopcode, address & 0xFF, (address >> 8) & 0xFF]
        exact = _find_exact_opcode("MOV", f"{left.upper()},{right.upper()}")
        if exact is None:
            raise ValueError(f"Unsupported MOV form on line {instruction.line_number}: {instruction.operands}")
        return list(exact)
    if mnemonic == "mvi":
        reg = operands[0].lower()
        imm = _resolve_value(operands[1], symbols) & 0xFF
        direct = {
            "v": 0x68,
            "a": 0x69,
            "b": 0x6A,
            "c": 0x6B,
            "d": 0x6C,
            "e": 0x6D,
            "h": 0x6E,
            "l": 0x6F,
        }
        return [direct[reg], imm]
    if mnemonic in {"adi", "ani", "eqi", "gti", "nei", "lti", "aci"}:
        reg = operands[0].lower()
        imm = _resolve_value(operands[1], symbols) & 0xFF
        return _encode_reg_imm(mnemonic, reg, imm)
    if mnemonic == "dcr":
        reg = operands[0].lower()
        return [{"a": 0x51, "b": 0x52, "c": 0x53}[reg]]
    if mnemonic == "inx":
        reg = operands[0].lower()
        return [{"sp": 0x02, "bc": 0x12, "de": 0x22, "hl": 0x32}[reg]]
    if mnemonic == "add":
        left = operands[0].lower()
        right = operands[1].lower()
        return _encode_reg_alu("add", left, right)
    if mnemonic == "sub":
        left = operands[0].lower()
        right = operands[1].lower()
        return _encode_reg_alu("sub", left, right)
    if mnemonic == "ana":
        left = operands[0].lower()
        right = operands[1].lower()
        return _encode_reg_alu("ana", left, right)
    if mnemonic == "eqa":
        left = operands[0].lower()
        right = operands[1].lower()
        return _encode_reg_alu("eqa", left, right)
    if mnemonic == "xra":
        left = operands[0].lower()
        right = operands[1].lower()
        return _encode_reg_alu("xra", left, right)
    if mnemonic == "ora":
        left = operands[0].lower()
        right = operands[1].lower()
        return _encode_reg_alu("ora", left, right)

    raise ValueError(f"Unsupported instruction on line {instruction.line_number}: {instruction.mnemonic} {instruction.operands}")


def assemble_program(program: ParsedProgram) -> AssembledImage:
    origin = _section_origin(program)
    location_range = _location_range(program)
    labels: Dict[str, int] = {}
    locals_map: Dict[str, int] = {entry.name: entry.value for entry in program.locals}
    offset = 0

    for statement in _iter_statements(program):
        if isinstance(statement, LabelStatement):
            labels[statement.name] = origin + offset
            continue
        if isinstance(statement, DataStatement):
            if statement.directive != "b":
                raise ValueError(f"Unsupported data directive dc.{statement.directive} on line {statement.line_number}")
            offset += len(statement.values)
            continue
        if isinstance(statement, InstructionStatement):
            offset += _instruction_size(statement)

    symbols = {**locals_map, **labels}
    output: List[int] = []
    offset = 0

    for statement in _iter_statements(program):
        if isinstance(statement, DataStatement):
            output.extend(_parse_data_value(value) for value in statement.values)
            offset += len(statement.values)
            continue
        if isinstance(statement, InstructionStatement):
            encoded = _encode_instruction(statement, origin + offset, symbols)
            output.extend(encoded)
            offset += len(encoded)

    image = bytes(output)
    if location_range is not None:
        start, end = location_range
        full_size = end - start + 1
        if full_size < 0:
            raise ValueError("Invalid location range")
        full_image = bytearray([0x00] * full_size)
        start_offset = origin - start
        full_image[start_offset:start_offset + len(image)] = image
        image = bytes(full_image)

    return AssembledImage(origin=origin, image=image, labels=labels, locals=locals_map)


def _iter_statements(program: ParsedProgram):
    by_line = []
    for collection in [
        program.requires,
        program.sections,
        program.locations,
        program.locals,
        program.labels,
        program.data,
        program.instructions,
        program.writebins,
    ]:
        by_line.extend(collection)
    return sorted(by_line, key=lambda item: item.line_number)


def parse_program(text: str) -> ParsedProgram:
    program = ParsedProgram([], [], [], [], [], [], [], [])

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith(COMMENT_PREFIX):
            continue

        require_match = REQUIRE_RE.match(line)
        if require_match:
            program.requires.append(RequireStatement(require_match.group(1), line_number))
            continue

        if line.startswith("section{"):
            program.sections.append(SectionStatement(line, line_number))
            continue

        location_match = LOCATION_RE.match(line)
        if location_match:
            program.locations.append(
                LocationStatement(
                    _parse_int(location_match.group(1)),
                    _parse_int(location_match.group(2)),
                    line_number,
                )
            )
            continue

        local_match = LOCAL_RE.match(line)
        if local_match:
            program.locals.append(
                LocalStatement(local_match.group(1), _parse_int(local_match.group(2)), line_number)
            )
            continue

        label_match = LABEL_RE.match(line)
        if label_match:
            program.labels.append(LabelStatement(label_match.group(1), line_number))
            continue

        data_match = DATA_RE.match(line)
        if data_match:
            values = [value.strip() for value in data_match.group(2).split(",") if value.strip()]
            program.data.append(DataStatement(data_match.group(1).lower(), values, line_number))
            continue

        writebin_match = WRITEBIN_RE.match(line)
        if writebin_match:
            program.writebins.append(WriteBinStatement(writebin_match.group(1).strip(), line_number))
            continue

        instruction_match = INSTRUCTION_RE.match(line)
        if instruction_match:
            program.instructions.append(
                InstructionStatement(
                    mnemonic=instruction_match.group(1).lower(),
                    operands=(instruction_match.group(2) or "").strip(),
                    line_number=line_number,
                )
            )
            continue

        raise ValueError(f"Unrecognized line {line_number}: {raw_line}")

    return program


def build_summary(program: ParsedProgram) -> dict:
    mnemonic_counts: dict[str, int] = {}
    directive_counts: dict[str, int] = {}
    data_value_count = 0

    for instruction in program.instructions:
        mnemonic_counts[instruction.mnemonic] = mnemonic_counts.get(instruction.mnemonic, 0) + 1

    for entry in program.data:
        key = f"dc.{entry.directive}"
        directive_counts[key] = directive_counts.get(key, 0) + 1
        data_value_count += len(entry.values)

    directive_counts["require"] = len(program.requires)
    directive_counts["section"] = len(program.sections)
    directive_counts["location"] = len(program.locations)
    directive_counts["local"] = len(program.locals)
    directive_counts["writebin"] = len(program.writebins)

    return {
        "require_count": len(program.requires),
        "section_count": len(program.sections),
        "location_count": len(program.locations),
        "local_count": len(program.locals),
        "label_count": len(program.labels),
        "data_statement_count": len(program.data),
        "data_value_count": data_value_count,
        "instruction_count": len(program.instructions),
        "writebin_count": len(program.writebins),
        "mnemonic_counts": dict(sorted(mnemonic_counts.items(), key=lambda item: (-item[1], item[0]))),
        "directive_counts": directive_counts,
    }


def _make_jsonable(program: ParsedProgram) -> dict:
    return {
        "requires": [asdict(item) for item in program.requires],
        "sections": [asdict(item) for item in program.sections],
        "locations": [asdict(item) for item in program.locations],
        "locals": [asdict(item) for item in program.locals],
        "labels": [asdict(item) for item in program.labels],
        "data": [asdict(item) for item in program.data],
        "instructions": [asdict(item) for item in program.instructions],
        "writebins": [asdict(item) for item in program.writebins],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse and analyze the repo's .l7801 dialect")
    parser.add_argument("source", help="Path to a .l7801 source file")
    parser.add_argument("--json", dest="json_path", help="Optional path to write parsed IR JSON")
    parser.add_argument("--summary-only", action="store_true", help="Print summary only (skip default assembly)")
    parser.add_argument("--assemble-bin", dest="assemble_bin", help="Assemble the parsed source and write a binary (default: <source>.bin)")
    parser.add_argument("--compare-bin", dest="compare_bin", help="Compare assembled output against an existing binary")
    args = parser.parse_args()

    source_path = Path(args.source)
    text = source_path.read_text(encoding="utf-8")
    program = parse_program(text)
    summary = build_summary(program)

    should_assemble = bool(args.assemble_bin) or bool(args.compare_bin) or not args.summary_only
    if should_assemble:
        assembled = assemble_program(program)
        output_path = Path(args.assemble_bin) if args.assemble_bin else source_path.with_suffix(".bin")
        output_path.write_bytes(assembled.image)
        print(f"assembled: {output_path}")
        print(f"origin: 0x{assembled.origin:04X}")
        print(f"bytes: {len(assembled.image)}")
        if args.compare_bin:
            compare_path = Path(args.compare_bin)
            compare_bytes = compare_path.read_bytes()
            if compare_bytes == assembled.image:
                print(f"compare: match {compare_path}")
            else:
                print(f"compare: mismatch {compare_path}")
                print(f"assembled_size={len(assembled.image)} compare_size={len(compare_bytes)}")
                mismatch_at = next((i for i, (a, b) in enumerate(zip(assembled.image, compare_bytes)) if a != b), None)
                if mismatch_at is None and len(assembled.image) != len(compare_bytes):
                    mismatch_at = min(len(assembled.image), len(compare_bytes))
                if mismatch_at is not None:
                    assembled_byte = assembled.image[mismatch_at] if mismatch_at < len(assembled.image) else None
                    compare_byte = compare_bytes[mismatch_at] if mismatch_at < len(compare_bytes) else None
                    print(f"first_mismatch=0x{mismatch_at:04X} assembled={assembled_byte} compare={compare_byte}")
                return 1
        return 0

    print(f"source: {source_path}")
    print(f"instructions: {summary['instruction_count']}")
    print(f"labels: {summary['label_count']}")
    print(f"locals: {summary['local_count']}")
    print(f"data statements: {summary['data_statement_count']}")
    print(f"data values: {summary['data_value_count']}")
    print("top mnemonics:")
    for mnemonic, count in list(summary["mnemonic_counts"].items())[:20]:
        print(f"  {mnemonic:8} {count}")

    if not args.summary_only:
        print("directives:")
        for directive, count in sorted(summary["directive_counts"].items()):
            print(f"  {directive:8} {count}")

    if args.json_path:
        output = {
            "summary": summary,
            "program": _make_jsonable(program),
        }
        Path(args.json_path).write_text(json.dumps(output, indent=2), encoding="utf-8")
        print(f"wrote json: {args.json_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())