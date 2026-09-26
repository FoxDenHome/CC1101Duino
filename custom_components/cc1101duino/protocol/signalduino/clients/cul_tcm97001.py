"""Port of FHEM's 14_CUL_TCM97001.pm: TCM, Prologue, Mebus, Auriol, GT-WT-02 and more (``s...``).

FHEM tells these sensors apart by trying one decoder after another, guided by the model
attribute of the device the sensor was autocreated as. Without that state, the model is
found the way FHEM autocreates a device (the first decoder that accepts the message wins)
and the readings are then decoded as FHEM does for a device of that model.
"""

from __future__ import annotations

from typing import Any

from .. import Message
from .base import Reading, hex_to_bits, perl_num, perl_round

WIND_DIRECTIONS_8 = ("N", "NE", "E", "SE", "S", "SW", "W", "NW", "N")
TRENDS = ("consistent", "falling", "rising", "unknown")


class _Undefined(Exception):
    """FHEM's goto UNDEFINED_MODEL: a new device of this model would be created."""

    def __init__(self, model: str) -> None:
        self.model = model


def _nibbles_reversed(msg: str) -> list[int]:
    """Every nibble with its bits in reverse order."""
    return [int(f"{int(char, 16):04b}"[::-1], 2) for char in msg]


def _check_values(temp: Any, hum: Any = None) -> bool:
    if temp is None:
        return False
    if not -30 <= perl_num(temp) <= 60:
        return False
    return hum is None or 0 <= perl_num(hum) <= 100


def _crc_w174(msg: str) -> bool:
    r = _nibbles_reversed(msg)
    return len(r) > 8 and (7 + sum(r[0:8])) & 15 == r[8]


def _crc_w155(msg: str) -> bool:
    r = _nibbles_reversed(msg)
    return len(r) > 8 and (15 - sum(r[0:8])) & 15 == r[8]


def _crc4(msg: str) -> bool:
    if len(msg) < 9:
        return False
    crc = 0
    for char in msg[0:8]:
        crc ^= int(char, 16)
    return crc == int(msg[8], 16)


def _is_rain(msg: str) -> bool:
    return len(msg) >= 9 and not int(msg[2], 16) & 1


def _crc_kw9010(msg: str) -> bool:
    r = _nibbles_reversed(msg)
    return len(r) > 8 and sum(r[0:8]) & 15 == r[8]


def _crc_mebus(msg: str) -> bool:
    n = [int(char, 16) for char in msg[0:7]]
    return (sum(n[1:7]) - 1) & 15 == n[0]


def _crc_gtwt02(msg: str) -> bool:
    n = [int(char, 16) for char in msg[0:8]]
    check = (int(msg[7:10], 16) & 0x1F8) >> 3
    return (sum(n[0:7]) + (n[7] & 0xE)) % 64 == check


def _crc_type1(msg: str) -> bool:
    n = [int(char, 16) for char in msg[0:8]]
    return sum(n) == (int(msg[7:10], 16) & 0x1F8) >> 3


def _crc_sduino_id33(bits: str) -> bool:
    crc = 0
    for i in range(34):
        if int(bits[i]) == (crc & 1):
            crc >>= 1
        else:
            crc = (crc >> 1) ^ 12
    crc ^= int(bits[34:38][::-1], 2)
    return crc == int(bits[38:42][::-1], 2)


def _signed(value: int, mask: int, negative: bool) -> int:
    """The sensors' two's complement: negate the masked complement plus one."""
    return -((~value & mask) + 1) if negative else value


class _Decoder:
    """One run through CUL_TCM97001_Parse for a message."""

    def __init__(self, msg: str, readed_model: str, device_exists: bool) -> None:
        self.msg = msg
        self.a = msg
        self.readed_model = readed_model
        self.device_exists = device_exists
        self.package_ok = False
        self.model = "Unknown"
        self.temp: Any = None
        self.humidity: Any = None
        self.channel: Any = None
        self.batbit: Any = None
        self.mode: Any = None
        self.trend: Any = None
        self.rain: Any = 0
        self.wind_speed: Any = 0
        self.wind_gust: Any = 0
        self.wind_direction: Any = 0
        self.wind_direction_degree: Any = 0
        self.wind_direction_text = "N"
        self.has = dict.fromkeys(
            ("humidity", "batcheck", "trend", "channel", "mode", "windspeed", "wind", "rain"),
            False,
        )

    def h(self, *indexes: int) -> int:
        return int("".join(self.a[i] for i in indexes), 16)

    def found(self, model: str, **flags: bool) -> None:
        """A decoder accepted the message as the given model."""
        self.model = model
        if not self.device_exists:
            raise _Undefined(model)
        for flag, value in flags.items():
            self.has[flag] = value
        self.package_ok = True
        self.readed_model = model

    def is_model(self, *models: str) -> bool:
        return self.readed_model in ("Unknown", *models)

    def run(self) -> None:
        length = len(self.msg)
        if length == 8:
            self._length_8()
        elif length == 10:
            self._length_10()
        elif length == 12:
            self._length_12()
        elif length == 14:
            self._length_14()

    def _length_8(self) -> None:
        if self.readed_model in ("Unknown", "ABS700"):
            temp = (self.h(2, 3) & 0x7F) + self.h(5) / 10
            if self.h(2) & 0x8:
                temp = -temp
            self.temp = temp
            if _check_values(temp):
                self.batbit = (self.h(4) & 0x8) != 0x8
                self.mode = (self.h(4) & 0x4) >> 2
                self.found("ABS700", batcheck=True, mode=True)
        if self.readed_model in ("Unknown", "TCM97..."):
            temp = (self.h(3, 4, 5) >> 2) & 0xFFFF
            temp = _signed(temp, 0x3FF, self.h(2) & 0x3 == 0x3) / 10
            self.temp = temp
            if _check_values(temp):
                self.batbit = ~(self.h(2) & 0x4) & 0x1
                self.mode = self.h(5) & 0x1
                self.found("TCM97...", batcheck=True, mode=True)

    def _length_10(self) -> None:
        if _crc_mebus(self.msg) and self.is_model("Mebus"):
            temp = _signed(self.h(3, 4, 5) & 0x3FF, 0x3FF, self.h(3) & 0xC == 0xC) / 10
            self.temp = temp
            if _check_values(temp):
                self.batbit = (self.h(6) & 0x2) >> 1
                self.mode = self.h(6) & 0x1
                self.channel = (self.h(6) & 0xC) >> 2
                self.found("Mebus", mode=True, batcheck=True, channel=True)
        if not self.package_ok and self.readed_model in ("AURIOL", "Auriol_Z31743B", "Unknown"):
            check = True
            if self.readed_model == "Auriol_Z31743B":
                bits = hex_to_bits(self.msg)
                parity = 0
                for bit in bits[0:31]:
                    parity ^= int(bit)
                check = str(parity) == bits[31:32] and self.h(2) & 7 == 0
            temp = _signed(self.h(3, 4, 5) & 0x7FF, 0x7FF, self.h(3) & 0x8 == 0x8) / 10
            self.temp = temp
            if _check_values(temp) and check:
                self.batbit = (self.h(2) & 0x8) >> 3
                self.mode = (self.h(2) & 0x4) >> 2
                self.channel = 0
                self.trend = self.h(7) & 0x3
                model = "AURIOL" if self.readed_model == "Unknown" else self.readed_model
                extra = {"trend": True, "mode": True} if model == "AURIOL" else {}
                self.found(model, batcheck=True, **extra)

    def _length_12(self) -> None:  # noqa: C901 - one branch per sensor family, as in FHEM
        bits = hex_to_bits(self.msg)

        # Eurochron is only decoded here when the device already has that model; new ones
        # are passed on to SD_WS07 by SIGNALduino itself

        if _crc_w174(self.msg) and self.is_model("W174"):
            r = _nibbles_reversed(self.msg)
            if r[2] >> 1 == 3 and r[3] == 0x03:
                self.batbit = ~(r[2] & 0x1) & 0x1
                self.rain = (r[4] + r[5] * 16 + r[6] * 256 + r[7] * 4096) * 0.25
                self.found("W174", batcheck=True, rain=True)

        if _crc_w155(self.msg) and self.is_model("TCM21....", "W044", "W132"):
            r = _nibbles_reversed(self.msg)
            self.channel = int(bits[4:6], 2)
            self.has["channel"] = True
            self.batbit = 0 if bits[8] == "1" else 1
            self.has["batcheck"] = True
            model = self.model
            if bits[9:11] != "11":
                self.mode = bits[11]
                self.has["mode"] = True
                raw = r[3] + r[4] * 16 + r[5] * 256
                self.temp = -((~raw & 0x3FF) + 1) / 10 if r[5] > 3 else raw / 10
                self.humidity = f"{r[7]}{r[6]}"
                self.has["humidity"] = True
                model = "W044" if self.readed_model == "Unknown" else self.readed_model
                self.package_ok = True
            else:
                if self.h(3) == 0x8 and self.h(4) == 0 and self.h(5) == 0:
                    self.wind_speed = (r[6] + r[7] * 16) * 0.2
                    self.has["windspeed"] = True
                    model = "W132"
                if self.h(3) in (0xE, 0xF):
                    self.wind_gust = (r[6] + r[7] * 16) * 0.2
                    degree = (self.h(3) & 0x1) + r[4] * 2 + r[5] * 32
                    self.wind_direction_degree = degree
                    self.wind_direction = int(degree / 45)
                    self.wind_direction_text = WIND_DIRECTIONS_8[self.wind_direction]
                    self.has["wind"] = True
                    model = "W132"
                if self.h(3) == 0xC:
                    self.rain = (self.h(4) + self.h(5) + self.h(6) + self.h(7)) * 0.25
                    self.has["rain"] = True
                    model = "W174"
            # The channel flag is always set, so this always accepts the message
            self.found(model, batcheck=True)

        gtwt02 = _crc_gtwt02(self.msg)
        if (gtwt02 and self.is_model("GT_WT_02", "Type1")) or (
            _crc_type1(self.msg) and self.is_model("Type1", "GT_WT_02")
        ):
            temp = _signed(self.h(3, 4, 5) & 0x3FF, 0x3FF, self.h(3) & 0xC == 0xC) / 10
            humidity = min(max((self.h(6, 7) & 0x0FE) >> 1, 20), 100)
            self.temp, self.humidity = temp, humidity
            if _check_values(temp, humidity):
                self.channel = (self.h(2) & 0x3) + 1
                self.batbit = (self.h(2) & 0x8) != 0x8
                self.mode = (self.h(2) & 0x4) >> 2
                self.found(
                    "GT_WT_02" if gtwt02 else "Type1",
                    humidity=True,
                    batcheck=True,
                    channel=True,
                    mode=True,
                )

        if self.readed_model == "Prologue" or (self.h(0) == 0x9 and self.readed_model == "Unknown"):
            temp = _signed(self.h(4, 5, 6) & 0x3FFF, 0x3FF, self.h(4) & 0xC == 0xC) / 10
            humidity = None if self.h(7) == 0xC and self.h(8) == 0xC else self.h(7, 8)
            self.temp = temp
            if humidity is not None:
                self.humidity = humidity
            if _check_values(temp, humidity):
                self.channel = (self.h(3) & 0x3) + 1
                self.batbit = ~((self.h(3) & 0x8) >> 3) & 0x1
                self.mode = (self.h(3) & 0x4) >> 2
                self.found(
                    "Prologue",
                    **({"humidity": True} if humidity is not None and humidity >= 20 else {}),
                    batcheck=True,
                    mode=True,
                    channel=True,
                )

        if self.readed_model == "NC_WS" or (self.h(0) == 0x5 and self.readed_model == "Unknown"):
            temp = _signed(self.h(4, 5, 6) & 0x7FFF, 0x7FF, self.h(4) & 0x8 == 0x8) / 10
            humidity = self.h(7, 8) & 0x7F
            self.temp, self.humidity = temp, humidity
            if _check_values(temp, humidity):
                self.channel = (self.h(3) & 0x3) + 1
                self.batbit = (self.h(3) & 0x8) >> 3
                self.mode = (self.h(3) & 0x4) >> 2
                self.found("NC_WS", humidity=True, batcheck=True, mode=True, channel=True)

        if self.readed_model == "Rubicson" or (self.h(2) == 0x8 and self.readed_model == "Unknown"):
            temp = _signed(self.h(3, 4, 5) & 0x3FF, 0x3FF, self.h(3) & 0xC == 0xC) / 10
            self.temp = temp
            if _check_values(temp):
                self.channel = 0
                self.found("Rubicson")

        if _crc4(self.msg) and _is_rain(self.msg) and self.is_model("PFR_130"):
            temp = _signed(self.h(3, 4, 5) & 0x7FF, 0x7FF, self.h(3) & 0x8 == 0x8) / 10
            self.temp = temp
            if _check_values(temp):
                self.batbit = ~((self.h(2) & 0x8) >> 3) & 0x1
                self.mode = (self.h(2) & 0x4) >> 2
                self.trend = self.h(7) & 0x3
                self.found("PFR_130", batcheck=True, trend=False, mode=True)

        if _crc_kw9010(self.msg) and self.is_model("KW9010", "KW9015"):
            r = _nibbles_reversed(self.msg)
            raw = r[3] + r[4] * 16 + r[5] * 256
            temp = -((~raw & 0x3FF) + 1) / 10 if r[5] > 3 else raw / 10
            self.temp = temp
            rain_hum = r[7] * 16 + r[6]
            flags: dict[str, bool] = {}
            if self.readed_model == "Unknown":
                ok = _check_values(temp)
            elif self.readed_model == "KW9010":
                self.humidity = rain_hum - 156
                ok = _check_values(temp, self.humidity)
                if ok:
                    flags["humidity"] = True
            else:
                ok = _check_values(temp)
                if ok:
                    flags["rain"] = True
                    self.rain = rain_hum * 0.45
            if ok:
                self.batbit = ~((self.h(2) & 0x8) >> 3) & 0x1
                self.channel = (self.h(1) & 0xC) >> 2
                self.mode = self.h(2) & 0x1
                trend = (self.h(2) & 0x6) >> 1
                self.trend = trend ^ 3 if trend in (1, 2) else trend
                if self.readed_model == "Unknown":
                    model = "KW9010" if self.channel > 0 else "KW9015"
                else:
                    model = self.readed_model
                self.found(
                    model,
                    batcheck=True,
                    trend=True,
                    mode=True,
                    **({"channel": True} if self.channel > 0 else {}),
                    **flags,
                )

        if self.readed_model == "Auriol_IAN" or (
            self.h(7) < 10
            and self.h(8) < 10
            and 1 <= self.h(9) <= 3
            and self.readed_model == "Unknown"
        ):
            temp = perl_round((self.h(4, 5, 6) - 1220) * 5 / 90.0, 1)
            if self.h(7) < 10 and self.h(8) < 10:
                humidity: Any = perl_num(self.a[7]) * 10 + perl_num(self.a[8])
            else:
                humidity = 101
            self.temp, self.humidity = temp, humidity
            if _check_values(temp, humidity):
                self.batbit = ~((self.h(3) & 0x4) >> 2) & 0x1
                self.mode = (self.h(3) & 0x8) >> 3
                self.trend = self.h(3) & 0x3
                self.channel = self.h(9) & 0x3
                self.found(
                    "Auriol_IAN",
                    humidity=True,
                    batcheck=True,
                    channel=True,
                    mode=True,
                    trend=True,
                )

        if self.readed_model == "Mebus7312" or (
            self.h(6) == 0xF and self.readed_model == "Unknown"
        ):
            temp = self.h(3, 4, 5)
            if temp >= 3840:
                temp -= 4096
            temp /= 10
            humidity = self.h(7, 8)
            self.temp, self.humidity = temp, humidity
            if _check_values(temp, humidity):
                self.channel = (self.h(2) & 0x3) + 1
                self.batbit = (self.h(2) & 0x8) >> 3
                self.found(
                    "Mebus7312",
                    **({"humidity": True} if humidity > 0 else {}),
                    batcheck=True,
                    channel=True,
                )

        if self.readed_model in ("AURIOL", "Unknown"):
            temp = _signed(self.h(3, 4, 5) & 0x7FF, 0x7FF, self.h(3) & 0x8 == 0x8) / 10
            self.temp = temp
            if _check_values(temp):
                self.batbit = (self.h(2) & 0x8) >> 3
                self.mode = (self.h(2) & 0x4) >> 2
                self.channel = 0
                self.trend = self.h(7) & 0x3
                self.found("AURIOL", batcheck=True, trend=True, mode=True)

        if self.readed_model in ("TCM218943", "Unknown"):
            temp = ~(self.h(6, 7, 8) & 0x3FF) & 0x3FF
            temp = _signed(temp, 0x3FF, ~self.h(6) & 0xC == 0xC) / 10
            humidity = ~self.h(4, 5) & 0xFF
            self.temp, self.humidity = temp, humidity
            if _check_values(temp, humidity):
                self.batbit = (self.h(2) & 0x8) >> 3
                self.mode = ~(self.h(2) & 0x1) & 0x1
                self.channel = 0
                self.found(
                    "TCM218943",
                    **({"humidity": True} if humidity >= 20 else {}),
                    batcheck=True,
                    channel=False,
                    mode=True,
                )

    def _length_14(self) -> None:
        bits = hex_to_bits(self.msg)
        if _crc_sduino_id33(bits) and self.is_model("NX7674"):
            self.temp = (int(bits[22:26] + bits[18:22] + bits[14:18], 2) - 1220) * 5 / 90.0
            self.batbit = 1 if bits[35] == "0" else 0
            self.channel = 1 if bits[2] == "0" else 2
            trend = int(bits[36:38], 2)
            self.trend = trend ^ 3 if trend in (1, 2) else trend
            self.found("NX7674", batcheck=True, channel=True, trend=True)

    def readings(self) -> dict[str, Any]:
        readings: dict[str, Any] = {}
        has = self.has
        if has["rain"]:
            readings["israining"] = "yes" if self.rain != 0 else "no"
            readings["rain"] = self.rain
        if has["wind"]:
            readings["windGust"] = self.wind_gust
            readings["windDirection"] = self.wind_direction
            readings["windDirectionDegree"] = self.wind_direction_degree
            readings["windDirectionText"] = self.wind_direction_text
        if has["windspeed"]:
            readings["windSpeed"] = self.wind_speed
        if has["trend"] and self.trend is not None:
            readings["trend"] = TRENDS[self.trend]
        if has["batcheck"]:
            battery = "ok" if self.batbit is not None and int(self.batbit) == 1 else "low"
            readings["battery"] = battery
            readings["batteryState"] = battery
        if has["mode"]:
            readings["mode"] = "forced" if perl_num(self.mode) else "normal"
        if has["channel"]:
            readings["channel"] = self.channel
        if self.temp is not None:
            readings["temperature"] = f"{perl_num(self.temp):2.1f}"
        if has["humidity"]:
            readings["humidity"] = self.humidity
        return readings


def _decode(msg: str, readed_model: str, device_exists: bool) -> _Decoder:
    decoder = _Decoder(msg, readed_model, device_exists)
    decoder.run()
    return decoder


def detect_model(msg: str) -> str | None:
    """The model FHEM would autocreate a device for this message as."""
    try:
        _decode(msg, "Unknown", device_exists=False)
    except _Undefined as undefined:
        return undefined.model
    except (IndexError, ValueError):
        return None
    return None


def decode(msg: str, model: str) -> Reading | None:
    """Decode a message for a device of the given model."""
    try:
        decoder = _decode(msg, model, device_exists=True)
    except (IndexError, ValueError):
        return None
    if not decoder.package_ok:
        return None
    # FHEM's device code: the id is the first byte, or bytes 1-2 for Mebus and TCM97
    if len(msg) == 10 and decoder.model == "Mebus":
        sensor_id = int(msg[1:3], 16)
    else:
        sensor_id = int(msg[0:2], 16)
    return Reading(
        device=f"CUL_TCM97001_{sensor_id}", model=decoder.model, readings=decoder.readings()
    )


def parse(message: Message) -> Reading | None:
    msg = message.dmsg[1:]
    if not message.dmsg.startswith("s") or len(msg) < 5:
        return None
    model = detect_model(msg)
    if model is None:
        return None
    return decode(msg, model)
