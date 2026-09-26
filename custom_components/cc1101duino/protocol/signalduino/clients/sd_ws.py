"""Port of FHEM's 14_SD_WS.pm: various weather sensors (dmsg ``W<id>#<hex>``).

Only protocols received through ASK/OOK are ported; the xFSK ones (Bresser 5-in-1 etc.)
cannot be received by this firmware.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .. import Message
from .base import (
    WIND_DIRECTIONS,
    Reading,
    bin2dec,
    bin_num,
    crc8,
    hex_bytes,
    hex_to_bits,
    perl_num,
    perl_round,
    perl_str,
)


@dataclass
class Ctx:
    """The message as the decoder subs see it. Some prematch subs rewrite it in place."""

    raw: str
    bits: str
    msg: str


Field = Callable[[Ctx], Any]


def _match(pattern: str) -> Callable[[Ctx], bool]:
    regex = re.compile(pattern)
    return lambda ctx: regex.search(ctx.raw) is not None


def _always(ctx: Ctx) -> bool:
    return True


def _ok_low(bit_index: int, ok: str = "0") -> Field:
    return lambda ctx: "ok" if ctx.bits[bit_index : bit_index + 1] == ok else "low"


def _sendmode(bit_index: int) -> Field:
    return lambda ctx: "manual" if ctx.bits[bit_index : bit_index + 1] == "1" else "auto"


def _crc8_equals(start: int, length: int, check_at: int, init: int = 0) -> Callable[[Ctx], bool]:
    """Digest::CRC width 8 poly 0x31 over hex digits start..start+length."""

    def check(ctx: Ctx) -> bool:
        crc = crc8(hex_bytes(ctx.raw[start : start + length]), 0x31, init)
        return crc == int(ctx.raw[check_at:][:2] or "0", 16)

    return check


def _nibble_sums_ok(ctx: Ctx) -> bool:
    """Checksum of NC-3911 and TFA 30.3255.02."""
    n = [int(char, 16) for char in ctx.raw[:8]]
    if len(n) < 8:
        return False
    sum1 = n[0] + n[2] + n[4] + 6
    sum2 = n[1] + n[3] + n[5] + 6 + (sum1 >> 4)
    return (sum1 & 0x0F) == n[6] and (sum2 & 0x0F) == n[7]


def _winddir(direction: float) -> tuple[float, str]:
    return direction, WIND_DIRECTIONS[int(perl_round(direction / 22.5, 0))]


# 27: EuroChron EFTH-800, EFS-3110A


def _temp_27(ctx: Ctx) -> float:
    value = bin_num(ctx.bits, 18, 27)
    return (value - 1024) / 10.0 if ctx.bits[17] == "0" else value / 10.0


# 33: Conrad S522, renkforce E0001PA, TX-EZ6 and others


def _crc_33(ctx: Ctx) -> bool:
    crc = 0
    for i in range(34):
        if int(ctx.bits[i]) == (crc & 1):
            crc >>= 1
        else:
            crc = (crc >> 1) ^ 12
    crc ^= int(ctx.bits[34:38][::-1] or "0", 2)
    return crc == int(ctx.bits[38:42][::-1] or "0", 2)


# 37: Bresser 7009994


def _crc_37(ctx: Ctx) -> bool:
    total = sum(bin_num(ctx.bits, n, n + 7) for n in range(0, 32, 8)) & 0xFF
    return total == bin_num(ctx.bits, 32, 39)


def _temp_37(ctx: Ctx) -> str:
    temp_f = bin_num(ctx.bits, 12, 23) / 10 - 90
    return f"{(temp_f - 32) * 5 / 9 + 0.05:.1f}"


# 44: BresserTemeo


def _prematch_44(ctx: Ctx) -> bool:
    if len(ctx.bits) != 72:
        return False
    # An "x" after the protocol id marks a humidity above 79 %
    x_variant = re.match(r"^[WP]\d+x", ctx.msg) is not None
    ctx.bits = ("1" if x_variant else "0") + ctx.bits
    return True


BRESSER_TEMEO_FIELDS = ((0, 8), (10, 2), (9, 1), (13, 7), (12, 1), (21, 11))


def _crc_44(ctx: Ctx) -> bool:
    # Each field is repeated inverted 32 bits later
    for start, width in BRESSER_TEMEO_FIELDS:
        mask = (1 << width) - 1
        value = bin_num(ctx.bits, start, start + width - 1)
        check = bin_num(ctx.bits, start + 32, start + width + 31) ^ mask
        if value != check:
            return False
    return True


def _temp_44(ctx: Ctx) -> Any:
    digits = f"{bin_num(ctx.bits, 21, 23)}{bin_num(ctx.bits, 24, 27)}.{bin_num(ctx.bits, 28, 31)}"
    temp = float(digits)
    if temp > 60:
        return ""
    return -temp if ctx.bits[12] == "1" else temp


def _hum_44(ctx: Ctx) -> Any:
    hum = f"{bin_num(ctx.bits, 0, 3)}{bin_num(ctx.bits, 4, 7)}"
    if int(hum) < 1 or int(hum) > 100:
        return None
    return hum


# 48: TFA 30.3212


def _temp_48(ctx: Ctx) -> float:
    temp = bin_num(ctx.bits, 21, 31) / 10
    return -temp if ctx.bits[20] == "1" else temp


# 50: XT300


def _crc_50(ctx: Ctx) -> bool:
    total = sum(int(ctx.raw[i : i + 2], 16) for i in range(2, 10, 2)) & 0xFF
    return total == int(ctx.raw[10:12], 16)


# 53: Auriol IAN 314695


def _crc_53(ctx: Ctx) -> bool:
    total = sum(bin_num(ctx.bits, n, n + 3) for n in range(0, 36, 4)) & 0x3F
    return total == bin_num(ctx.bits, 36, 41)


def _temp_53(ctx: Ctx) -> float:
    value = bin_num(ctx.bits, 12, 23)
    return (value - 4096) / 10.0 if ctx.bits[12] == "1" else value / 10.0


# 54: TFA Drop 30.3233.01


def _lfsr_digest8_reflect(num_bytes: int, gen: int, key: int, raw: str) -> int:
    total = 0
    for k in range(num_bytes - 1, -1, -1):
        data = int(raw[k * 2 : k * 2 + 2] or "0", 16)
        for i in range(8):
            if (data >> i) & 1:
                total ^= key
            key = (key << 1) ^ gen if key & 0x80 else key << 1
    return total & 0xFF


def _rain_counter_54(ctx: Ctx) -> int:
    counter = bin_num(ctx.bits, 32, 39) + bin_num(ctx.bits, 48, 55) * 256
    # The counter starts at 65526 for 0 tips and rolls over at 65535
    return counter - 65526 if counter > 65525 else counter + 10


# 58: TFA 30.3208.02, FT007xx


def _crc_58(ctx: Ctx) -> bool:
    buff = ctx.raw[:10]
    mask = 0x7C
    checksum = 0x64
    for i in range(0, len(buff), 2):
        data = int(buff[i : i + 2], 16)
        for _ in range(8):
            bit = mask & 1
            mask = (mask >> 1) | ((mask << 7) & 0xFF)
            if bit:
                mask ^= 0x18
            if data & 0x80:
                checksum ^= mask & 0xFF
            data <<= 1
    return checksum == int(ctx.raw[10:12] or "0", 16)


# 64: WH2, WH2A


def _wh2_shift(raw: str) -> str:
    """Shift the message right by one bit, inserting a 1."""
    bits = ("1" + hex_to_bits(raw))[:-1]
    return f"{int(bits, 2):0{len(bits) // 4}X}"


def _prematch_64(ctx: Ctx) -> bool:
    typ = ctx.bits[:8]
    shifts = {"11111110": 1, "11111101": 2}.get(typ, 0)
    if shifts:
        for _ in range(shifts):
            ctx.raw = _wh2_shift(ctx.raw)
        ctx.msg = "W64#" + ctx.raw
        ctx.bits = hex_to_bits(ctx.raw)
        typ = ctx.bits[:8]
    return typ == "11111111"


def _crc_64(ctx: Ctx) -> bool:
    if crc8(hex_bytes(ctx.raw[2:12]), 0x31) != 0:
        return False
    if len(ctx.raw) == 14:  # WH2A has an additional checksum
        checksum = (1 + sum(int(ctx.raw[i : i + 2], 16) for i in range(0, 12, 2))) & 0xFF
        if checksum != int(ctx.raw[12:14], 16):
            return False
    return True


def _temp_64(ctx: Ctx) -> float:
    temp = bin2dec(ctx.bits[21:32]) / 10
    return -temp if bin2dec(ctx.bits[20:21]) else temp


# 84: Auriol IAN 283582


def _temp_signed_12(first: int) -> Field:
    def temp(ctx: Ctx) -> float:
        raw = bin_num(ctx.bits, first, first + 11)
        if raw > 1023:
            raw -= 4096
        return raw / 10.0

    return temp


# 85: TFA 30.3222.02, TFA 30.3251.10, LaCrosse TX141W


def _if_type_85(typ: str, field: Field) -> Field:
    return lambda ctx: field(ctx) if ctx.bits[30:32] == typ else None


# 94: Atech


def _id_94(ctx: Ctx) -> str:
    # The sensor sends 0 as "0" and 1 as "110"
    ctx.bits = ctx.bits.replace("110", "1")
    return f"{bin2dec(ctx.bits[:8]):02X}"


def _temp_94(ctx: Ctx) -> float | None:
    digits = [bin_num(ctx.bits, i, i + 3) for i in (12, 16, 20)]
    if any(digit > 9 for digit in digits):
        return None
    sign = -1.0 if ctx.bits[10:11] == "1" else 1.0
    return (digits[0] * 10 + digits[1] + digits[2] / 10) * sign


# 106: GT-TMBBQ-01


def _temp_106(ctx: Ctx) -> str:
    temp_f = bin_num(ctx.bits, 8, 21) / 20 - 90
    return perl_round((temp_f - 32) * 5 / 9, 1)


# 110: ADE WS1907


def _rain_counter_110(ctx: Ctx) -> int:
    counter = bin_num(ctx.bits, 32, 39) * 256 + bin_num(ctx.bits, 24, 31)
    return counter - 65526 if counter > 65525 else counter + 10


def _byte_sum_ok(length: int, check_at: int, start: int = 0) -> Callable[[Ctx], bool]:
    def check(ctx: Ctx) -> bool:
        total = start + sum(bin_num(ctx.bits, n, n + 7) for n in range(0, length, 8))
        return total & 0xFF == bin_num(ctx.bits, check_at, check_at + 7)

    return check


# 111: TS-FT002


def _rev_nibble(ctx: Ctx, start: int) -> int:
    return bin2dec(ctx.bits[start : start + 4][::-1])


def _crc_111(ctx: Ctx) -> bool:
    xor = 0
    for n in range(0, 72, 8):
        xor ^= bin_num(ctx.bits, n, n + 7)
    return xor == 0


# 113: GFGT 433 B1


def _temp_113(high: int, low: int) -> Field:
    def temp(ctx: Ctx) -> str:
        temp_f = bin_num(ctx.bits, high, high + 1) * 256 + bin_num(ctx.bits, low, low + 7) - 90
        return perl_round((temp_f - 32) * 5 / 9, 0)

    return temp


# 120: TFA 35.1077.54.S2


def _weather_120(field: Field) -> Field:
    return lambda ctx: None if ctx.bits[19:20] == "1" else field(ctx)


def _dcf_120(ctx: Ctx) -> str | None:
    if ctx.bits[19:20] == "0":
        return None
    b = ctx.bits
    return (
        f"20{bin_num(b, 47, 50)}{bin_num(b, 51, 54)}-"
        f"{b[58:59]}{bin_num(b, 59, 62)}-"
        f"{bin_num(b, 65, 66)}{bin_num(b, 67, 70)} "
        f"{bin_num(b, 25, 26)}{bin_num(b, 27, 30)}:"
        f"{bin_num(b, 32, 34)}{bin_num(b, 35, 38)}:"
        f"{bin_num(b, 40, 42)}{bin_num(b, 43, 46)}"
    )


def _crc_120(ctx: Ctx) -> bool:
    return crc8(hex_bytes(ctx.raw[2:]), 0x31) == 0


# 122: TM40


def _probe_122(flags_at: int, first: int) -> Field:
    def temp(ctx: Ctx) -> float | None:
        if ctx.bits[flags_at : flags_at + 3] != "000":  # probe not connected
            return None
        return bin_num(ctx.bits, first, first + 15) / 10

    return temp


# 129: Sainlogic FT-0835 and others


def _winddir_129(ctx: Ctx) -> tuple[float, str]:
    return _winddir(int(ctx.bits[29]) * 256 + bin_num(ctx.bits, 48, 55))


def _brightness_129(ctx: Ctx) -> int | None:
    if ctx.raw[28:30] == "FB":
        return None
    return int(ctx.bits[72]) * 65536 + bin_num(ctx.bits, 96, 111)


def _uv_129(ctx: Ctx) -> float | None:
    if ctx.raw[28:30] == "FB":
        return None
    return 0.1 * int(ctx.raw[28:30], 16)


def _crc_129(ctx: Ctx) -> bool:
    return crc8(hex_bytes(ctx.raw[4:32]), 0x31, 0xC0) == 0


# 136: EMOS E06016


def _dcf_136(ctx: Ctx) -> str:
    b = ctx.bits
    return (
        f"{bin_num(b, 17, 23) + 2000}-{bin_num(b, 24, 27):02d}-{bin_num(b, 28, 32):02d} "
        f"{bin_num(b, 33, 37):02d}:{bin_num(b, 38, 43):02d}:{bin_num(b, 44, 49):02d} "
        + ("CET" if b[86:87] == "0" else "CEST")
    )


TREND = ("consistent", "rising", "falling", "unknown")


DECODERS: dict[str, dict[str, Any]] = {
    "27": {
        "sensortype": "EFTH-800, EFS-3110A",
        "model": "SD_WS_27_TH",
        "prematch": _match(r"^[0-9A-F]{7}[08][0-9]{2}[0-9A-F]{2}$"),
        "channel": lambda ctx: bin_num(ctx.bits, 1, 3) + 1,
        "id": lambda ctx: ctx.raw[1:4],
        "bat": _ok_low(16),
        "temp": _temp_27,
        "hum": lambda ctx: bin_num(ctx.bits, 32, 35) * 10 + bin_num(ctx.bits, 36, 39),
        "crcok": _crc8_equals(0, 10, -2),
    },
    "33": {
        "sensortype": "E0001PA, s014, S522, TCM, TFA 30.3200, TX-EZ6",
        "model": "SD_WS_33_T",
        "prematch": _match(r"^[0-9A-F]{11}$"),
        "crcok": _crc_33,
        "id": lambda ctx: bin_num(ctx.bits, 0, 9),
        "temp": lambda ctx: perl_round(
            (
                bin_num(ctx.bits, 22, 25) * 256
                + bin_num(ctx.bits, 18, 21) * 16
                + bin_num(ctx.bits, 14, 17)
                - 1220
            )
            * 5
            / 90.0,
            1,
        ),
        "hum": lambda ctx: bin_num(ctx.bits, 30, 33) * 16 + bin_num(ctx.bits, 26, 29),
        "channel": lambda ctx: bin_num(ctx.bits, 12, 13) + 1,
        "bat": _ok_low(34),
    },
    "37": {
        "sensortype": "Bresser 7009994",
        "model": "SD_WS37_TH",
        "prematch": _match(r"^[0-9A-F]{2}[1235679ABDEF]{1}[0-9A-F]{3}[0-7][0-9A-F]{3,4}$"),
        "sendmode": _sendmode(9),
        "crcok": _crc_37,
        "temp": _temp_37,
        "hum": lambda ctx: bin_num(ctx.bits, 24, 31),
        "channel": lambda ctx: bin_num(ctx.bits, 10, 11),
        "id": lambda ctx: ctx.raw[0:2],
        "bat": _ok_low(8),
    },
    "38": {
        "sensortype": "NC-3911",
        "model": "SD_WS_38_T",
        "prematch": _match(r"^[0-9A-F]{9}$"),
        "id": lambda ctx: ctx.raw[0:2],
        "bat": _ok_low(8, ok="1"),
        "beep": lambda ctx: "on" if ctx.bits[9] == "1" else "off",
        "channel": lambda ctx: bin_num(ctx.bits, 10, 11),
        "temp": lambda ctx: (bin_num(ctx.bits, 12, 23) - 500) / 10.0,
        "crcok": _nibble_sums_ok,
    },
    "44": {
        "sensortype": "BresserTemeo",
        "model": "BresserTemeo",
        "prematch": _prematch_44,
        "crcok": _crc_44,
        "id": lambda ctx: bin_num(ctx.bits, 13, 19),
        "temp": _temp_44,
        "channel": lambda ctx: bin_num(ctx.bits, 10, 11),
        "bat": lambda ctx: "ok" if ctx.bits[9] == "0" else "low",
        "hum": _hum_44,
    },
    "48": {
        "sensortype": "Temperature transmitter",
        "model": "SD_WS_48_T",
        "modelStat": lambda ctx: "TFA 30.3212",
        "prematch": _match(r"^FF4[0-9A-F]{5}FF[0-9A-F]{2}"),
        "id": lambda ctx: ctx.raw[3:5],
        "temp": _temp_48,
        "crcok": lambda ctx: crc8(hex_bytes(ctx.raw[0:12]), 0x31, 0xFF) == 0,
    },
    "50": {
        "sensortype": "XT300",
        "model": "SD_WS_50_SM",
        "prematch": _match(r"^FF5[0-9A-F]{5}FF[0-9A-F]{2}"),
        "crcok": _crc_50,
        "id": lambda ctx: int(ctx.raw[2:4], 16) & 0x03,
        "temp": lambda ctx: int(ctx.raw[6:8], 16) - 40,
        "hum": lambda ctx: int(ctx.raw[4:6], 16),
        "channel": lambda ctx: bin_num(ctx.bits, 12, 15) & 0x03,
    },
    "51": {
        "sensortype": "Auriol IAN 275901, IAN 114324, IAN 60107",
        "model": "SD_WS_51_TH",
        "prematch": _match(r"^[0-9A-F]{9}[1-3]$"),
        "crcok": _always,
        "id": lambda ctx: ctx.raw[0:2],
        "sendmode": _sendmode(12),
        "bat": lambda ctx: "low" if ctx.bits[13] == "1" else "ok",
        "trend": lambda ctx: TREND[bin_num(ctx.bits, 14, 15)],
        "temp": lambda ctx: perl_round((bin_num(ctx.bits, 16, 27) - 1220) * 5 / 90.0, 1),
        "hum": lambda ctx: bin_num(ctx.bits, 28, 31) * 10 + bin_num(ctx.bits, 32, 35),
        "channel": lambda ctx: bin_num(ctx.bits, 38, 39),
    },
    "53": {
        "sensortype": "Auriol IAN 314695",
        "model": "SD_WS_53_TH",
        "prematch": _match(r"^[0-9A-F]{8}4[0-9A-F]{2}$"),
        "crcok": _crc_53,
        "id": lambda ctx: ctx.raw[0:2],
        "bat": lambda ctx: "low" if ctx.bits[8] == "1" else "ok",
        "channel": lambda ctx: bin_num(ctx.bits, 10, 11) + 1,
        "temp": _temp_53,
        "hum": lambda ctx: bin_num(ctx.bits, 24, 30),
    },
    "54": {
        "sensortype": "TFA 30.3233.01",
        "model": "SD_WS_54_R",
        "prematch": _match(r"^3[0-9A-F]{9}AA[0-9A-F]{4,5}$"),
        "id": lambda ctx: ctx.raw[1:6],
        "bat": _ok_low(24),
        "batChange": lambda ctx: ctx.bits[25],
        "sendCounter": lambda ctx: bin_num(ctx.bits, 28, 30),
        "rawRainCounter": _rain_counter_54,
        "rain_total": lambda ctx: _rain_counter_54(ctx) * 0.254,
        "crcok": lambda ctx: (
            _lfsr_digest8_reflect(7, 0x31, 0xF4, ctx.raw) == int(ctx.raw[14:16], 16)
        ),
    },
    "58": {
        "sensortype": "TFA 30.3208.02, FT007xx",
        "model": "SD_WS_58_T",
        "prematch": _match(r"^4[5|6][0-9A-F]{11}"),
        "crcok": _crc_58,
        "id": lambda ctx: bin_num(ctx.bits, 8, 15),
        "bat": lambda ctx: "low" if bin_num(ctx.bits, 16) == 1 else "ok",
        "channel": lambda ctx: bin_num(ctx.bits, 17, 19) + 1,
        "temp": lambda ctx: perl_round((bin_num(ctx.bits, 20, 31) - 720) * 0.0556, 1),
        "hum": lambda ctx: bin_num(ctx.bits, 32, 39) if ctx.raw[1:2] == "5" else 0,
    },
    "64": {
        "sensortype": "WH2, WH2A",
        "model": "SD_WS_WH2",
        "prematch": _prematch_64,
        "modelStat": lambda ctx: "WH2A" if len(ctx.raw) == 14 else "WH2",
        "crcok": _crc_64,
        "id": lambda ctx: f"{bin2dec(ctx.bits[12:18]):03X}",
        "bat": lambda ctx: "low" if ctx.bits[32:33] == "1" else "ok",
        "temp": _temp_64,
        "hum": lambda ctx: bin2dec(ctx.bits[32:40]),
        "channel": lambda ctx: 0,
    },
    "71": {
        "sensortype": "PV-8644",
        "model": "SD_WS71_T",
        "prematch": _match(r"^5[A-F0-9]{6}F[A-F0-9]{2}"),
        "crcok": _always,
        "id": lambda ctx: bin_num(ctx.bits, 4, 11),
        "temp": lambda ctx: (bin_num(ctx.bits, 12, 23) - 2448) / 10,
        "channel": lambda ctx: bin_num(ctx.bits, 26, 27),
    },
    "84": {
        "sensortype": "Auriol IAN 283582, TV-4848",
        "model": "SD_WS_84_TH",
        "prematch": _match(r"^[0-9A-F]{4}[01245689ACDE]{1}[0-9A-F]{5,6}$"),
        "id": lambda ctx: bin_num(ctx.bits, 0, 7),
        "hum": lambda ctx: bin_num(ctx.bits, 8, 15),
        "bat": _ok_low(16),
        "sendmode": _sendmode(17),
        "channel": lambda ctx: bin_num(ctx.bits, 18, 19) + 1,
        "temp": _temp_signed_12(20),
        "crcok": _always,
    },
    "85": {
        "sensortype": "TFA 30.3222.02, TFA 30.3251.10, LaCrosse TX141W",
        "model": "SD_WS_85_THW",
        "prematch": _match(r"^[0-9A-F]{16}"),
        "id": lambda ctx: ctx.raw[1:6],
        "bat": _ok_low(24),
        "channel": lambda ctx: bin_num(ctx.bits, 26, 27) + 1,
        "temp": _if_type_85("01", lambda ctx: (bin_num(ctx.bits, 32, 43) - 500) / 10.0),
        "hum": _if_type_85("01", lambda ctx: bin_num(ctx.bits, 48, 55)),
        "windspeed": _if_type_85("10", lambda ctx: bin_num(ctx.bits, 32, 43) / 10.0),
        # Wind direction is only sent by the TFA 30.3251.10, which FHEM only reports when
        # the device's model attribute says so
        "crcok": _crc8_equals(0, 14, 14),
    },
    "89": {
        "sensortype": "TFA 30.3221.02",
        "model": "SD_WS_89_TH",
        "prematch": _match(r"^[0-9A-F]{2}[01245689ACDE]{1}[0-9A-F]{7}$"),
        "id": lambda ctx: ctx.raw[0:2],
        "bat": _ok_low(8),
        "sendmode": _sendmode(9),
        "channel": lambda ctx: bin_num(ctx.bits, 10, 11) + 1,
        "temp": lambda ctx: (bin_num(ctx.bits, 12, 23) - 500) / 10.0,
        "hum": lambda ctx: bin_num(ctx.bits, 24, 31),
        "crcok": _always,
    },
    "94": {
        "sensortype": "Atech",
        "model": "SD_WS_94_T",
        "prematch": _always,
        "id": _id_94,
        "temp": _temp_94,
        "crcok": _always,
    },
    "106": {
        "sensortype": "GT-TMBBQ-01",
        "model": "SD_WS_106_T",
        "prematch": _always,
        "id": lambda ctx: ctx.raw[0:2],
        "temp": _temp_106,
        "crcok": _always,
    },
    "110": {
        "sensortype": "ADE WS1907",
        "model": "SD_WS_110_TR",
        "prematch": _always,
        "id": lambda ctx: ctx.raw[0:4],
        "bat": _ok_low(16),
        "batChange": lambda ctx: ctx.bits[17],
        "sendCounter": lambda ctx: bin_num(ctx.bits, 20, 22),
        "rawRainCounter": _rain_counter_110,
        "rain": lambda ctx: _rain_counter_110(ctx) * 0.1,
        "temp": lambda ctx: perl_round(
            (bin_num(ctx.bits, 48, 55) * 256 + bin_num(ctx.bits, 40, 47) - 1220) * 5 / 90.0, 1
        ),
        "crcok": _byte_sum_ok(56, 56),
    },
    "111": {
        "sensortype": "TS-FT002",
        "model": "SD_WS_111_TL",
        "prematch": _match(r"^5F[0-9A-F]{2}88[0-9A-F]{12}"),
        "id": lambda ctx: ctx.raw[2:4],
        "distance": lambda ctx: (
            _rev_nibble(ctx, 24) * 16 + _rev_nibble(ctx, 28) * 256 + _rev_nibble(ctx, 32)
        ),
        "temp": lambda ctx: (
            (_rev_nibble(ctx, 48) * 16 + _rev_nibble(ctx, 52) * 256 + _rev_nibble(ctx, 40) - 400)
            / 10
        ),
        "crcok": _crc_111,
    },
    "113": {
        "sensortype": "GFGT_433_B1",
        "model": "SD_WS_113_T",
        "prematch": _always,
        "id": lambda ctx: ctx.raw[0:2],
        "temp": _temp_113(12, 16),
        "temp2": _temp_113(14, 24),
        "crcok": _always,
    },
    "120": {
        "sensortype": "TFA_35.1077",
        "model": "SD_WS_120",
        "prematch": _always,
        "id": lambda ctx: bin_num(ctx.bits, 11, 18),
        "bat": _ok_low(20),
        "temp": _weather_120(lambda ctx: bin_num(ctx.bits, 21, 30) * 0.1 - 40),
        "hum": _weather_120(lambda ctx: bin_num(ctx.bits, 31, 38)),
        "windspeed": _weather_120(lambda ctx: perl_round(bin_num(ctx.bits, 39, 46) / 3.0, 1)),
        "windgust": _weather_120(lambda ctx: perl_round(bin_num(ctx.bits, 47, 54) / 3.0, 1)),
        "rawRainCounter": _weather_120(lambda ctx: bin_num(ctx.bits, 55, 70)),
        "rain": _weather_120(lambda ctx: bin_num(ctx.bits, 55, 70) * 0.3),
        "dcf": _dcf_120,
        "crcok": _crc_120,
    },
    "122": {
        "sensortype": "TM40",
        "model": "SD_WS_122_T",
        "prematch": _always,
        "id": lambda ctx: ctx.raw[0:4],
        "temp4": _probe_122(81, 16),
        "temp3": _probe_122(85, 32),
        "temp2": _probe_122(89, 48),
        "temp": _probe_122(93, 64),
        "bat": _ok_low(88),
        "transmitter": lambda ctx: "on" if ctx.bits[92:93] == "0" else "off",
        "crcok": _always,
    },
    "129": {
        "sensortype": "FT-0835, FT0300, FT-0310, FT020T, WS019T",
        "model": "SD_WS_129",
        "prematch": _match(r"^FFD4"),
        "id": lambda ctx: ctx.raw[5:7],
        "bat": _ok_low(28),
        "windspeed": lambda ctx: perl_round(
            (int(ctx.bits[31]) * 256 + bin_num(ctx.bits, 32, 39)) / 10.0, 1
        ),
        "windgust": lambda ctx: perl_round(
            (int(ctx.bits[30]) * 256 + bin_num(ctx.bits, 40, 47)) / 10.0, 1
        ),
        "winddir": _winddir_129,
        "rain": lambda ctx: 0.1 * int(ctx.raw[14:18], 16),
        "temp": lambda ctx: perl_round((bin_num(ctx.bits, 76, 87) - 320 - 400) * 5 / 90.0, 1),
        "hum": lambda ctx: bin_num(ctx.bits, 88, 95),
        "brightness": _brightness_129,
        "uv": _uv_129,
        "crcok": _crc_129,
    },
    "135": {
        "sensortype": "TFA 30.3255.02",
        "model": "SD_WS_135_T",
        "prematch": _match(r"^[0-9A-F]{8,9}$"),
        "id": lambda ctx: ctx.raw[0:2],
        "bat": _ok_low(8, ok="1"),
        "sendmode": _sendmode(9),
        "channel": lambda ctx: bin_num(ctx.bits, 10, 11),
        "temp": lambda ctx: (bin_num(ctx.bits, 12, 23) - 500) / 10.0,
        "crcok": _nibble_sums_ok,
    },
    "136": {
        "sensortype": "EMOS E06016 wind",
        "model": "SD_WS_136_THW",
        "prematch": _match(r"^[0-9A-F]{26}$"),
        "id": lambda ctx: ctx.raw[2:4],
        "dcfStatus": lambda ctx: "ok" if ctx.bits[16] == "1" else "off",
        "dcf": _dcf_136,
        "channel": lambda ctx: bin_num(ctx.bits, 50, 51) + 1,
        "temp": _temp_signed_12(52),
        "hum": lambda ctx: bin_num(ctx.bits, 65, 71),
        "windspeed": lambda ctx: perl_round(bin_num(ctx.bits, 72, 79) * 0.295, 1),
        "winddir": lambda ctx: (
            bin_num(ctx.bits, 80, 83) * 22.5,
            WIND_DIRECTIONS[bin_num(ctx.bits, 80, 83)],
        ),
        "bat": _ok_low(85),
        "crcok": _byte_sum_ok(88, 88, start=170 + 165),
        "count": lambda ctx: bin_num(ctx.bits, 96, 103),
    },
}

# The order SD_WS_Parse calls the decoder subs in; some rewrite the bits for later ones
FIELD_ORDER = (
    "id",
    "temp",
    "temp2",
    "temp3",
    "temp4",
    "hum",
    "windspeed",
    "winddir",
    "windgust",
    "channel",
    "modelStat",
    "bat",
    "batVoltage",
    "batChange",
    "batteryPercent",
    "rawRainCounter",
    "rain",
    "rain_total",
    "sendCounter",
    "beep",
    "adc",
    "sendmode",
    "trend",
    "distance",
    "count",
    "identified",
    "uv",
    "brightness",
    "transmitter",
    "dcf",
    "dcfStatus",
)

# Protocols whose temperature may exceed the usual -30..70 °C (barbecue thermometers)
BBQ_PROTOCOLS = ("106", "113", "122")

# FHEM reading names, in the order SD_WS_Parse writes them, for the simple decoder fields
READINGS = (
    ("windspeed", "windSpeed"),
    ("windgust", "windGust"),
    ("bat", "batteryState"),
    ("batVoltage", "batteryVoltage"),
    ("batteryPercent", "batteryPercent"),
    ("batChange", "batteryChanged"),
    ("channel", "channel"),
    ("trend", "trend"),
    ("sendmode", "sendmode"),
    ("beep", "beep"),
    ("adc", "adc"),
    ("rain", "rain"),
    ("rawRainCounter", "rawRainCounter"),
    ("rain_total", "rain_total"),
    ("sendCounter", "sendCounter"),
    ("distance", "distance"),
    ("count", "count"),
    ("identified", "identified"),
    ("uv", "uv"),
    ("brightness", "brightness"),
    ("transmitter", "transmitter"),
    ("dcf", "dcf"),
    ("dcfStatus", "dcfStatus"),
)


def parse(message: Message) -> Reading | None:
    """SD_WS_Parse, without FHEM's comparison against the previous reading."""
    prefix, _, raw = message.dmsg.partition("#")
    protocol = re.sub(r"^[WP](\d+)x?", r"\1", prefix)
    decoder = DECODERS.get(protocol)
    if decoder is None:
        return None

    ctx = Ctx(raw, hex_to_bits(raw), message.dmsg)
    try:
        if not decoder["prematch"](ctx) or not decoder["crcok"](ctx):
            return None
        values = {key: decoder[key](ctx) for key in FIELD_ORDER if key in decoder}
    except (IndexError, ValueError):
        return None

    model = decoder["model"]
    hum = values.get("hum")
    if model in ("SD_WS_33_T", "SD_WS_58_T") and perl_num(hum) != 0:
        model += "H"

    channel = values.get("channel")
    device = model if channel is None else f"{model}_{perl_str(channel)}"

    temp = values.get("temp")
    if temp is not None and not -30 <= perl_num(temp) <= 70 and protocol not in BBQ_PROTOCOLS:
        return None
    if hum is not None and perl_num(hum) > 100:
        return None

    readings: dict[str, Any] = {}
    for key, name in (("temp", "temperature"), ("temp2", "temperature2")):
        value = values.get(key)
        if value is not None and (-60 < perl_num(value) < 70 or protocol in BBQ_PROTOCOLS):
            readings[name] = value
    for key, name in (("temp3", "temperature3"), ("temp4", "temperature4")):
        value = values.get(key)
        if value is not None and (-60 < perl_num(value) < 70 or protocol == "122"):
            readings[name] = value
    if hum is not None and 0 < perl_num(hum) < 100:
        readings["humidity"] = hum

    winddir = values.pop("winddir", None)
    if winddir is not None:
        readings["windDirectionDegree"], readings["windDirectionText"] = winddir

    for key, name in READINGS:
        value = values.get(key)
        if value is None:
            continue
        if key in ("bat", "channel", "trend", "sendmode") and perl_str(value) == "":
            continue
        readings[name] = value

    readings["type"] = decoder["sensortype"]
    readings["model"] = values.get("modelStat", model)

    return Reading(device=device, model=decoder["sensortype"], readings=readings)
