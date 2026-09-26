"""Turns received lines into signal dicts via SIGNALduino demodulation and client modules."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from ..coders import Signal
from . import Demodulator, Message
from .clients import CLIENTS, Reading, parse
from .clients.base import perl_num

# Like FHEM, a message repeated within this many seconds is only reported once
REPEAT_WINDOW = 2.0

MPH_TENTH = 0.1 * 0.44704  # m/s

# Wind speeds are reported in m/s, except by these modules
WIND_FACTORS = {"Hideki": MPH_TENTH, "CUL_WS": 1 / 3.6}

# FHEM reading -> (subtype, unit)
READINGS: dict[str, tuple[str, str]] = {
    "temperature": ("temperature", "°C"),
    "temperature2": ("temperature_2", "°C"),
    "temperature3": ("temperature_3", "°C"),
    "temperature4": ("temperature_4", "°C"),
    "temp-food": ("temperature_food", "°C"),
    "temp-bbq": ("temperature_bbq", "°C"),
    "windChill": ("wind_chill", "°C"),
    "humidity": ("humidity", "%"),
    "pressure": ("pressure", "hPa"),
    "windSpeed": ("wind_speed", "m/s"),
    "wind_speed": ("wind_speed", "m/s"),
    "wind": ("wind_speed", "m/s"),
    "wind_avspeed": ("wind_speed_average", "m/s"),
    "windGust": ("wind_gust", "m/s"),
    "windDirectionDegree": ("wind_direction", "°"),
    "wind_direction": ("wind_direction", "°"),
    "rain": ("rain", "mm"),
    "rain_total": ("rain", "mm"),
    "rain_rate": ("rain_rate", "mm/h"),
    "batteryPercent": ("battery", "%"),
    "batteryVoltage": ("battery_voltage", "V"),
    "brightness": ("illuminance", "lx"),
    "Lux": ("illuminance", "lx"),
    "uv": ("uv_index", "UV index"),
    "UV": ("uv_index", "UV index"),
    "uv_val": ("uv_index", "UV index"),
    "distance": ("distance", "cm"),
}

WIND_SUBTYPES = ("wind_speed", "wind_speed_average", "wind_gust")


def reading_signals(message: Message, reading: Reading) -> list[Signal]:
    """One signal per value of a decoded sensor message."""
    client = message.client or ""
    base = {
        "coder": client.lower(),
        "type": "sensor",
        # Unique ids are joined with "-"
        "id": reading.device.replace("-", "_"),
        "model": reading.model,
        "protocol": message.protocol.id,
    }
    values: dict[str, Any] = {}
    for name, value in reading.readings.items():
        if name == "batteryState":
            values["battery_low"] = (value != "ok", None)
            continue
        mapped = READINGS.get(name)
        if mapped is None or value in (None, ""):
            continue
        subtype, unit = mapped
        if subtype == "rain" and "rain_total" in reading.readings and name == "rain":
            continue  # prefer the counter that does not reset
        number = perl_num(value)
        if subtype in WIND_SUBTYPES:
            number *= WIND_FACTORS.get(client, 1)
        values[subtype] = (round(number, 2), unit)

    return [
        {**base, "subtype": subtype, "value": value, **({"unit": unit} if unit else {})}
        for subtype, (value, unit) in values.items()
    ]


def message_signal(message: Message) -> Signal:
    """A demodulated message that no ported client module decodes, e.g. a remote button."""
    return {
        "coder": "signalduino",
        "type": "message",
        "protocol": message.protocol.id,
        "name": message.protocol.name,
        "data": message.dmsg,
    }


def split_line(line: str) -> tuple[str, int | None]:
    """The SIGNALduino message of a received line, without this firmware's F= and M=."""
    parts = line.removeprefix("^S").split(";")
    modulation = None
    kept = []
    for part in parts:
        if part.startswith("F="):
            continue
        if part.startswith("M="):
            modulation = int(part[2:]) if part[2:].isdigit() else None
            continue
        kept.append(part)
    return ";".join(kept), modulation


class SignalduinoCoder:
    """Decodes lines with every SIGNALduino protocol this firmware can receive."""

    # The firmware only receives pulse timings (ASK / OOK)
    MODULATION = 2

    def __init__(
        self,
        enabled_ids: set[str] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.demodulator = Demodulator(enabled_ids)
        self._clock = clock
        self._recent: dict[str, float] = {}

    def process_line(self, line: str) -> list[Signal]:
        body, modulation = split_line(line)
        if modulation is not None and modulation != self.MODULATION:
            return []

        results: list[Signal] = []
        seen: set[str] = set()
        for message in self.demodulator.demodulate(body):
            if message.dmsg in seen:
                continue
            seen.add(message.dmsg)
            if message.client in CLIENTS:
                reading = parse(message)
                if reading is not None:
                    results.extend(reading_signals(message, reading))
            elif message.client is None:
                # Protocols without a FHEM client module are still being worked out and
                # mostly match noise
                continue
            else:
                signal = message_signal(message)
                if self._is_repeat(message.dmsg):
                    # Remotes repeat each press; only the first one should trigger anything
                    signal["repeat"] = True
                results.append(signal)
        return results

    def _is_repeat(self, dmsg: str) -> bool:
        """Drop repeats within 2 seconds, like SD_Message::Dispatch.

        FHEM only compares with the previous message; remembering every recent one also
        catches repeats of lines that carry several messages.
        """
        now = self._clock()
        self._recent = {
            key: seen for key, seen in self._recent.items() if now - seen < REPEAT_WINDOW
        }
        repeat = dmsg in self._recent
        self._recent[dmsg] = now
        return repeat
