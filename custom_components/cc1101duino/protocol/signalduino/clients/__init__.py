"""Ports of the FHEM client modules that turn a SIGNALduino dmsg into readings.

Each client module exposes ``parse(message) -> Reading | None``. The readings keep FHEM's
names (temperature, humidity, batteryState, windSpeed, ...) and values, so they can be
checked against FHEM's own test data.
"""

from __future__ import annotations

from collections.abc import Callable

from .. import Message
from . import cul_tcm97001, cul_tx, cul_ws, hideki, oregon, sd_ws, sd_ws07, sd_ws09, sd_ws_maverick
from .base import Reading

__all__ = ["CLIENTS", "Reading", "parse"]

CLIENTS: dict[str, Callable[[Message], Reading | None]] = {
    "CUL_TCM97001": cul_tcm97001.parse,
    "CUL_TX": cul_tx.parse,
    "CUL_WS": cul_ws.parse,
    "Hideki": hideki.parse,
    "OREGON": oregon.parse,
    "SD_WS": sd_ws.parse,
    "SD_WS07": sd_ws07.parse,
    "SD_WS09": sd_ws09.parse,
    "SD_WS_Maverick": sd_ws_maverick.parse,
}


def parse(message: Message) -> Reading | None:
    """Decode a message with its protocol's client module, if that module is ported."""
    client = CLIENTS.get(message.client or "")
    if client is None:
        return None
    return client(message)
