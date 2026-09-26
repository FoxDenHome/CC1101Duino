"""Helpers shared by the client module ports, mirroring the Perl originals."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Reading:
    """What a FHEM client module would store for one received message."""

    # FHEM's device code (the DEF of the autocreated device), unique per sensor
    device: str
    # Human readable sensor type
    model: str
    readings: dict[str, Any] = field(default_factory=dict)


def hex_to_bits(hex_str: str) -> str:
    """unpack("B*", pack("H*", $hex))."""
    if not hex_str:
        return ""
    return "".join(f"{int(char, 16):04b}" for char in hex_str)


def bin_num(bits: str, first: int, last: int | None = None) -> int:
    """SD_WS_binaryToNumber: bits first..last (inclusive) as a number."""
    if last is None:
        last = first
    part = bits[first : last + 1] if first < len(bits) else ""
    return int(part, 2) if part else 0


def bin2dec(bits: str) -> int:
    """SD_WS_bin2dec: the last 32 bits as a number."""
    part = bits[-32:]
    return int(part, 2) if part else 0


def perl_round(value: float, digits: int) -> str:
    """FHEM::Core::Utils::Math::round is sprintf("%.Nf"), so it returns a string."""
    return f"{value:.{digits}f}"


def perl_str(value: Any) -> str:
    """How Perl prints a value: numbers with up to 15 significant digits."""
    if isinstance(value, bool):
        return "1" if value else ""
    if isinstance(value, float):
        if math.isfinite(value) and value == int(value) and abs(value) < 1e15:
            return str(int(value))
        return f"{value:.15g}"
    return str(value)


PERL_NUMBER = re.compile(r"^\s*[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def perl_num(value: Any) -> float:
    """A value in numeric context: the leading number of a string, or 0."""
    if isinstance(value, int | float):
        return value
    match = PERL_NUMBER.match(str(value))
    return float(match.group(0)) if match else 0.0


def crc8(data: bytes, poly: int, init: int = 0) -> int:
    """Digest::CRC with width 8, not reflected, as FHEM uses it."""
    crc = init
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ poly) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def hex_bytes(hex_str: str) -> bytes:
    """pack("H*", $hex), which pads an odd number of digits with 0."""
    if len(hex_str) % 2:
        hex_str += "0"
    return bytes.fromhex(hex_str)


WIND_DIRECTIONS = (
    "N",
    "NNE",
    "NE",
    "ENE",
    "E",
    "ESE",
    "SE",
    "SSE",
    "S",
    "SSW",
    "SW",
    "WSW",
    "W",
    "WNW",
    "NW",
    "NNW",
    "N",
)
