"""Port of FHEM's 14_SD_WS07.pm: Eurochron, Auriol, Hama TS36E and similar (dmsg ``P7#``)."""

from __future__ import annotations

import re

from .. import Message
from .base import Reading, bin_num, hex_to_bits

MATCH = re.compile(r"^P7#[A-Fa-f0-9]{6}[AFaf][A-Fa-f0-9]{2,3}")


def parse(message: Message) -> Reading | None:
    if not MATCH.match(message.dmsg):
        return None
    raw = message.dmsg.partition("#")[2]
    bits = hex_to_bits(raw)

    bat = "ok" if bits[8] == "1" else "low"
    sendmode = None
    channel = bin_num(bits, 9, 11) + 1
    if bits[24:28] == "1010":
        sendmode = "manual" if bits[9] == "1" else "auto"
        channel = bin_num(bits, 10, 11) + 1
    temp: float = bin_num(bits, 12, 23)
    hum = bin_num(bits, 28, 35)

    model = "SD_WS07_TH" if hum else "SD_WS07_T"
    if model != "SD_WS07_T" and not 0 <= hum <= 100:
        return None
    if 700 < temp < 3840:  # outside -25.6 .. 70.0 °C
        return None
    if temp >= 3840:
        temp -= 4096
    temp /= 10

    readings: dict[str, object] = {"temperature": temp}
    if model == "SD_WS07_TH":
        readings["humidity"] = hum
    readings["batteryState"] = bat
    if sendmode is not None:
        readings["sendmode"] = sendmode
    readings["channel"] = channel
    return Reading(device=f"{model}_{channel}", model=model, readings=readings)
