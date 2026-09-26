"""Nexus temperature / humidity sensors, also sold under other brands."""

from __future__ import annotations

from ..packetizers import NexusPacketizer
from ..signal import BinarySignal, Modulation, NumberRange
from .base import Signal, SignalCoder

PACKET_BITS = 36
CONSTANT = 0b1111


class NexusSignalCoder(SignalCoder):
    """36 bits: ID (8), battery ok (1), unused (1), channel (2), temperature in 0.1 °C
    (12, signed), constant 1111 (4), humidity in % (8)."""

    name = "nexus"
    packetizer = NexusPacketizer
    frequency = NumberRange(433.92, 1.0)
    modulation = Modulation.ASK_OOK

    def decode_internal(self, signal: BinarySignal) -> list[Signal] | None:
        # The last packet of a transmission is one bit short, see SignalPacketizerPulseDistance
        if len(signal.bits) not in (PACKET_BITS - 1, PACKET_BITS):
            return None

        sensor_id = str(signal.read_number_msb_first(8))
        signal.read_bits(4)  # battery ok, unused, channel
        temperature = signal.read_number_msb_first(12)
        if temperature >= 1 << 11:
            temperature -= 1 << 12
        if signal.read_number_msb_first(4) != CONSTANT:
            return None

        results = [self._make_signal("temperature", sensor_id, "°C", temperature / 10)]

        # Humidity's lowest bit is lost in a short packet, so it is only reported from full ones
        if len(signal.bits) == PACKET_BITS:
            humidity = signal.read_number_msb_first(8)
            if humidity > 100:
                return None
            results.append(self._make_signal("humidity", sensor_id, "%", humidity))

        return results

    def _make_signal(self, subtype: str, sensor_id: str, unit: str, value: float) -> Signal:
        return {
            "coder": self.name,
            "type": "sensor",
            "subtype": subtype,
            "id": sensor_id,
            "unit": unit,
            "value": round(value, 1),
        }
