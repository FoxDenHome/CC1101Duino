"""Packetizers turn raw pulse timings into bit streams and back."""

from __future__ import annotations

import math

from .signal import (
    NUMBER_RANGE_ZERO,
    BinarySignal,
    NotSupportedError,
    NumberRange,
    RawSignal,
)


class SignalPacketizer:
    def unpack(self, raw_signal: RawSignal) -> list[BinarySignal]:
        raise NotSupportedError

    def pack(self, signal: BinarySignal) -> RawSignal:
        raise NotSupportedError


class _SignalCollector:
    """Accumulates bits and keeps each run that reaches the minimum length."""

    def __init__(self, min_len: int) -> None:
        self.min_len = min_len
        self.signals: list[BinarySignal] = []
        self.current: list[int] = []

    def flush(self) -> None:
        if len(self.current) >= self.min_len:
            self.signals.append(BinarySignal(self.current))
        self.current = []


class SignalPacketizerFixed(SignalPacketizer):
    """Every pulse is a multiple of one base length; high = 1, low = 0."""

    min_len = 5
    pulse: NumberRange = NUMBER_RANGE_ZERO
    max_consecutive_pulse = 3

    def _unpack_bits(self, raw_signal: RawSignal, min_len: int) -> list[BinarySignal]:
        pulse_len = raw_signal.find_closest_abs(self.pulse)
        if not pulse_len:
            return []

        collector = _SignalCollector(min_len)
        for timing in raw_signal.timings:
            # Round half up, like JS Math.round
            pulse_count = math.floor(abs(timing) / pulse_len + 0.5)
            if pulse_count < 1 or pulse_count > self.max_consecutive_pulse:
                collector.flush()
                continue
            collector.current.extend([1 if timing > 0 else 0] * pulse_count)
        collector.flush()

        return collector.signals

    def unpack(self, raw_signal: RawSignal) -> list[BinarySignal]:
        return self._unpack_bits(raw_signal, self.min_len)

    def pack(self, signal: BinarySignal) -> RawSignal:
        pulse = int(self.pulse.value)
        return RawSignal("MU", 0, [pulse if bit else -pulse for bit in signal.bits])


class SignalPacketizerOnOffBit(SignalPacketizerFixed):
    """Each bit is three base pulses: high, low, then the data bit."""

    max_consecutive_pulse = 2

    def unpack(self, raw_signal: RawSignal) -> list[BinarySignal]:
        collector = _SignalCollector(self.min_len)
        for bin_sig in self._unpack_bits(raw_signal, self.min_len * 3):
            bits = bin_sig.bits
            i = 0
            while i < len(bits) - 2:
                # Align ourselves on the next "1 0" prefix
                if bits[i] != 1 or bits[i + 1] != 0:
                    collector.flush()
                    i += 1
                    continue
                collector.current.append(bits[i + 2])
                i += 3
            collector.flush()

        return collector.signals

    def pack(self, signal: BinarySignal) -> RawSignal:
        bits = []
        for bit in signal.bits:
            bits.extend((1, 0, bit))
        return super().pack(BinarySignal(bits))


class SignalPacketizerFixedVariable(SignalPacketizer):
    """Each bit is a fixed pulse followed by a pulse whose length encodes 0 or 1."""

    min_len = 5
    fixed_pulse: NumberRange = NUMBER_RANGE_ZERO
    zero_pulse: NumberRange = NUMBER_RANGE_ZERO
    one_pulse: NumberRange = NUMBER_RANGE_ZERO

    def unpack(self, raw_signal: RawSignal) -> list[BinarySignal]:
        fixed = raw_signal.find_closest(self.fixed_pulse)
        zero = raw_signal.find_closest(self.zero_pulse)
        one = raw_signal.find_closest(self.one_pulse)

        if not fixed or not zero or not one:
            return []

        default = fixed if fixed < 0 else zero

        collector = _SignalCollector(self.min_len)
        last = default

        for timing in raw_signal.timings:
            if timing not in (fixed, zero, one):
                collector.flush()
                last = default
                continue

            if last == fixed:
                if timing == fixed:
                    continue
                collector.current.append(1 if timing == one else 0)
            elif timing != fixed:
                collector.flush()

            last = timing

        collector.flush()

        return collector.signals

    def pack(self, signal: BinarySignal) -> RawSignal:
        timings = []
        for bit in signal.bits:
            timings.append(int(self.fixed_pulse.value))
            timings.append(int(self.one_pulse.value if bit else self.zero_pulse.value))
        return RawSignal("MU", 0, timings)


class LacrossePacketizer(SignalPacketizerFixedVariable):
    min_len = 40
    fixed_pulse = NumberRange(-1075, 200)
    zero_pulse = NumberRange(1400, 200)
    one_pulse = NumberRange(550, 200)


class MinkaAirePacketizer(SignalPacketizerOnOffBit):
    min_len = 13
    pulse = NumberRange(417, 100)
