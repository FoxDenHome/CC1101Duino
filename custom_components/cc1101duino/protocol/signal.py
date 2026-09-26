"""Raw pulse-timing signals and bit streams exchanged with the CC1101Duino."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum


class Modulation(IntEnum):
    INVALID = -1

    TWOFSK = 0
    GFSK = 1
    ASK_OOK = 2
    FOURFSK = 3
    MSK = 4


class NotSupportedError(Exception):
    """Raised when a coder or packetizer cannot handle a signal."""


class EndOfSignalError(Exception):
    """Raised when reading past the end of a BinarySignal."""


@dataclass(frozen=True)
class NumberRange:
    value: float
    tolerance: float


NUMBER_RANGE_ZERO = NumberRange(0, 0)

MAX_UNIQUE_PULSES = 10


def _sign(value: float) -> int:
    return (value > 0) - (value < 0)


class RawSignal:
    """A sequence of pulse timings in microseconds (positive = high, negative = low)."""

    def __init__(
        self,
        signal_type: str,
        clock_index: int,
        timings: list[int],
        modulation: int = Modulation.INVALID,
        frequency: float = 0,
        rssi: int = 0,
    ) -> None:
        self.signal_type = signal_type
        self.clock_index = clock_index
        self.rssi = rssi
        self.frequency = frequency
        self.modulation = modulation
        self.timings = timings
        # dict keeps insertion order, which find_closest relies on for ties
        self.unique_timings = list(dict.fromkeys(timings))

    @classmethod
    def from_string(cls, line: str) -> RawSignal | None:
        """Parse a received line such as ``^SMU;P0=...;D=...;CP=3;R=190;F=433.88;M=2;``."""
        line = line.strip()
        if len(line) < 3 or not line.startswith("^S"):
            return None

        fields = line[2:].split(";")
        if len(fields) < 3:
            return None

        signal_type = fields.pop(0)

        rssi = -1
        clock_index = -1
        frequency = 0.0
        modulation: int = Modulation.INVALID
        timing_values: dict[str, int] = {}
        timing_str = None

        try:
            for field in fields:
                key, _, value = field.partition("=")
                if key.startswith("P") and len(key) > 1:
                    timing_values[key[1]] = int(value)
                elif key == "D":
                    timing_str = value
                elif key == "CP":
                    clock_index = int(value)
                elif key == "R":
                    rssi = int(value)
                elif key == "F":
                    frequency = float(value)
                elif key == "M":
                    modulation = int(value)
        except ValueError:
            return None

        if not timing_str:
            return None

        timings = []
        for char in timing_str:
            timing = timing_values.get(char)
            if not timing:
                return None
            timings.append(timing)

        return cls(signal_type, clock_index, timings, modulation, frequency, rssi)

    def to_command_string(self, repetitions: int, repetition_delay: int) -> str:
        """Build a transmit command for the firmware's ``S`` command."""
        params: dict[str, object] = {
            "F": self.frequency,
            "M": int(self.modulation),
            "R": repetitions,
            "S": repetition_delay,
        }

        pulse_indexes: dict[int, int] = {}
        data = ""
        for timing in self.timings:
            index = pulse_indexes.get(timing)
            if index is None:
                index = len(pulse_indexes)
                if index >= MAX_UNIQUE_PULSES:
                    raise ValueError(f"More than {MAX_UNIQUE_PULSES} unique pulses")
                pulse_indexes[timing] = index
            data += str(index)
        params["D"] = data
        for timing, index in pulse_indexes.items():
            params[f"P{index}"] = timing

        return "^S;" + "".join(f"{key}={value};" for key, value in params.items()) + "\n"

    def find_closest(self, pulse: NumberRange, ignore_sign: bool = False) -> int | None:
        """Find the observed timing nearest to the expected pulse, within tolerance."""
        best_timing = None
        best_dist = None

        pulse_sign = _sign(pulse.value)
        pulse_abs = abs(pulse.value)

        for timing in self.unique_timings:
            # Never turn a low pulse into a high pulse, unless requested
            if not ignore_sign and _sign(timing) != pulse_sign:
                continue

            dist = abs(pulse_abs - abs(timing))
            if dist > pulse.tolerance:
                continue

            if best_dist is None or dist < best_dist:
                best_timing = timing
                best_dist = dist

        return best_timing

    def find_closest_abs(self, pulse: NumberRange) -> int | None:
        timing = self.find_closest(pulse, ignore_sign=True)
        if timing:
            return abs(timing)
        return None


class BinarySignal:
    """A bit stream with a read cursor, as produced by a packetizer."""

    def __init__(self, bits: list[int]) -> None:
        self.bits = bits
        self.offset = 0
        self.reader_hook: Callable[[int, int], None] | None = None

    @classmethod
    def from_untyped(cls, raw_bits) -> BinarySignal:
        return cls([int(bit) for bit in raw_bits])

    def copy(self) -> BinarySignal:
        """Fresh reader over the same bits, so several coders can decode one packet."""
        return BinarySignal(self.bits)

    def match_and_strip_header(self, header: list[int], header_offset: int = 0) -> bool:
        check_length = len(header) - header_offset
        if self.bits[:check_length] != header[header_offset:]:
            return False
        self.offset += check_length
        return True

    def match_and_strip_header_fuzzy(
        self, header: list[int], header_missing_allowed: int = 1
    ) -> bool:
        """Match a header that may have up to ``header_missing_allowed`` leading bits cut off."""
        return any(
            self.match_and_strip_header(header, i) for i in range(header_missing_allowed + 1)
        )

    def read_bit(self) -> int:
        if self.offset >= len(self.bits):
            raise EndOfSignalError
        bit = self.bits[self.offset]
        if self.reader_hook:
            self.reader_hook(bit, self.offset)
        self.offset += 1
        return bit

    def read_bits(self, num: int) -> list[int]:
        return [self.read_bit() for _ in range(num)]

    def read_bits_as_string(self, num: int) -> str:
        return "".join(str(bit) for bit in self.read_bits(num))

    def read_number_lsb_first(self, bits: int) -> int:
        res = 0
        for i in range(bits):
            res |= self.read_bit() << i
        return res

    def read_number_msb_first(self, bits: int) -> int:
        res = 0
        for i in reversed(range(bits)):
            res |= self.read_bit() << i
        return res
