"""LaCrosse TX temperature / humidity sensors."""

from __future__ import annotations

from ..packetizers import LacrossePacketizer
from ..signal import BinarySignal, Modulation, NumberRange
from .base import Signal, SignalCoder

HEADER = [0, 0, 0, 0, 1, 0, 1, 0]

SENSOR_TEMPERATURE = 0b0000
SENSOR_HUMIDITY = 0b1110


class LacrosseSignalCoder(SignalCoder):
    name = "lacrosse"
    packetizer = LacrossePacketizer
    frequency = NumberRange(433.88, 1.0)
    modulation = Modulation.ASK_OOK

    def decode_internal(self, signal: BinarySignal) -> Signal | None:
        if not signal.match_and_strip_header_fuzzy(HEADER, 2):
            return None

        offset_zero = signal.offset
        parity_tmp = 0
        # The header's last nibble is part of the checksum
        checksum_tmp = 0b0000 + 0b1010

        def hook(bit: int, offset: int) -> None:
            nonlocal parity_tmp, checksum_tmp
            if bit:
                parity_tmp = 1 - parity_tmp
                checksum_tmp += 1 << (3 - ((offset - offset_zero) % 4))

        signal.reader_hook = hook

        # Relevant for just checksum
        sensor_type = signal.read_number_msb_first(4)
        sensor_id = str(signal.read_number_msb_first(7))
        parity = signal.read_bit()

        # Relevant for parity + checksum
        parity_tmp = 0
        tens = signal.read_number_msb_first(4)
        ones = signal.read_number_msb_first(4)
        tenths = signal.read_number_msb_first(4)

        # Relevant for just checksum
        measured_parity = parity_tmp
        tens2 = signal.read_number_msb_first(4)
        ones2 = signal.read_number_msb_first(4)

        # Not relevant for either integrity mechanism
        signal.reader_hook = None
        checksum = signal.read_number_msb_first(4)

        if (
            tens != tens2
            or ones != ones2
            or parity != measured_parity
            or checksum != checksum_tmp & 0b1111
        ):
            return None

        raw_value = tens * 10 + ones + tenths / 10

        if sensor_type == SENSOR_TEMPERATURE:
            return self._make_signal("temperature", sensor_id, "°C", raw_value - 50.0)
        if sensor_type == SENSOR_HUMIDITY:
            return self._make_signal("humidity", sensor_id, "%", raw_value)
        return None

    def _make_signal(self, subtype: str, sensor_id: str, unit: str, value: float) -> Signal:
        return {
            "coder": self.name,
            "type": "sensor",
            "subtype": subtype,
            "id": sensor_id,
            "unit": unit,
            "value": round(value, 1),
        }
