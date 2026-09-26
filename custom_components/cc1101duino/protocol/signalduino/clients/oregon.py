"""Port of FHEM's 41_OREGON.pm: Oregon Scientific v1/v2/v3 sensors.

The dmsg is the bit count as one hex byte, followed by the message bytes.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from .. import Message
from .base import Reading, perl_str

WIND_DIRECTIONS = (
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
)  # fmt: skip

UV_RISK = ("low",) * 3 + ("medium",) * 3 + ("high",) * 2 + ("very high",) * 3

FORECASTS = {0xC: "sunny", 0x6: "partly", 0x2: "cloudy", 0x3: "rain"}

MATCH = re.compile(r"^(3[8-9A-F]|[4-6][0-9A-F]|7[0-8]).*", re.S)


class Bytes(list[int]):
    """Message bytes, where reading past the end gives 0 like Perl's undef."""

    def __getitem__(self, index):  # type: ignore[override]
        try:
            return super().__getitem__(index)
        except IndexError:
            return 0


def hi(value: int) -> int:
    return (value & 0xF0) >> 4


def lo(value: int) -> int:
    return value & 0xF


def bcd(value: int) -> int:
    """sprintf("%02x", $byte) in numeric context: the BCD digits, up to a non-digit."""
    digits = re.match(r"\d*", f"{value:02x}").group(0)  # type: ignore[union-attr]
    return int(digits) if digits else 0


def nibble_sum(count: int, data: Bytes) -> int:
    return sum(hi(data[i]) + lo(data[i]) for i in range(count))


Item = dict[str, Any]


def _temperature(data: Bytes) -> list[Item]:
    sign = -1 if data[6] & 0x8 else 1
    temp = sign * (hi(data[5]) * 10 + lo(data[5]) + hi(data[4]) / 10)
    return [{"type": "temp", "current": temp}]


def _humidity(data: Bytes) -> list[Item]:
    return [{"type": "humidity", "current": lo(data[7]) * 10 + hi(data[6])}]


def _pressure(data: Bytes, forecast_nibble: int, offset: int = 795) -> list[Item]:
    return [
        {
            "type": "pressure",
            "current": data[8] + offset,
            "forecast": FORECASTS.get(forecast_nibble, "unknown"),
        }
    ]


def _simple_battery(data: Bytes) -> list[Item]:
    battery = "low" if data[4] & 0x4 else "ok"
    return [{"type": "battery", "current": battery}, {"type": "batteryState", "current": battery}]


def _percentage_battery(data: Bytes) -> list[Item]:
    level = 100 - 10 * lo(data[4])
    state = "ok" if level > 50 else "low"
    return [
        {"type": "battery", "current": f"{state} {level}%"},
        {"type": "batteryPercent", "current": level},
        {"type": "batteryState", "current": state},
    ]


def _uv_risk(uv: int) -> str:
    return UV_RISK[uv] if 0 <= uv < len(UV_RISK) else "dangerous"


def _uv138(data: Bytes) -> list[Item]:
    uv = lo(data[5]) * 10 + hi(data[4])
    return [{"type": "uv", "current": uv, "risk": _uv_risk(uv)}, *_simple_battery(data)]


def _uvn800(data: Bytes) -> list[Item]:
    uv = hi(data[4])
    return [{"type": "uv", "current": uv, "risk": _uv_risk(uv)}, *_percentage_battery(data)]


def _wind(data: Bytes, direction: float, name: str) -> list[Item]:
    speed = lo(data[7]) * 10 + bcd(data[6]) / 10
    average = bcd(data[8]) + hi(data[7]) / 10
    return [
        {"type": "speed", "current": speed, "average": average},
        {"type": "direction", "current": direction, "string": name},
        *_percentage_battery(data),
    ]


def _wgr918_anemometer(data: Bytes) -> list[Item]:
    direction = bcd(data[5]) * 10 + hi(data[4])
    index = int(direction / 22.5)
    return _wind(data, direction, WIND_DIRECTIONS[index] if index < 16 else "")


def _wtgr800_anemometer(data: Bytes) -> list[Item]:
    direction = hi(data[4]) % 16
    return _wind(data, direction * 22.5, WIND_DIRECTIONS[direction])


def _common_temp(data: Bytes) -> list[Item]:
    return [*_temperature(data), *_simple_battery(data)]


def _common_temphydro(data: Bytes) -> list[Item]:
    return [*_temperature(data), *_humidity(data), *_simple_battery(data)]


def _alt_temphydro(data: Bytes) -> list[Item]:
    return [*_temperature(data), *_humidity(data), *_percentage_battery(data)]


def _common_temphydrobaro(data: Bytes) -> list[Item]:
    return [
        *_temperature(data),
        *_humidity(data),
        *_pressure(data, lo(data[9])),
        *_simple_battery(data),
    ]


def _alt_temphydrobaro(data: Bytes) -> list[Item]:
    return [
        *_temperature(data),
        *_humidity(data),
        *_pressure(data, hi(data[9]), 856),
        *_percentage_battery(data),
    ]


def _datetime(data: Bytes) -> list[Item]:
    # FHEM does not store the date and time of the RTGR328N clock
    return []


def _common_rain(data: Bytes) -> list[Item]:
    rain = bcd(data[5]) * 10 + hi(data[4])
    total = lo(data[8]) * 1000 + bcd(data[7]) * 10 + hi(data[6])
    return [
        {"type": "rain", "current": rain},
        {"type": "train", "current": total},
        {"type": "flip", "current": lo(data[6])},
        *_simple_battery(data),
    ]


def _rain_pcr800(data: Bytes) -> list[Item]:
    rain = (lo(data[6]) * 10 + bcd(data[5]) / 10 + hi(data[4]) / 100) * 25.4
    total = (lo(data[9]) * 100 + bcd(data[8]) + bcd(data[7]) / 100 + hi(data[6]) / 1000) * 25.4
    return [
        {"type": "rain", "current": rain},
        {"type": "train", "current": total},
        *_simple_battery(data),
    ]


def _checksum(
    count: int, check: Callable[[Bytes], int], extra: Callable[[Bytes], int] | None = None
):
    def verify(data: Bytes) -> bool:
        total = nibble_sum(count, data) + (extra(data) if extra else 0) - 0xA
        return total & 0xFF == check(data)

    return verify


def _nibbles(low_byte: int) -> Callable[[Bytes], int]:
    return lambda data: hi(data[low_byte]) + (lo(data[low_byte + 1]) << 4)


CHECKSUMS = {
    1: _checksum(6, _nibbles(6), lambda data: lo(data[6])),
    2: _checksum(8, lambda data: data[8]),
    3: _checksum(11, lambda data: data[11]),
    4: _checksum(9, lambda data: data[9]),
    5: _checksum(10, lambda data: data[10]),
    "5plus": _checksum(10, lambda data: data[10]),
    "6plus": _checksum(8, _nibbles(8), lambda data: data[8] & 0x0F),
    7: _checksum(7, lambda data: data[7]),
    8: _checksum(9, _nibbles(9), lambda data: lo(data[9])),
    9: _checksum(6, _nibbles(6)),
}


def _key(sensor_type: int, bits: int) -> int:
    return (sensor_type << 8) + bits


TYPES: dict[int, tuple[str, Any, Callable[[Bytes], list[Item]]]] = {
    _key(0xFA28, 80): ("THGR810", 2, _common_temphydro),
    _key(0xFAB8, 80): ("WTGR800_T", 2, _alt_temphydro),
    _key(0x1A99, 88): ("WTGR800_A", 4, _wtgr800_anemometer),
    _key(0x1A89, 88): ("WGR800", 4, _wtgr800_anemometer),
    _key(0xDA78, 72): ("UVN800", 7, _uvn800),
    _key(0xEA7C, 120): ("UV138", 1, _uv138),
    _key(0xEA4C, 80): ("THWR288A", 1, _common_temp),
    _key(0xEA4C, 64): ("THN132N", 1, _common_temp),
    _key(0x9AEC, 104): ("RTGR328N", 3, _datetime),
    _key(0x9AEA, 104): ("RTGR328N", 3, _datetime),
    _key(0x1A2D, 80): ("THGR228N", 2, _common_temphydro),
    _key(0x1A3D, 80): ("THGR918", 2, _common_temphydro),
    _key(0x5A5D, 88): ("BTHR918", "5plus", _common_temphydrobaro),
    _key(0x5A6D, 88): ("BTHR918N", 5, _alt_temphydrobaro),
    _key(0x3A0D, 80): ("WGR918", 4, _wgr918_anemometer),
    _key(0x2A1D, 80): ("RGR918", "6plus", _common_rain),
    _key(0x0A4D, 80): ("THR128", 2, _common_temp),
    _key(0xCA2C, 80): ("THGR328N", 2, _common_temphydro),
    _key(0xCA2C, 120): ("THGR328N", 2, _common_temphydro),
    _key(0x0ACC, 80): ("RTGR328N", 2, _common_temphydro),
    _key(0x2A19, 92): ("PCR800", 8, _rain_pcr800),
    _key(0xCA48, 68): ("THWR800", 9, _common_temp),
    # Masked to ?adc because of the rolling code
    _key(0x0ADC, 64): ("RTHN318", 1, _common_temp),
}


def _lookup(sensor_type: int, bits: int) -> tuple[str, Any, Callable[[Bytes], list[Item]]] | None:
    key = _key(sensor_type, bits)
    return TYPES.get(key) or TYPES.get(key & 0xFFFFF)


def parse(message: Message) -> Reading | None:
    msg = message.dmsg
    if not MATCH.match(msg):
        return None
    try:
        raw = bytes.fromhex(msg if len(msg) % 2 == 0 else msg + "0")
    except ValueError:
        return None
    bits = raw[0]
    data = Bytes(raw[1:])
    if len(data) < 4:
        return None
    sensor_type = (data[0] << 8) + data[1]

    # Messages may carry up to two nibbles too many
    for _ in range(3):
        if rec := _lookup(sensor_type, bits):
            break
        bits -= 4
    else:
        return None

    part, checksum, method = rec
    if not CHECKSUMS[checksum](data):
        return None
    items = method(data)
    if not items:
        return None

    # FHEM defaults to long ids for Oregon sensors: model, rolling code and channel
    device = f"{part}_{data[3]:02x}"
    if hi(data[2]) > 0:
        device += f"_{hi(data[2])}"

    readings: dict[str, Any] = {}
    for item in items:
        typ = item["type"]
        if typ == "temp":
            readings["temperature"] = item["current"]
        elif typ in ("humidity", "battery", "batteryPercent", "batteryState"):
            readings[typ] = item["current"]
        elif typ == "pressure":
            readings["pressure"] = item["current"]
            readings["forecast"] = item["forecast"]
        elif typ == "speed":
            readings["wind_speed"] = item["current"]
            readings["wind_avspeed"] = item["average"]
        elif typ == "direction":
            readings["wind_dir"] = f"{perl_str(item['current'])} {item['string']}"
            readings["windDirectionDegree"] = item["current"]
        elif typ == "rain":
            readings["rain_rate"] = item["current"]
        elif typ == "train":
            readings["rain_total"] = item["current"]
        elif typ == "flip":
            readings["rain_flip"] = item["current"]
        elif typ == "uv":
            readings["uv_val"] = item["current"]
            readings["uv_risk"] = item["risk"]
    return Reading(device=device, model=part, readings=readings)
