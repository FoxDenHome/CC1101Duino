"""Minka Aire ceiling fan remotes."""

from __future__ import annotations

from ..packetizers import MinkaAirePacketizer
from ..signal import BinarySignal, Modulation, NotSupportedError, NumberRange
from .base import Signal, SignalCoder

COMMANDS = {
    "off": "10100",
    "low": "00100",
    "medium": "01000",
    "high": "10000",
    "light_1": "01010",
    "light_2": "10010",
}

COMMANDS_REV = {bits: name for name, bits in COMMANDS.items()}

COMMANDS["light"] = COMMANDS["light_1"]

ID_BITS = 8
COMMAND_BITS = 5


class MinkaAireSignalCoder(SignalCoder):
    name = "minka_aire"
    packetizer = MinkaAirePacketizer
    frequency = NumberRange(304.2, 1.0)
    modulation = Modulation.ASK_OOK
    repetitions = 10
    repetition_delay = 10000

    def decode_internal(self, signal: BinarySignal) -> Signal | None:
        return {
            "coder": self.name,
            "type": "command",
            "id": signal.read_bits_as_string(ID_BITS),
            "command": COMMANDS_REV.get(signal.read_bits_as_string(COMMAND_BITS)),
        }

    def encode(self, signal: Signal) -> BinarySignal:
        if signal.get("type", "command") != "command":
            raise NotSupportedError

        remote_id = str(signal.get("id", ""))
        command = COMMANDS.get(signal.get("command"))
        if len(remote_id) != ID_BITS or set(remote_id) - {"0", "1"} or command is None:
            raise NotSupportedError

        return BinarySignal.from_untyped(remote_id + command)
