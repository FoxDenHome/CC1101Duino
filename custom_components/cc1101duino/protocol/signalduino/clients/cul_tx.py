"""Port of FHEM's 14_CUL_TX.pm: LaCrosse TX2 / TX3 / TX4 sensors (dmsg ``TX...``)."""

from __future__ import annotations

import re

from .. import Message
from .base import Reading, perl_num

MATCH = re.compile(r"^TX..........")


def parse(message: Message) -> Reading | None:
    msg = message.dmsg
    if not MATCH.match(msg):
        return None
    a = msg[1:]
    try:
        sensor_id = (int(a[3], 16) << 3) + (int(a[4], 16) >> 1)
        # The integer part is sent twice
        if a[5] != a[8] or a[6] != a[9]:
            return None
        value_raw = f"{int(a[5], 16)}{a[6]}.{a[7]}"
    except (IndexError, ValueError):
        return None

    if a[2] == "0":
        name = "temperature"
        value = f"{perl_num(value_raw) - 50:2.1f}"
    elif a[2] == "E":
        name = "humidity"
        value = value_raw
    else:
        return None
    if not re.fullmatch(r"[0-9.-]*", value):
        return None
    return Reading(device=f"CUL_TX_{sensor_id}", model="CUL_TX", readings={name: value})
