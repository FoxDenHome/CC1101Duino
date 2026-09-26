"""Port of FHEM's 14_CUL_WS.pm: ELV S300 / WS300 / WS7000 sensors (dmsg ``K...``).

The values are decimal digits of the message joined into strings, so Perl's numeric
conversion of those strings is kept.
"""

from __future__ import annotations

import re
from typing import Any

from .. import Message
from .base import Reading, perl_num

MATCH = re.compile(r"^K[A-Fa-f0-9]{5,}")


def _num(*digits: str) -> float:
    return perl_num("".join(digits))


def parse(message: Message) -> Reading | None:
    msg = message.dmsg
    if not MATCH.match(msg):
        return None
    a = list(msg)
    first = int(a[1], 16)
    code = (first & 7) + 1
    typ = int(a[2], 16) & 7
    sign = -1 if first & 8 else 1
    readings: dict[str, Any] = {}
    devtype = "unknown"
    family = "unknown"
    n = len(a)

    def temp_hum() -> None:
        readings["temperature"] = sign * _num(a[6], a[3], ".", a[4])
        readings["humidity"] = _num(a[7], a[8], ".", a[5])

    if first & 7 == 7:
        if typ == 0 and n > 6:
            readings["temperature"] = sign * _num(a[6], a[3], ".", a[4])
            devtype = "Temp"
        elif typ == 1 and n > 8:
            temp_hum()
            devtype, family = "PS50", "WS300"
        elif typ == 2 and n > 5:
            readings["rain"] = int(a[5] + a[3] + a[4], 16)
            devtype, family = "Rain", "WS7000"
        elif typ == 3 and n > 8:
            readings["wind"] = _num(a[6], a[3], ".", a[4]) + (100 if first & 8 else 0)
            readings["wind_direction"] = _num(str(int(a[7], 16) & 3), a[8], a[5])
            readings["wind_swing"] = (int(a[7], 16) & 6) >> 2
            devtype, family = "Wind", "WS7000"
        elif typ == 4 and n > 10:
            temp_hum()
            pressure = _num(a[9], a[10]) + 900
            readings["pressure"] = pressure + 100 if pressure < 930 else pressure
            devtype, family = "Indoor", "WS7000"
        elif typ == 5 and n > 5:
            factor = {1: 10, 2: 100, 3: 1000}.get(int(perl_num(a[6])), 1)
            readings["brightness"] = int(a[5] + a[4] + a[3], 16) * factor
            devtype, family = "Brightness", "WS7000"
        elif typ == 7 and n > 8:
            temp_hum()
            devtype, family = "Temp/Hum", "WS7000"
    elif n == 9:  # S300TH
        if not re.match(r"^K[0-9A-F]\d\d\d\d\d\d\d$", msg):
            return None
        readings["temperature"] = f"{sign * _num(a[6], a[3], '.', a[4]):0.1f}"
        readings["humidity"] = _num(a[7], a[8], ".", a[5])
        devtype, family = "S300TH", "WS300"
    elif n == 15:  # KS300/2
        readings["temperature"] = f"{_num(a[6], a[3], '.', a[4]):0.1f}"
        readings["humidity"] = f"{int(_num(a[8], a[5])):02d}"
        readings["wind"] = f"{_num(a[9], a[10], '.', a[7]):0.1f}"
        readings["rain"] = f"{int(a[14] + a[11] + a[12], 16) * 255 / 1000:0.1f}"
        readings["is_raining"] = "yes" if int(a[1], 16) & 2 else "no"
        devtype, family = "KS300/2", "WS300"
    elif n > 8 and re.fullmatch(r"\d*", "".join(a[3:9])):  # WS7000 temp / hum
        temp_hum()
        devtype, family = f"TH{first & 7}", "WS7000"

    if not readings:
        return None
    hum = readings.get("humidity")
    if hum is not None and not 0 <= perl_num(hum) <= 100:
        return None
    readings["DEVTYPE"] = devtype
    readings["DEVFAMILY"] = family
    return Reading(device=f"CUL_WS_{code}", model=devtype, readings=readings)
