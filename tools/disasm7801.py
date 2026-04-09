#!/usr/bin/env python3
"""uPD7801 disassembler for the Epoch Super Cassette Vision BIOS and game ROMs.
Johnny Blanchard, 2026-01-06

Usage:
    python3 disasm7801.py <binary> [--base ADDR] [--out FILE]

    --base  Load address of the binary (hex OK, default 0x0000)
    --out   Write output to FILE instead of stdout

"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Opcode tables  (derived from MAME src/devices/cpu/upd7810/upd7810_dasm.cpp)
# Each entry: (mnemonic_str, operand_fmt) or None for invalid/unimplemented.
#
# Operand format characters:
#   %a  - I/O address byte (reads 1 extra byte, displayed as VV:XX)
#   %A  - I/O address encoded in sub-opcode itself (no extra byte)
#   %b  - immediate byte (reads 1 extra byte)
#   %w  - immediate word LE (reads 2 extra bytes)
#   %d  - JRE relative (reads 1 extra byte; sign from bit 0 of prefix opcode)
#   %t  - CALT vector address (no extra bytes; from opcode bits)
#   %f  - CALF target (reads 1 extra byte)
#   %o  - JR short offset (no extra bytes; offset in opcode bits 5:0, signed 6-bit)
#   %i  - bit manipulation (reads 1 extra byte; reg/bit from following byte)
# ---------------------------------------------------------------------------

# Sub-table for prefix 0x48
D48 = [None] * 256
_d48 = {
    0x00: ("SKIT",  "F0"),   0x01: ("SKIT",  "FT"),   0x02: ("SKIT",  "F1"),
    0x03: ("SKIT",  "F2"),   0x04: ("SKIT",  "FS"),   0x0A: ("SK",    "CY"),
    0x0C: ("SK",    "Z"),    0x0E: ("PUSH",  "VA"),   0x0F: ("POP",   "VA"),
    0x10: ("SKNIT", "F0"),   0x11: ("SKNIT", "FT"),   0x12: ("SKNIT", "F1"),
    0x13: ("SKNIT", "F2"),   0x14: ("SKNIT", "FS"),   0x1A: ("SKN",   "CY"),
    0x1C: ("SKN",   "Z"),    0x1E: ("PUSH",  "BC"),   0x1F: ("POP",   "BC"),
    0x20: ("EI",    ""),     0x24: ("DI",    ""),
    0x2A: ("CLC",   ""),     0x2B: ("STC",   ""),
    0x2C: ("PER",   ""),     0x2D: ("PEX",   ""),
    0x2E: ("PUSH",  "DE"),   0x2F: ("POP",   "DE"),
    0x30: ("RLL",   "A"),    0x31: ("RLR",   "A"),
    0x32: ("RLL",   "C"),    0x33: ("RLR",   "C"),
    0x34: ("SLL",   "A"),    0x35: ("SLR",   "A"),
    0x36: ("SLL",   "C"),    0x37: ("SLR",   "C"),
    0x38: ("RLD",   ""),     0x39: ("RRD",   ""),
    0x3C: ("PER",   ""),
    0x3E: ("PUSH",  "HL"),   0x3F: ("POP",   "HL"),
    # 0x40-0x7F: MOV A,PA etc
    0x68: ("MOV",   "A,PA"), 0x69: ("MOV",   "A,PB"), 0x6A: ("MOV",   "A,PC"),
    0x6B: ("MOV",   "A,MK"), 0x6C: ("MOV",   "A,S"),
    # 0xC0-0xFF: MOV PA,A etc
    0xC0: ("MOV",   "PA,A"), 0xC1: ("MOV",   "PB,A"), 0xC2: ("MOV",   "PC,A"),
    0xC3: ("MOV",   "MK,A"), 0xC4: ("MOV",   "MB,A"), 0xC5: ("MOV",   "MC,A"),
    0xC6: ("MOV",   "TM0,A"),0xC7: ("MOV",   "TM1,A"),
    0xC8: ("MOV",   "S,A"),  0xC9: ("MOV",   "TMM,A"),
}
for k, v in _d48.items():
    D48[k] = v

# Sub-table for prefix 0x4C: IN port (port encoded in sub-opcode)
D4C = [None] * 256
for i in range(256):
    D4C[i] = ("IN", "%A")   # all 256 are valid IN instructions

# Sub-table for prefix 0x4D: OUT port
D4D = [None] * 256
# 0x00-0xBF are varying OUT/MOV entries but the majority are OUT %A
# non-OUT entries in the upper range:
for i in range(256):
    D4D[i] = ("OUT", "%A")
# Override the few MOV entries at 0xC0+
_d4d_mov = {
    0xC0: ("MOV", "PA,A"), 0xC1: ("MOV", "PB,A"), 0xC2: ("MOV", "PC,A"),
    0xC3: ("MOV", "MK,A"), 0xC4: ("MOV", "MB,A"), 0xC5: ("MOV", "MC,A"),
    0xC6: ("MOV", "TM0,A"),0xC7: ("MOV", "TM1,A"),
    0xC8: ("MOV", "S,A"),  0xC9: ("MOV", "TMM,A"),
}
for k, v in _d4d_mov.items():
    D4D[k] = v

# Sub-table for prefix 0x60: register-register ALU (dst,src = reg,A mostly)
D60 = [None] * 256
_d60_ops = [
    (0x08, "ANA"),  (0x10, "XRA"),  (0x18, "ORA"),
    (0x20, "ADDNC"),(0x28, "GTA"),  (0x30, "SUBNB"),(0x38, "LTA"),
    (0x40, "ADD"),  (0x48, "ONA"),  (0x50, "ADC"),  (0x58, "OFFA"),
    (0x60, "SUB"),  (0x68, "NEA"),  (0x70, "SBB"),  (0x78, "EQA"),
]
_regs = ["V","A","B","C","D","E","H","L"]
for base_op, mnem in _d60_ops:
    for j, reg in enumerate(_regs):
        D60[base_op + j] = (mnem, f"A,{reg}")
# Some ops only go from 0x08..0x0F (V=no, A-L yes, V entry at 0x08 = A,A repeated)
# Per MAME tables the pattern for d60 is complete for all 8 regs for each group
# Also lower range (single reg ops):
_d60_single = {
    0x00: ("INC",  "V"),  0x01: ("INC",  "A"),  0x02: ("INC",  "B"),
    0x03: ("INC",  "C"),  0x04: ("INC",  "D"),  0x05: ("INC",  "E"),
    0x06: ("INC",  "H"),  0x07: ("INC",  "L"),
    # Note: many entries are sparse in d60 for the 7801 - trust the MAME pattern
}

# The pattern seems to be: for each ALU op group of 8 (dst/src regs), starting at:
# 0x08 (ANA), 0x10 (XRA), 0x18 (ORA), 0x20 (ADDNC), 0x28 (GTA),
# 0x30 (SUBNB), 0x38 (LTA), 0x40 (ADD), 0x48 (ONA), 0x50 (ADC),
# 0x58 (OFFA), 0x60 (SUB), 0x68 (NEA), 0x70 (SBB), 0x78 (EQA)
# Each group: reg order [V,A,B,C,D,E,H,L] = offsets 0-7 within group
# The d60 sub-table covers both 0x08-0x7F (lower) and 0x88-0xFF (upper)
# Lower range 0x00-0x07 = single-reg ops (INC) - but actual MAME shows they start at 0x08
# Upper range 0x88-0xFF mirrors with V register in register operand slot

# Sub-table for prefix 0x64: ALU immediate byte
D64 = [None] * 256
_d64_ops = [
    (0x08, "ANI"),   (0x10, "XRI"),   (0x18, "ORI"),
    (0x20, "ADINC"), (0x28, "GTI"),   (0x30, "SUINB"), (0x38, "LTI"),
    (0x40, "ADI"),   (0x48, "ONI"),   (0x50, "ACI"),   (0x58, "OFFI"),
    (0x60, "SUI"),   (0x68, "NEI"),   (0x70, "SBI"),   (0x78, "EQI"),
    # Port group (0x80+)
    (0x80, "ANI"),   (0x90, "XRI"),   (0x98, "ORI"),
    (0xA0, "ADINC"), (0xA8, "GTI"),   (0xB0, "SUINB"), (0xB8, "LTI"),
    (0xC0, "ADI"),   (0xC8, "ONI"),   (0xD0, "ACI"),
    (0xE0, "SUI"),   (0xE8, "NEI"),   (0xF0, "SBI"),   (0xF8, "EQI"),
]
for base_op, mnem in _d64_ops:
    for j, reg in enumerate(_regs):
        if base_op + j < 256:
            if base_op < 0x80:
                D64[base_op + j] = (mnem, f"{reg},%b")
            else:
                # port ops: only 4 entries (PA,PB,PC,MK)
                port_names = ["PA","PB","PC","MK"]
                if j < 4:
                    D64[base_op + j] = (mnem, f"{port_names[j]},%b")
# Fix D64 port group: add missing OFFI,SUI,NEI,SBI,EQI port ops
_d64_port_extra = {
    0xD8: ("OFFI", "PA,%b"), 0xD9: ("OFFI", "PB,%b"), 0xDA: ("OFFI", "PC,%b"), 0xDB: ("OFFI", "MK,%b"),
}
for k, v in _d64_port_extra.items():
    D64[k] = v
# Sub-table for prefix 0x70: load/store word, etc.
# Extend D60 with 0x88-0xFF (register-register ALU including V register)
_d60_upper_ops = [
    (0x88, "ANA"),  (0x90, "XRA"),  (0x98, "ORA"),
    (0xA0, "ADDNC"),(0xA8, "GTA"),  (0xB0, "SUBNB"),(0xB8, "LTA"),
    (0xC0, "ADD"),  (0xC8, "ONA"),  (0xD0, "ADC"),  (0xD8, "OFFA"),
    (0xE0, "SUB"),  (0xE8, "NEA"),  (0xF0, "SBB"),  (0xF8, "EQA"),
]
for base_op, mnem in _d60_upper_ops:
    for j, reg in enumerate(_regs):
        if base_op + j < 256:
            D60[base_op + j] = (mnem, f"A,{reg}")

D70 = [None] * 256
_d70 = {
    0x0E: ("SSPD", "%w"), 0x0F: ("LSPD", "%w"),
    0x1E: ("SBCD", "%w"), 0x1F: ("LBCD", "%w"),
    0x2E: ("SDED", "%w"), 0x2F: ("LDED", "%w"),
    0x3E: ("SHLD", "%w"), 0x3F: ("LHLD", "%w"),
    0x68: ("MOV",  "V,%w"),  0x69: ("MOV",  "A,%w"),
    0x6A: ("MOV",  "B,%w"),  0x6B: ("MOV",  "C,%w"),
    0x6C: ("MOV",  "D,%w"),  0x6D: ("MOV",  "E,%w"),
    0x6E: ("MOV",  "H,%w"),  0x6F: ("MOV",  "L,%w"),
    0x78: ("MOV",  "%w,V"),  0x79: ("MOV",  "%w,A"),
    0x7A: ("MOV",  "%w,B"),  0x7B: ("MOV",  "%w,C"),
    0x7C: ("MOV",  "%w,D"),  0x7D: ("MOV",  "%w,E"),
    0x7E: ("MOV",  "%w,H"),  0x7F: ("MOV",  "%w,L"),
    # Indirect ALU ops with register pairs
    0x89: ("ANAX", "BC"),  0x8A: ("ANAX", "DE"),  0x8B: ("ANAX", "HL"),
    0x8C: ("ANAX", "DE+"), 0x8D: ("ANAX", "HL+"), 0x8E: ("ANAX", "DE-"), 0x8F: ("ANAX", "HL-"),
    0x91: ("XRAX", "BC"),  0x92: ("XRAX", "DE"),  0x93: ("XRAX", "HL"),
    0x94: ("XRAX", "DE+"), 0x95: ("XRAX", "HL+"), 0x96: ("XRAX", "DE-"), 0x97: ("XRAX", "HL-"),
    0x99: ("ORAX", "BC"),  0x9A: ("ORAX", "DE"),  0x9B: ("ORAX", "HL"),
    0x9C: ("ORAX", "DE+"), 0x9D: ("ORAX", "HL+"), 0x9E: ("ORAX", "DE-"), 0x9F: ("ORAX", "HL-"),
    0xA1: ("ADDNCX","BC"), 0xA2: ("ADDNCX","DE"), 0xA3: ("ADDNCX","HL"),
    0xA4: ("ADDNCX","DE+"),0xA5: ("ADDNCX","HL+"),0xA6: ("ADDNCX","DE-"),0xA7: ("ADDNCX","HL-"),
    0xA9: ("GTAX",  "BC"), 0xAA: ("GTAX",  "DE"), 0xAB: ("GTAX",  "HL"),
    0xAC: ("GTAX",  "DE+"),0xAD: ("GTAX",  "HL+"),0xAE: ("GTAX",  "DE-"),0xAF: ("GTAX",  "HL-"),
    0xB1: ("SUBNBX","BC"),0xB2: ("SUBNBX","DE"), 0xB3: ("SUBNBX","HL"),
    0xB4: ("SUBNBX","DE+"),0xB5: ("SUBNBX","HL+"),0xB6: ("SUBNBX","DE-"),0xB7: ("SUBNBX","HL-"),
    0xB9: ("LTAX",  "BC"), 0xBA: ("LTAX",  "DE"), 0xBB: ("LTAX",  "HL"),
    0xBC: ("LTAX",  "DE+"),0xBD: ("LTAX",  "HL+"),0xBE: ("LTAX",  "DE-"),0xBF: ("LTAX",  "HL-"),
    0xC1: ("ADDX",  "BC"), 0xC2: ("ADDX",  "DE"), 0xC3: ("ADDX",  "HL"),
    0xC4: ("ADDX",  "DE+"),0xC5: ("ADDX",  "HL+"),0xC6: ("ADDX",  "DE-"),0xC7: ("ADDX",  "HL-"),
    0xC9: ("ONAX",  "BC"), 0xCA: ("ONAX",  "DE"), 0xCB: ("ONAX",  "HL"),
    0xCC: ("ONAX",  "DE+"),0xCD: ("ONAX",  "HL+"),0xCE: ("ONAX",  "DE-"),0xCF: ("ONAX",  "HL-"),
    0xD1: ("ADCX",  "BC"), 0xD2: ("ADCX",  "DE"), 0xD3: ("ADCX",  "HL"),
    0xD4: ("ADCX",  "DE+"),0xD5: ("ADCX",  "HL+"),0xD6: ("ADCX",  "DE-"),0xD7: ("ADCX",  "HL-"),
    0xD9: ("OFFAX", "BC"), 0xDA: ("OFFAX", "DE"), 0xDB: ("OFFAX", "HL"),
    0xDC: ("OFFAX", "DE+"),0xDD: ("OFFAX", "HL+"),0xDE: ("OFFAX", "DE-"),0xDF: ("OFFAX", "HL-"),
    0xE1: ("SUBX",  "BC"), 0xE2: ("SUBX",  "DE"), 0xE3: ("SUBX",  "HL"),
    0xE4: ("SUBX",  "DE+"),0xE5: ("SUBX",  "HL+"),0xE6: ("SUBX",  "DE-"),0xE7: ("SUBX",  "HL-"),
    0xE9: ("NEAX",  "BC"), 0xEA: ("NEAX",  "DE"), 0xEB: ("NEAX",  "HL"),
    0xEC: ("NEAX",  "DE+"),0xED: ("NEAX",  "HL+"),0xEE: ("NEAX",  "DE-"),0xEF: ("NEAX",  "HL-"),
    0xF1: ("SBBX",  "BC"), 0xF2: ("SBBX",  "DE"), 0xF3: ("SBBX",  "HL"),
    0xF4: ("SBBX",  "DE+"),0xF5: ("SBBX",  "HL+"),0xF6: ("SBBX",  "DE-"),0xF7: ("SBBX",  "HL-"),
    0xF9: ("EQAX",  "BC"), 0xFA: ("EQAX",  "DE"), 0xFB: ("EQAX",  "HL"),
    0xFC: ("EQAX",  "DE+"),0xFD: ("EQAX",  "HL+"),0xFE: ("EQAX",  "DE-"),0xFF: ("EQAX",  "HL-"),
}
for k, v in _d70.items():
    D70[k] = v

# Sub-table for prefix 0x74: word ALU direct address
D74 = [None] * 256
_d74 = {
    0x88: ("ANAW",   "%a"), 0x90: ("XRAW",   "%a"), 0x98: ("ORAW",   "%a"),
    0xA0: ("ADDNCW", "%a"), 0xA8: ("GTAW",   "%a"), 0xB0: ("SUBNBW", "%a"),
    0xB8: ("LTAW",   "%a"), 0xC0: ("ADDW",   "%a"), 0xC8: ("ONAW",   "%a"),
    0xD0: ("ADCW",   "%a"), 0xD8: ("OFFAW",  "%a"), 0xE0: ("SUBW",   "%a"),
    0xE8: ("NEAW",   "%a"), 0xF0: ("SBBW",   "%a"), 0xF8: ("EQAW",   "%a"),
}
for k, v in _d74.items():
    D74[k] = v

# Sub-table dispatch: prefix → sub-table
PREFIXES = {
    0x48: D48,
    0x4C: D4C,
    0x4D: D4D,
    0x60: D60,
    0x64: D64,
    0x70: D70,
    0x74: D74,
}

# Main opcode table XX_7801
# None        = invalid/undefined
# ("mnem","") = no operand
# ("mnem",operand_fmt) = has operand with format chars
XX = [None] * 256

_main = {
    0x00: ("NOP",   ""),     0x01: ("HALT",  ""),    0x02: ("INX",   "SP"),
    0x03: ("DCX",   "SP"),   0x04: ("LXI",   "SP,%w"),0x05: ("ANIW",  "%a,%b"),
    0x07: ("ANI",   "A,%b"), 0x08: ("RET",   ""),    0x09: ("SIO",   ""),
    0x0A: ("MOV",   "A,B"),  0x0B: ("MOV",   "A,C"), 0x0C: ("MOV",   "A,D"),
    0x0D: ("MOV",   "A,E"),  0x0E: ("MOV",   "A,H"), 0x0F: ("MOV",   "A,L"),

    0x10: ("EX",    ""),     0x11: ("EXX",   ""),    0x12: ("INX",   "BC"),
    0x13: ("DCX",   "BC"),   0x14: ("LXI",   "BC,%w"),0x15: ("ORIW",  "%a,%b"),
    0x16: ("XRI",   "A,%b"), 0x17: ("ORI",   "A,%b"),0x18: ("RETS",  ""),
    0x19: ("STM",   ""),     0x1A: ("MOV",   "B,A"), 0x1B: ("MOV",   "C,A"),
    0x1C: ("MOV",   "D,A"),  0x1D: ("MOV",   "E,A"), 0x1E: ("MOV",   "H,A"),
    0x1F: ("MOV",   "L,A"),

    0x20: ("INRW",  "%a"),   0x21: ("TABLE", ""),    0x22: ("INX",   "DE"),
    0x23: ("DCX",   "DE"),   0x24: ("LXI",   "DE,%w"),0x25: ("GTIW",  "%a,%b"),
    0x26: ("ADINC", "A,%b"), 0x27: ("GTI",   "A,%b"),0x28: ("LDAW",  "%a"),
    0x29: ("LDAX",  "BC"),   0x2A: ("LDAX",  "DE"),  0x2B: ("LDAX",  "HL"),
    0x2C: ("LDAX",  "DE+"),  0x2D: ("LDAX",  "HL+"), 0x2E: ("LDAX",  "DE-"),
    0x2F: ("LDAX",  "HL-"),

    0x30: ("DCRW",  "%a"),   0x31: ("BLOCK", ""),    0x32: ("INX",   "HL"),
    0x33: ("DCX",   "HL"),   0x34: ("LXI",   "HL,%w"),0x35: ("LTIW",  "%a,%b"),
    0x36: ("SUINB", "A,%b"), 0x37: ("LTI",   "A,%b"),0x38: ("STAW",  "%a"),
    0x39: ("STAX",  "BC"),   0x3A: ("STAX",  "DE"),  0x3B: ("STAX",  "HL"),
    0x3C: ("STAX",  "DE+"),  0x3D: ("STAX",  "HL+"), 0x3E: ("STAX",  "DE-"),
    0x3F: ("STAX",  "HL-"),

    0x41: ("INR",   "A"),    0x42: ("INR",   "B"),   0x43: ("INR",   "C"),
    0x44: ("CALL",  "%w"),   0x45: ("ONIW",  "%a,%b"),0x46: ("ADI",   "A,%b"),
    0x47: ("ONI",   "A,%b"), 0x48: ("PREFIX","0x48"), 0x49: ("MVIX",  "BC,%b"),
    0x4A: ("MVIX",  "DE,%b"),0x4B: ("MVIX",  "HL,%b"),0x4C: ("PREFIX","0x4C"),
    0x4D: ("PREFIX","0x4D"), 0x4E: ("JRE",   "%d"),  0x4F: ("JRE",   "%d"),

    0x51: ("DCR",   "A"),    0x52: ("DCR",   "B"),   0x53: ("DCR",   "C"),
    0x54: ("JMP",   "%w"),   0x55: ("OFFIW", "%a,%b"),0x56: ("ACI",   "A,%b"),
    0x57: ("OFFI",  "A,%b"), 0x58: ("BIT",   "0,%a"),0x59: ("BIT",   "1,%a"),
    0x5A: ("BIT",   "2,%a"), 0x5B: ("BIT",   "3,%a"),0x5C: ("BIT",   "4,%a"),
    0x5D: ("BIT",   "5,%a"), 0x5E: ("BIT",   "6,%a"),0x5F: ("BIT",   "7,%a"),

    0x60: ("PREFIX","0x60"), 0x61: ("DAA",   ""),    0x62: ("RETI",  ""),
    0x63: ("CALB",  ""),     0x64: ("PREFIX","0x64"),0x65: ("NEIW",  "%a,%b"),
    0x66: ("SUI",   "A,%b"), 0x67: ("NEI",   "A,%b"),0x68: ("MVI",   "V,%b"),
    0x69: ("MVI",   "A,%b"), 0x6A: ("MVI",   "B,%b"),0x6B: ("MVI",   "C,%b"),
    0x6C: ("MVI",   "D,%b"), 0x6D: ("MVI",   "E,%b"),0x6E: ("MVI",   "H,%b"),
    0x6F: ("MVI",   "L,%b"),

    0x70: ("PREFIX","0x70"), 0x71: ("MVIW",  "%a,%b"),0x72: ("SOFTI", ""),
    0x73: ("JB",    ""),     0x74: ("PREFIX","0x74"),0x75: ("EQIW",  "%a,%b"),
    0x76: ("SBI",   "A,%b"), 0x77: ("EQI",   "A,%b"),
}
# 0x78-0x7F: CALF
for i in range(8):
    _main[0x78 + i] = ("CALF", "%f")
# 0x80-0xBF: CALT
for i in range(64):
    _main[0x80 + i] = ("CALT", "%t")
# 0xC0-0xFF: JR (short relative jump, offset in low 6 bits)
for i in range(64):
    _main[0xC0 + i] = ("JR", "%o")

for k, v in _main.items():
    XX[k] = v


# ---------------------------------------------------------------------------
# Disassembly engine
# ---------------------------------------------------------------------------

def _read16(data: bytes, pos: int) -> int:
    return data[pos] | (data[pos + 1] << 8)


def disassemble(data: bytes, base: int = 0) -> list[tuple[int, bytes, str, str]]:
    """Disassemble data.
    Returns list of (address, raw_bytes, mnemonic, operands).
    """
    results = []
    pos = 0
    length = len(data)

    while pos < length:
        start = pos
        addr = base + pos
        op = data[pos]
        pos += 1
        raw = bytearray([op])

        entry = XX[op]
        if entry is None:
            results.append((addr, bytes(raw), "???", f"0x{op:02X}"))
            continue

        mnem, fmt = entry

        # Handle prefix opcodes
        if mnem == "PREFIX":
            sub_table = PREFIXES.get(op)
            if sub_table is None or pos >= length:
                results.append((addr, bytes(raw), "???", f"PREFIX 0x{op:02X}"))
                continue
            sub_op = data[pos]
            pos += 1
            raw.append(sub_op)
            sub_entry = sub_table[sub_op]
            if sub_entry is None:
                results.append((addr, bytes(raw), "???", f"0x{op:02X} 0x{sub_op:02X}"))
                continue
            mnem, fmt = sub_entry
            # Decode operands for sub-entry
            operand = _decode_operand(fmt, sub_op, data, pos, addr + len(raw), base)
            extra_bytes, operand_str = operand
            for b in data[pos:pos + extra_bytes]:
                raw.append(b)
            pos += extra_bytes
            results.append((addr, bytes(raw), mnem, operand_str))
            continue

        operand = _decode_operand(fmt, op, data, pos, addr + len(raw), base)
        extra_bytes, operand_str = operand
        for b in data[pos:pos + extra_bytes]:
            raw.append(b)
        pos += extra_bytes
        results.append((addr, bytes(raw), mnem, operand_str))

    return results


def _decode_operand(fmt: str, op: int, data: bytes, pos: int, next_pc: int, base: int) -> tuple[int, str]:
    """Decode operand format string. Returns (extra_bytes_consumed, operand_string)."""
    if not fmt:
        return 0, ""

    extra = 0
    parts = []
    i = 0
    while i < len(fmt):
        ch = fmt[i]
        if ch == '%' and i + 1 < len(fmt):
            spec = fmt[i + 1]
            i += 2
            if spec == 'b':
                if pos + extra < len(data):
                    b = data[pos + extra]
                    extra += 1
                    parts.append(f"${b:02X}")
                else:
                    parts.append("?")
            elif spec == 'w':
                if pos + extra + 1 < len(data):
                    w = data[pos + extra] | (data[pos + extra + 1] << 8)
                    extra += 2
                    parts.append(f"${w:04X}")
                else:
                    parts.append("????")
            elif spec == 'a':
                # I/O byte: reads one byte, displayed as VV:XX
                if pos + extra < len(data):
                    b = data[pos + extra]
                    extra += 1
                    parts.append(f"VV:{b:02X}")
                else:
                    parts.append("VV:??")
            elif spec == 'A':
                # I/O address from sub-opcode itself (no extra byte consumed)
                parts.append(f"${op:02X}")
            elif spec == 'd':
                # JRE: next byte is disp, sign from op bit 0
                if pos + extra < len(data):
                    disp = data[pos + extra]
                    extra += 1
                    if op & 1:
                        offset = -(256 - disp)
                    else:
                        offset = disp
                    target = (next_pc + extra + offset) & 0xFFFF
                    parts.append(f"${target:04X}")
                else:
                    parts.append("?")
            elif spec == 't':
                # CALT: vector address = 0x80 + 2*(op & 0x3F)
                vec_addr = 0x80 + 2 * (op & 0x3F)
                parts.append(f"(${vec_addr:04X})")
            elif spec == 'f':
                # CALF: reads one byte, target = 0x800 + 0x100*(op&7) + byte
                if pos + extra < len(data):
                    b = data[pos + extra]
                    extra += 1
                    target = 0x800 + 0x100 * (op & 0x07) + b
                    parts.append(f"${target:04X}")
                else:
                    parts.append("????")
            elif spec == 'o':
                # JR: 6-bit signed offset in op bits [5:0]
                raw_off = op & 0x3F
                offset = raw_off - 0x20 if raw_off & 0x20 else raw_off
                target = (next_pc + offset) & 0xFFFF
                parts.append(f"${target:04X}")
            elif spec == 'i':
                # Bit manipulation: next byte encodes reg/bit
                if pos + extra < len(data):
                    b = data[pos + extra]
                    extra += 1
                    reg_idx = b & 0x1F
                    bit_num = b >> 5
                    reg_names = ["V","A","B","C","D","E","H","L","PA","PB","PC","MK","MB","MC","TM0","TM1","S","TMM"]
                    rname = reg_names[reg_idx] if reg_idx < len(reg_names) else f"R{reg_idx}"
                    parts.append(f"{rname},{bit_num}")
                else:
                    parts.append("?,?")
            else:
                parts.append(f"%{spec}")
        else:
            # Literal character — collect until next % or comma
            parts.append(ch)
            i += 1

    return extra, "".join(parts)


def format_disassembly(results: list, show_bytes: bool = True) -> str:
    """Format disassembly results as a string."""
    lines = []
    for addr, raw, mnem, operands in results:
        hex_bytes = " ".join(f"{b:02X}" for b in raw)
        if show_bytes:
            line = f"${addr:04X}:  {hex_bytes:<14}  {mnem:<10} {operands}"
        else:
            line = f"${addr:04X}:  {mnem:<10} {operands}"
        lines.append(line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# BIOS analysis: find CALT vectors and known patterns
# ---------------------------------------------------------------------------

SCV_KNOWN_ADDRS: dict[int, str] = {
    # Hardware registers
    0x3000: "VRAM_BASE",
    0x3040: "VRAM_TEXT",
    0x3200: "HW_SPRITE_TABLE",
    0xFF80: "SW_SPRITE_SHADOW",
    0xFFF0: "STACK_INIT",
    # SCV API calls known from scv_api.h / CrabSCV analysis
}

def analyze_bios(data: bytes, base: int, results: list) -> str:
    """Print CALT vector table and identify BIOS subroutines."""
    lines = ["=" * 70, "BIOS ANALYSIS", "=" * 70]

    # CALT vector table is at 0x0080 (for 7801: ea = 0x80 + 2*(op&0x3F))
    # Vectors for CALT 0x80..0xBF → vec addresses 0x0080..0x00FE
    lines.append("\n--- CALT Vector Table (0x0080-0x00FE) ---")
    for n in range(64):
        vec_addr = 0x80 + 2 * n
        calt_op = 0x80 + n
        if vec_addr + 1 - base < len(data):
            target = _read16(data, vec_addr - base)
            if target != 0xFFFF and target != 0x0000:
                label = SCV_KNOWN_ADDRS.get(target, "")
                lines.append(f"  CALT ${calt_op:02X}  vec@${vec_addr:04X}  -> ${target:04X}  {label}")

    # Scan for RET / RETS instructions to find subroutine boundaries
    lines.append("\n--- Identified Subroutines (by CALL/CALT targets + RET) ---")
    call_targets: set[int] = set()
    for addr, raw, mnem, operands in results:
        if mnem in ("CALL", "CALB") and operands.startswith("$"):
            try:
                t = int(operands[1:], 16)
                call_targets.add(t)
            except ValueError:
                pass
        if mnem == "CALT" and operands.startswith("($"):
            # operands = ($XXXX) = vector address; we need the value there
            try:
                vec = int(operands[2:6], 16)
                if vec + 1 - base < len(data):
                    t = _read16(data, vec - base)
                    if t != 0xFFFF:
                        call_targets.add(t)
            except (ValueError, IndexError):
                pass

    addr_to_result = {r[0]: r for r in results}
    for target in sorted(call_targets):
        if target in addr_to_result:
            _, _, mnem, operands = addr_to_result[target]
            label = SCV_KNOWN_ADDRS.get(target, "")
            lines.append(f"  ${target:04X}:  {mnem} {operands}  {label}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="uPD7801 disassembler for Epoch SCV\n2026 Johnny Blanchard (Tonsomo/RE:Enthused/Roguegunners)")
    parser.add_argument("binary", help="Binary file to disassemble")
    parser.add_argument("--base", default="0x0000",
                        help="Load address (hex or decimal, default 0x0000)")
    parser.add_argument("--out", help="Output file (default: stdout)")
    parser.add_argument("--analyze", action="store_true",
                        help="Print BIOS analysis (CALT vectors, subroutines)")
    args = parser.parse_args()

    base = int(args.base, 0)
    data = Path(args.binary).read_bytes()

    results = disassemble(data, base)
    output = format_disassembly(results) + "\n"

    if args.analyze:
        output += "\n" + analyze_bios(data, base, results) + "\n"

    if args.out:
        Path(args.out).write_text(output)
        print(f"Wrote {len(results)} instructions to {args.out}")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
