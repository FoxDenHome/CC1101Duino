"""Fingerprints that tell whether two unrecognized signals come from the same kind of device."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

# Lines shorter than this are too short to say anything about
MIN_PULSES = 24
# Pulses that make up less of a line than this are sync / end marks or noise
SIGNIFICANT_SHARE = 0.04
# Noise has many pulse lengths, encodings have few
MAX_SIGNIFICANT_PULSES = 6
# Timings of one transmitter jitter between receptions by this much
PULSE_TOLERANCE_US = 80
PULSE_TOLERANCE_SHARE = 0.15
# Receptions that start late miss a few pulses of the first packet
LENGTH_TOLERANCE = 4
LENGTH_TOLERANCE_SHARE = 0.1
FREQUENCY_TOLERANCE_MHZ = 0.2
# Manchester messages shorter than this many bits
MIN_MANCHESTER_BITS = 16


def _fields(line: str) -> dict[str, str]:
    fields = {}
    for part in line.removeprefix("^S").split(";"):
        key, _, value = part.partition("=")
        fields[key] = value
    return fields


def _pulses_match(a: int, b: int) -> bool:
    if (a > 0) != (b > 0):
        return False
    return abs(a - b) <= max(PULSE_TOLERANCE_US, PULSE_TOLERANCE_SHARE * max(abs(a), abs(b)))


def _covered(pulses: tuple[int, ...], by: tuple[int, ...]) -> bool:
    return all(any(_pulses_match(pulse, other) for other in by) for pulse in pulses)


@dataclass(frozen=True)
class Fingerprint:
    """The pulse lengths a signal is built from, which stay the same whatever it transmits.

    Two receptions of one sensor with different readings, or two remotes of the same
    model, have similar fingerprints even though their data differs.
    """

    # "pulse" for MS / MU messages (one transmitter may show up as either), "manchester" for MC
    kind: str
    frequency: float
    modulation: int | None
    # Significant pulse lengths in µs, sorted; positive is high, negative is low
    pulses: tuple[int, ...]
    # Longest run of significant pulses, i.e. the length of one packet between sync marks
    length: int
    # Whether every run that long was cut off by the start or end of the reception, which makes
    # the length only a lower bound; weak receptions often hold only part of a packet
    partial: bool = False

    @classmethod
    def from_line(cls, line: str) -> Fingerprint | None:
        """Fingerprint a received line, or None if it looks like noise."""
        if not line.startswith("^S"):
            return None
        fields = _fields(line)
        message_type = line[2:4]
        try:
            frequency = float(fields.get("F") or 0)
            modulation = int(fields["M"]) if fields.get("M") else None
            if message_type == "MC":
                clock = int(fields["C"])
                if int(fields.get("L") or 0) < MIN_MANCHESTER_BITS or clock <= 0:
                    return None
                return cls("manchester", frequency, modulation, (clock,), int(fields["L"]))
            if message_type not in ("MS", "MU"):
                return None
            timings = {
                key[1:]: int(value)
                for key, value in fields.items()
                if len(key) == 2 and key[0] == "P" and key[1].isdigit()
            }
        except (KeyError, ValueError):
            return None

        data = fields.get("D", "")
        if len(data) < MIN_PULSES or any(index not in timings for index in data):
            return None
        significant = {
            index
            for index, count in Counter(data).items()
            if count >= SIGNIFICANT_SHARE * len(data)
        }
        if not 2 <= len(significant) <= MAX_SIGNIFICANT_PULSES:
            return None
        pulses = tuple(sorted(timings[index] for index in significant))
        runs = [
            (match.start(), match.end())
            for match in re.finditer(f"[{''.join(significant)}]+", data)
        ]
        length = max(end - start for start, end in runs)
        partial = all(
            start == 0 or end == len(data) for start, end in runs if end - start == length
        )
        return cls("pulse", frequency, modulation, pulses, length, partial)

    def similar(self, other: Fingerprint) -> bool:
        return (
            self.kind == other.kind
            and self.modulation == other.modulation
            and abs(self.frequency - other.frequency) <= FREQUENCY_TOLERANCE_MHZ
            and _covered(self.pulses, other.pulses)
            and _covered(other.pulses, self.pulses)
            and self._length_matches(other)
        )

    def _length_matches(self, other: Fingerprint) -> bool:
        shorter, longer = sorted((self, other), key=lambda fingerprint: fingerprint.length)
        if shorter.partial:
            return True
        return longer.length - shorter.length <= max(
            LENGTH_TOLERANCE, LENGTH_TOLERANCE_SHARE * longer.length
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "frequency": self.frequency,
            "modulation": self.modulation,
            "pulses": list(self.pulses),
            "length": self.length,
            "partial": self.partial,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Fingerprint:
        return cls(
            data["kind"],
            data["frequency"],
            data["modulation"],
            tuple(data["pulses"]),
            data["length"],
            data.get("partial", False),
        )
