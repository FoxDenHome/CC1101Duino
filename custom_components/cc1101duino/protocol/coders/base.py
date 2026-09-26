"""Base class for protocol coders."""

from __future__ import annotations

from typing import Any

from ..packetizers import SignalPacketizer
from ..signal import (
    BinarySignal,
    EndOfSignalError,
    Modulation,
    NotSupportedError,
    NumberRange,
)

Signal = dict[str, Any]


class SignalCoder:
    """Decodes packetized bit streams into signal dicts and encodes them back."""

    name: str
    packetizer: type[SignalPacketizer]
    frequency: NumberRange
    modulation: Modulation
    repetitions = 1
    repetition_delay = 10000

    def decode(self, signal: BinarySignal) -> Signal | None:
        try:
            return self.decode_internal(signal)
        except (EndOfSignalError, NotSupportedError):
            return None

    def decode_internal(self, signal: BinarySignal) -> Signal | None:
        raise NotSupportedError

    def encode(self, signal: Signal) -> BinarySignal:
        raise NotSupportedError
