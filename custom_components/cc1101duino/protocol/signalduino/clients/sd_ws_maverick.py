"""Port of FHEM's 14_SD_WS_Maverick.pm: Maverick ET-732/733 BBQ thermometers (``P47#``)."""

from __future__ import annotations

from typing import Any

from .. import Message
from .base import Reading, perl_num

QUATERNARY = str.maketrans("569A", "0123")


def _probe(digits: str) -> tuple[Any, str]:
    """Temperature of one probe, and whether it is connected."""
    if digits == "55555":
        return None, "disconnected"
    temp = -532.0
    for i, char in enumerate(digits.translate(QUATERNARY)):
        temp += perl_num(char) * 4 ** (4 - i)
    if temp <= 0 or temp > 300:
        return None, "unknown"
    return temp, "connected"


def parse(message: Message) -> Reading | None:
    raw = message.dmsg.partition("#")[2]
    message_type = {"55": "normal", "59": "normal", "66": "sync", "6A": "sync"}.get(raw[0:2])
    if message_type is None:
        return None
    food, food_state = _probe(raw[2:7])
    bbq, bbq_state = _probe(raw[7:12])

    readings: dict[str, Any] = {"checksum": raw[12:].translate(QUATERNARY)}
    if food is not None:
        readings["temp-food"] = food
    if bbq is not None:
        readings["temp-bbq"] = bbq
    readings["messageType"] = message_type
    readings["Sensor-1-food_state"] = food_state
    readings["Sensor-2-bbq_state"] = bbq_state
    return Reading(device="SD_WS_Maverick", model="Maverick ET-732/733", readings=readings)
