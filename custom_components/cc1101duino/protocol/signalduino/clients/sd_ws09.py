"""Port of FHEM's 14_SD_WS09.pm: WH1080 / WS0101 / CTW600 weather stations (dmsg ``P9#``).

FHEM keeps some state per device that is left out here: the rain offset across counter
resets (so rain_total equals rain) and the wind direction average over time (so it is the
average of this message alone).
"""

from __future__ import annotations

import math
from typing import Any

from .. import Message
from .base import Reading, bin2dec, crc8, hex_bytes, hex_to_bits, perl_round

WIND_DIRECTIONS = (
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
)  # fmt: skip

WIND_UNITS = (("kmh", 3.6), ("fts", 3.28), ("mph", 2.24), ("kn", 1.94))


def _shift(raw: str) -> str:
    """Shift right by one bit, inserting a 1."""
    bits = ("1" + hex_to_bits(raw))[:-1]
    return f"{int(bits, 2):0{len(bits) // 4}X}"


def _crc(raw: str) -> int:
    return crc8(hex_bytes(raw[2:]), 0x31)


def _bcd(bits: str) -> str:
    return f"{bin2dec(bits):x}"


def _wind_average(speed: float, degree: float) -> int | None:
    """SD_WS09_WindDirAverage over a single sample."""
    rad = math.radians(degree)
    total_sin = math.sin(rad) * speed
    total_cos = math.cos(rad) * speed
    return int(math.degrees(math.atan2(total_sin, total_cos)) + 360) % 360


def parse(message: Message) -> Reading | None:
    raw = message.dmsg.partition("#")[2]
    bits = hex_to_bits(raw)
    model = None

    if len(raw) < 20:  # WH3080 UV / solar
        syncpos = bits.find("1111110111")
        if not 0 <= syncpos < 3:
            return None
        model = "WH1080"
        if syncpos < 2:
            raw = _shift(raw)
        if syncpos == 0:
            raw = _shift(raw)
    else:
        syncpos = bits.find("11111110")
        if syncpos == -1 or len(bits) - syncpos < 60:
            return None

    if model == "WH1080":
        if _crc(raw) != 0:
            return None
    else:
        original = raw
        for _ in range(3):
            if _crc(raw) == 0:
                model = "WH1080"
                break
            raw = _shift(raw)
        else:
            raw = original

    bits = hex_to_bits(raw)
    readings: dict[str, Any] = {}
    if model == "WH1080":
        sensdata = bits[8:]
        whid = sensdata[0:4]
        sensor_id = bin2dec(sensdata[4:12])
        if whid == "1010":
            bat = "ok" if bin2dec(sensdata[64:68]) == 0 else "low"
            temp = (bin2dec(sensdata[12:24]) - 400) / 10
            hum = bin2dec(sensdata[24:32])
            wind_direction = bin2dec(sensdata[68:72])
            wind_speed = perl_round(bin2dec(sensdata[32:40]) * 34 / 100, 1)
            wind_gust = perl_round(bin2dec(sensdata[40:48]) * 34 / 100, 1)
            rain = bin2dec(sensdata[52:64]) * 0.3
        elif whid == "0111":
            return Reading(
                device=model,
                model=model,
                readings={
                    "id": sensor_id,
                    "UV": bin2dec(sensdata[12:16]),
                    "Lux": bin2dec(sensdata[24:48]) / 10,
                },
            )
        else:
            # 1011 is the DCF time, which FHEM does not store
            return None
    else:
        if bits[0:8] != "11111110" or len(bits) <= 70:
            return None
        sensdata = bits[syncpos + 8 :]
        model = "CTW600"
        bat = bin2dec(sensdata[0:3])
        sensor_id = bin2dec(sensdata[4:10])
        temp = (bin2dec(sensdata[12:22]) - 400) / 10
        hum = bin2dec(sensdata[22:30])
        wind_direction = bin2dec(sensdata[66:70])
        wind_speed = perl_round(bin2dec(sensdata[30:46]) / 240, 1)
        wind_gust = perl_round(bin2dec(sensdata[40:48]) * 34 / 100, 1)
        rain = perl_round(bin2dec(sensdata[46:62]) * 0.3, 1)

    if not 0 <= hum <= 100 or not -40 <= temp <= 60:
        return None

    degree = wind_direction * 360 / 16
    readings["id"] = sensor_id
    readings["temperature"] = temp
    if hum != 0:
        readings["humidity"] = hum
    readings["battery"] = bat
    readings["batteryState"] = bat
    readings["rain"] = rain
    readings["rain_total"] = rain
    readings["windGust"] = wind_gust
    readings["windSpeed"] = wind_speed
    for unit, factor in WIND_UNITS:
        readings[f"windGust_{unit}"] = perl_round(float(wind_gust) * factor, 1)
        readings[f"windSpeed_{unit}"] = perl_round(float(wind_speed) * factor, 1)
    readings["windDirectionAverage"] = _wind_average(float(wind_speed), degree)
    readings["windDirection"] = wind_direction
    readings["windDirectionDegree"] = degree
    readings["windDirectionText"] = WIND_DIRECTIONS[wind_direction]
    return Reading(device=model, model=model, readings=readings)
