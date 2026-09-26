"""Pure-Python CC1101Duino protocol decoding / encoding (no Home Assistant imports)."""

from __future__ import annotations

from .coders import ALL_CODERS, Signal, SignalCoder
from .packetizers import SignalPacketizer
from .signal import BinarySignal, NotSupportedError, RawSignal

__all__ = ["LineCoder", "NotSupportedError", "RawSignal", "Signal"]


class LineCoder:
    """Converts between firmware serial lines and decoded signal dicts."""

    def __init__(self, coders: list[type[SignalCoder]] | None = None) -> None:
        self.packetizers: dict[type[SignalPacketizer], SignalPacketizer] = {}
        self.coders: dict[str, SignalCoder] = {}
        for coder_class in ALL_CODERS if coders is None else coders:
            self.load_coder(coder_class())

    def load_coder(self, coder: SignalCoder) -> None:
        if coder.packetizer not in self.packetizers:
            self.packetizers[coder.packetizer] = coder.packetizer()
        self.coders[coder.name] = coder

    def create_signal_line(self, signal: Signal) -> str:
        coder = self.coders.get(signal.get("coder"))
        if coder is None:
            raise NotSupportedError(f"Unknown coder: {signal.get('coder')}")

        raw_signal = self.packetizers[coder.packetizer].pack(coder.encode(signal))
        raw_signal.frequency = coder.frequency.value
        raw_signal.modulation = coder.modulation

        return raw_signal.to_command_string(coder.repetitions, coder.repetition_delay)

    def process_signal_line(self, line: str) -> list[Signal]:
        """Decode one received line. Identical packets repeated within it are reported once."""
        raw_signal = RawSignal.from_string(line)
        if raw_signal is None:
            return []
        return self.process_raw_signal(raw_signal)

    def process_raw_signal(self, raw_signal: RawSignal) -> list[Signal]:
        results: list[Signal] = []
        packetized: dict[type[SignalPacketizer], list[BinarySignal]] = {}

        for coder in self.coders.values():
            if abs(raw_signal.frequency - coder.frequency.value) > coder.frequency.tolerance:
                continue
            if raw_signal.modulation != coder.modulation:
                continue

            signals = packetized.get(coder.packetizer)
            if signals is None:
                signals = self.packetizers[coder.packetizer].unpack(raw_signal)
                packetized[coder.packetizer] = signals

            for bin_sig in signals:
                decoded = coder.decode(bin_sig.copy())
                if decoded is not None and decoded not in results:
                    results.append(decoded)

        return results
