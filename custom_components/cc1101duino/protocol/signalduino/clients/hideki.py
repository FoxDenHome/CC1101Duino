"""Port of FHEM's 14_Hideki.pm: Hideki protocol sensors (Bresser, Cresta, TFA, Hama)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .. import Message
from .base import Reading

COMFORT_LEVELS = {
    0: "Hum. OK. Temp. uncomfortable (>24.9 or <20)",
    1: "Wet. More than 69% RHWet. More than 69% RH",
    2: "Dry. Less than 40% RH",
    3: "Temp. and Hum. comfortable",
}

WIND_DIRECTIONS = (
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
)  # fmt: skip

WIND_DIRECTION_MAP = (0, 15, 13, 14, 9, 10, 12, 11, 1, 2, 4, 3, 8, 7, 5, 6)


def _second_check(b: int) -> int:
    if b & 0x80:
        b ^= 0x95
    c = b ^ (b >> 1)
    if b & 1:
        c ^= 0x5F
    if c & 1:
        b ^= 0x5F
    return b ^ (c >> 1)


def decrypt_and_check(raw: str) -> list[int] | None:
    data = [int(raw[i : i + 2], 16) for i in range(0, len(raw) - 1, 2)]
    if len(data) < 3:
        return None
    count = ((data[2] ^ (data[2] << 1)) >> 1) & 0x1F
    if len(data) <= count + 2 or data[0] != 0x75:
        return None
    cs1 = 0
    cs2 = 0
    for i in range(1, count + 2):
        cs1 ^= data[i]
        cs2 = _second_check(data[i] ^ cs2)
        data[i] ^= (data[i] << 1) & 0xFF
    if cs1 != 0 or cs2 != data[count + 2]:
        return None
    return data


def _temperature(d: list[int]) -> float:
    temp = 100 * (d[5] & 0x0F) + 10 * (d[4] >> 4) + (d[4] & 0x0F)
    if not d[5] & 0x80:
        temp = -temp
    return temp / 10


def _channel(d: list[int]) -> int:
    channel = d[1] >> 5
    return channel - 1 if channel >= 5 else channel


def _humidity(d: list[int]) -> int:
    return 10 * (d[6] >> 4) + (d[6] & 0x0F)


def _battery(d: list[int]) -> str:
    return "ok" if d[2] >> 6 == 3 else "low"


def _count(d: list[int]) -> int:
    return d[3] >> 6


def _comfort(d: list[int]) -> Any:
    level = (d[7] >> 2) & 0x03
    return COMFORT_LEVELS.get(level, level)


def _rain(d: list[int]) -> float:
    return (d[4] + d[5] * 0xFF) * 0.7


def _windchill(d: list[int]) -> float:
    chill = 100 * (d[7] & 0x0F) + 10 * (d[6] >> 4) + (d[6] & 0x0F)
    if not d[7] & 0x80:
        chill = -chill
    return chill / 10


def _winddir(d: list[int]) -> int:
    return WIND_DIRECTION_MAP[d[11] >> 4]


def _windspeed(d: list[int]) -> str:
    speed = (d[9] & 0x0F) * 100 + (d[8] >> 4) * 10 + (d[8] & 0x0F)
    # FHEM's windSpeedCorr (default 1) formats it once more
    return f"{float(f'{speed:.2f}') * 1:.2f}"


def _windgust(d: list[int]) -> str:
    gust = (d[10] >> 4) * 100 + (d[10] & 0x0F) * 10 + (d[9] >> 4)
    return f"{float(f'{gust:.2f}') * 1:.2f}"


Decoder = Callable[[list[int]], Any]

SENSOR_TYPES: dict[int, dict[str, Decoder]] = {
    30: {
        "temperature": _temperature,
        "channel": _channel,
        "battery": _battery,
        "humidity": _humidity,
        "comfort_level": _comfort,
        "package_number": _count,
    },
    31: {
        "temperature": _temperature,
        "channel": _channel,
        "battery": _battery,
        "package_number": _count,
    },
    14: {
        "rain": _rain,
        "channel": _channel,
        "battery": _battery,
        "package_number": _count,
    },
    12: {
        "temperature": _temperature,
        "channel": _channel,
        "battery": _battery,
        "package_number": _count,
        "windChill": _windchill,
        "windDirection": _winddir,
        "windDirectionDegree": lambda d: _winddir(d) * 22.5,
        "windDirectionText": lambda d: WIND_DIRECTIONS[_winddir(d)],
        "windGust": _windgust,
        "windSpeed": _windspeed,
    },
    13: {
        "temperature": _temperature,
        "channel": _channel,
        "battery": _battery,
        "package_number": _count,
    },
}


def parse(message: Message) -> Reading | None:
    raw = message.dmsg.partition("#")[2]
    data = decrypt_and_check(raw)
    if not data or len(data) < 4:
        return None

    sensor_type = data[3] & 0x1F
    decoders = SENSOR_TYPES.get(sensor_type)
    if decoders is None:
        return None
    try:
        readings = {key: decoder(data) for key, decoder in decoders.items()}
    except IndexError:
        return None
    readings["batteryState"] = readings["battery"]

    model = f"Hideki_{sensor_type}"
    return Reading(device=f"{model}_{readings['channel']}", model=model, readings=readings)
