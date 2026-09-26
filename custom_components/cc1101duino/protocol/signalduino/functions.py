"""Protocol specific helpers referenced by name from protocols.json.

Ported from RFFHEM's lib/FHEM/Devices/SIGNALduino/SD_Protocols.pm and 00_SIGNALduino.pm.

- ``method`` functions turn the bits of a Manchester (MC) message into the dispatched hex
  string. They return ``(rcode, hex)``; an rcode of -1 means the message does not match.
- ``postDemodulation`` functions check and rearrange the bits of a MS / MU message. They
  return ``(rcode, bits)``; an rcode below 1 means the message does not match.
- ``filterfunc`` functions preprocess the raw data and pattern list of a MU message.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import Protocol

Bits = list[str]


def bin_to_hex(bits: str) -> str | None:
    """SD_Protocols::binStr2hexStr: hex digits of a bit string, grouped from the right."""
    if not bits or re.fullmatch(r"[01]+", bits) is None:
        return None
    hex_str = ""
    index = len(bits) - 4
    while True:
        width = 4
        if index < 0:
            width += index
            index = 0
        hex_str = f"{int(bits[index : index + width], 2):X}" + hex_str
        index -= 4
        if index <= -4:
            return hex_str


def length_in_range(protocol: Protocol, length: int) -> tuple[bool, str]:
    if length < protocol.num("length_min", -1):
        return False, "message is to short"
    if protocol.get("length_max") is not None and length > protocol.num("length_max"):
        return False, "message is to long"
    return True, ""


def _bits_value(bits: Bits | str) -> int:
    return int("".join(bits), 2) if bits else 0


def _invert(bits: str) -> str:
    return bits.translate(str.maketrans("01", "10"))


# Manchester methods


def MCRAW(protocol: Protocol, bits: str, mcbitnum: int) -> tuple[int, str | None]:  # noqa: N802
    if mcbitnum > protocol.num("length_max", 0):
        return -1, " message is to long"
    return 1, bin_to_hex(bits)


def mc2dmc(bits: str) -> str:
    """Remodulate a Manchester signal as differential Manchester."""
    bits = bits.replace("1", "lh").replace("0", "hl")
    return "".join("0" if bits[i] == bits[i + 1] else "1" for i in range(1, len(bits) - 1, 2))


def mcBit2Funkbus(protocol: Protocol, bits: str, mcbitnum: int) -> tuple[int, str | None]:  # noqa: N802
    if mcbitnum < protocol.num("length_min", -1):
        return -1, " message is to short"
    if protocol.get("length_max") is not None and mcbitnum > protocol.num("length_max"):
        return -1, " message is to long"

    bits = bits.replace("1", "lh").replace("0", "hl")
    s_bitmsg = mc2dmc(bits)

    if protocol.id == "119":
        pos = s_bitmsg.find("01100")
        if 0 <= pos < 5:
            s_bitmsg = "001" + s_bitmsg[pos:]
            if len(s_bitmsg) < 48:
                return -1, "wrong bits at begin"
        else:
            return -1, "wrong bits at begin"
    else:
        s_bitmsg = "0" + s_bitmsg

    xor = 0
    chk = 0
    parity = 0
    hex_str = ""
    for i in range(6):
        chunk = s_bitmsg[i * 8 : i * 8 + 8]
        data = int(chunk, 2) if chunk else 0
        hex_str += f"{data:02X}"
        if i < 5:
            xor ^= data
        else:
            chk = data & 0x0F
            xor ^= data & 0xE0
            data &= 0xF0
        while data:
            parity ^= data & 1
            data >>= 1

    if parity == 1:
        return -1, "parity error"

    xor_nibble = ((xor & 0xF0) >> 4) ^ (xor & 0x0F)
    result = 0
    if xor_nibble & 0x8:
        result ^= 0xC
    if xor_nibble & 0x4:
        result ^= 0x2
    if xor_nibble & 0x2:
        result ^= 0x8
    if xor_nibble & 0x1:
        result ^= 0x3
    if result != chk:
        return -1, "checksum error"
    return 1, hex_str


def mcBit2Sainlogic(protocol: Protocol, bits: str, mcbitnum: int) -> tuple[int, str | None]:  # noqa: N802
    if mcbitnum > protocol.num("length_max", 0):
        return -1, " message is to long"
    if mcbitnum < 128:
        start = bits.find("010100")
        if start < 0 or start > 10:
            return -1, "start 010100 not found"
        while start < 10:
            bits = "1" + bits
            start = bits.find("010100")
        bits = bits[:128]
        mcbitnum = len(bits)
    if mcbitnum < protocol.num("length_min", 0):
        return -1, " message is to short"
    return 1, bin_to_hex(bits)


def mcBit2AS(protocol: Protocol, bits: str, mcbitnum: int) -> tuple[int, str | None]:  # noqa: N802
    message_start = bits.find("1100", 16)
    if message_start < 0:
        return -1, None
    message_end = bits.find("1100", message_start + 16)
    if message_end == -1:
        message_end = len(bits)
    ok, reason = length_in_range(protocol, message_end - message_start)
    if not ok:
        return -1, reason
    return 1, bin_to_hex(bits[message_start:])


def mcBit2Grothe(protocol: Protocol, bits: str, mcbitnum: int) -> tuple[int, str | None]:  # noqa: N802
    bits = bits[:mcbitnum]
    pos = bits.find("01000111")
    if pos < 0 or pos > 5:
        return -1, "Start pattern (01000111) not found"
    if pos == 1:
        bits = bits.removeprefix("0")
    ok, reason = length_in_range(protocol, len(bits))
    if not ok:
        return -1, reason
    return 1, bin_to_hex(bits)


def mcBit2Hideki(protocol: Protocol, bits: str, mcbitnum: int) -> tuple[int, str | None]:  # noqa: N802
    if mcbitnum == 89:
        # The beginning is missing, restore the first bit
        bits = str(int(bits[0]) ^ 1) + bits

    message_start = bits.find("10101110")
    message_start_invert = bits.find("01010001")
    if message_start < 0 or (
        message_start_invert != -1 and message_start > 0 and message_start_invert < message_start
    ):
        bits = _invert(bits)
        message_start = bits.find("10101110")

    if message_start < 0:
        return -1, None

    # A second 0x75 is at least 72 bits later, as the rain sensor sends at least 8 bytes
    message_end = bits.find("10101110", message_start + 71)
    if message_end == -1:
        message_end = len(bits)
    message_length = message_end - message_start
    if message_length < protocol.num("length_min", -1):
        return -1, " message is to short"
    if protocol.get("length_max") is not None and message_length > protocol.num("length_max"):
        return -1, " message is to long"

    hex_str = ""
    # Every 9th bit is a parity bit, and each byte is sent LSB first
    for idx in range(message_start, message_end, 9):
        byte = bits[idx : idx + 8][::-1]
        hex_str += f"{int(byte, 2) if byte else 0:02X}"
    return 1, hex_str


def mcBit2Maverick(protocol: Protocol, bits: str, mcbitnum: int) -> tuple[int, str | None]:  # noqa: N802
    match = re.search("(101010101001100110010101)", bits)
    if match is None:
        return -1, None
    header_pos = match.end(1)
    return 1, bin_to_hex(bits[header_pos : header_pos + 26 * 4])


def mcBit2OSV1(protocol: Protocol, bits: str, mcbitnum: int) -> tuple[int, str | None]:  # noqa: N802
    if mcbitnum < protocol.num("length_min", -1):
        return -1, " message is to short"
    if protocol.get("length_max") is not None and mcbitnum > protocol.num("length_max"):
        return -1, " message is to long"

    if bits[20:21] != "0":
        bits = _invert(bits)

    def rev(start: int, length: int) -> str:
        return bits[start : start + length][::-1]

    calcsum = int(rev(0, 8), 2) + int(rev(8, 8), 2) + int(rev(16, 8), 2)
    calcsum = (calcsum & 0xFF) + (calcsum >> 8)
    checksum = int(rev(24, 8), 2)
    if calcsum != checksum:
        return -1, f"OSV1 - ERROR checksum not equal: {calcsum} != {checksum}"

    new_bits = "00001010" + "01001101"
    channel = bits[6:8]
    if channel == "00":
        new_bits += "0001"
    elif channel == "10":
        new_bits += "0010"
    elif channel == "01":
        new_bits += "0011"
    else:
        return -1, f"OSV1 - ERROR channel not valid: {channel}"

    new_bits += "0000"
    new_bits += "0000"
    new_bits += rev(0, 4)
    new_bits += rev(8, 4)
    new_bits += "0" + bits[23:24] + "00"
    new_bits += rev(16, 4)
    new_bits += rev(12, 4)
    new_bits += "0000"
    new_bits += bits[21:22] + "000"
    new_bits += "00000000"

    checksum = sum(int(new_bits[i : i + 4], 2) for i in range(0, 64, 4))
    checksum = (checksum - 0xA) & 0xFF
    new_bits += f"{checksum:08b}"
    new_bits += "00000000"
    return 1, "50" + (bin_to_hex(new_bits) or "")


def mcBit2OSV2o3(protocol: Protocol, bits: str, mcbitnum: int) -> tuple[int, str | None]:  # noqa: N802
    if match := re.match(r"^.?(01){12,17}.?10011001", bits, re.S):
        preamble_pos = match.end(1)
        if preamble_pos < 24:
            return -1, " sync not found"
        message_end = None
        if end_match := re.match(r"^.{44,}(01){16,17}.?10011001", bits):
            message_end = end_match.start(1)
        if message_end is None or message_end < preamble_pos:
            message_end = len(bits)
        else:
            message_end += 16

        message_length = (message_end - preamble_pos) / 2
        if message_length < protocol.num("length_min", -1):
            return -1, " message is to short"
        if protocol.get("length_max") is not None and message_length > protocol.num("length_max"):
            return -1, " message is to long"

        osv2hex = ""
        for idx in range(preamble_pos, message_end, 16):
            if message_end - idx < 8:
                break
            osv2byte = bits[idx : idx + 16]
            # Every second bit, in reverse order and inverted
            rvosv2byte = _invert(osv2byte[::2][::-1])
            value = int(rvosv2byte, 2) if rvosv2byte else 0
            osv2hex += f"{value:02X}" if len(rvosv2byte) == 8 else f"{value:X}"

        return 1, f"{len(osv2hex) * 4:02X}{osv2hex}"

    if match := re.search(r"1{12,24}(0101)", bits):
        preamble_pos = match.start(1)
        msg_start = preamble_pos + 4
        # Preamble and sync of a second message
        if second := re.compile(r".+?(1{24})0101", re.S).match(bits, match.end()):
            message_end = second.start(1)
        else:
            message_end = mcbitnum
        message_length = message_end - msg_start
        if message_length < protocol.num("length_min", -1):
            return -1, f" message with length ({message_length}) is to short"

        osv3hex = ""
        for idx in range(msg_start, message_end, 4):
            if len(bits) - idx < 4:
                break
            osv3hex += f"{int(bits[idx : idx + 4][::-1], 2):X}"

        korr = 10
        if osv3hex[1:2] != "A":
            n1 = osv3hex[1:2]
            korr = int(osv3hex[3:4] or "0", 16)
            osv3hex = osv3hex[:1] + "A" + osv3hex[2:3] + n1 + osv3hex[4:]
        ins_korr = f"{korr:X}"

        if osv3hex[-2:] == "00":
            osv3hex = osv3hex[:-2]

        osv3len = len(osv3hex)
        osv3hex += "0"
        turn0 = osv3hex[5 : 5 + osv3len - 4]
        turn = ""
        for idx in range(0, osv3len - 5, 2):
            turn += turn0[idx + 1 : idx + 2] + turn0[idx : idx + 1]
        osv3hex = osv3hex[:5] + ins_korr + turn
        osv3hex = osv3hex[: osv3len + 1]
        return 1, f"{len(osv3hex) * 4:02X}{osv3hex}"

    return -1, None


def mcBit2OSPIR(protocol: Protocol, bits: str, mcbitnum: int) -> tuple[int, str | None]:  # noqa: N802
    if re.search("(1{14}|0{14})", bits):
        return 1, bin_to_hex(bits)
    return -1, None


def mcBit2SomfyRTS(protocol: Protocol, bits: str, mcbitnum: int) -> tuple[int, str | None]:  # noqa: N802
    if mcbitnum == 57:
        bits = bits[1:57]
    return 1, bin_to_hex(bits)


def mcBit2TFA(protocol: Protocol, bits: str, mcbitnum: int) -> tuple[int, str | None]:  # noqa: N802
    match = re.search("(1{9}101)", bits)
    if match is None:
        return -1, None
    preamble_pos = match.end(1)

    messages: list[str] = []
    reason = ""
    for _ in range(10):
        message_end = bits.find("1111111111101", preamble_pos)
        if message_end < preamble_pos:
            message_end = mcbitnum
        message_length = message_end - preamble_pos
        ok, text = length_in_range(protocol, message_length)
        if ok:
            messages.append(bin_to_hex(bits[preamble_pos:message_end]) or "")
        else:
            reason = ", " + text
        preamble_pos = bits.find("1101", message_end) + 4
        if message_end >= mcbitnum:
            break
    else:
        return -1, "loop error"

    # Only a message that was received at least twice is trusted
    seen: set[str] = set()
    for message in messages:
        if message in seen:
            return 1, message
        seen.add(message)
    return -1, f" no duplicate found{reason}"


MC_METHODS: dict[str, Callable[[Protocol, str, int], tuple[int, str | None]]] = {
    "MCRAW": MCRAW,
    "mcBit2AS": mcBit2AS,
    "mcBit2Funkbus": mcBit2Funkbus,
    "mcBit2Grothe": mcBit2Grothe,
    "mcBit2Hideki": mcBit2Hideki,
    "mcBit2Maverick": mcBit2Maverick,
    "mcBit2OSPIR": mcBit2OSPIR,
    "mcBit2OSV1": mcBit2OSV1,
    "mcBit2OSV2o3": mcBit2OSV2o3,
    "mcBit2Sainlogic": mcBit2Sainlogic,
    "mcBit2SomfyRTS": mcBit2SomfyRTS,
    "mcBit2TFA": mcBit2TFA,
}


# postDemodulation functions


def _first_one(bits: Bits) -> int:
    for index, bit in enumerate(bits):
        if bit == "1":
            return index
    return len(bits)


def _parity_ok(bits: Bits, start: int, count: int = 9) -> bool:
    """Even parity over a byte and its parity bit."""
    return sum(int(bit) for bit in bits[start : start + count]) % 2 == 0


def postDemo_EM(protocol: Protocol, bits: Bits) -> tuple[int, Bits | None]:  # noqa: N802
    msg = "".join(bits)
    msg_start = msg.find("0000000001")
    msg = msg[msg_start + 10 :]
    msg_length = len(msg)
    if msg_start <= 0 or msg_length != 89:
        return 0, None

    new_msg = ""
    msgcrc = 0
    crcbyte = ""
    for count in range(0, msg_length + 1, 9):
        crcbyte = msg[count : count + 8]
        if count < msg_length - 10:
            start = msg_start + 10 + count
            new_msg += "".join(reversed(bits[start : start + 8]))
            msgcrc ^= int(crcbyte, 2)
    if crcbyte and msgcrc == int(crcbyte, 2):
        return 1, list(new_msg)
    return 0, None


def postDemo_Revolt(protocol: Protocol, bits: Bits) -> tuple[int, Bits | None]:  # noqa: N802
    checksum = _bits_value(bits[88:96])
    total = sum(_bits_value(bits[b : b + 8]) for b in range(0, 88, 8)) & 0xFF
    if total != checksum:
        return 0, None
    return 1, bits[:88]


def postDemo_FS20(protocol: Protocol, bits: Bits) -> tuple[int, Bits | None]:  # noqa: N802
    datastart = _first_one(bits)
    if datastart == len(bits):
        return 0, None
    bits = bits[datastart + 1 :]  # preamble and start bit
    length = len(bits)
    if length in (46, 55):  # EOT bit
        bits = bits[:-1]
        length -= 1
    if length not in (45, 54):
        return 0, None

    total = 6
    for b in range(0, length - 9, 9):
        total += _bits_value(bits[b : b + 8])
    checksum = _bits_value(bits[length - 9 : length - 1])
    if ((total + 6) & 0xFF) == checksum:  # FHT80 room thermostat
        return 0, None
    if (total & 0xFF) != checksum:
        return 0, None

    for b in range(0, length, 9):
        if not _parity_ok(bits, b):
            return 0, None
    for b in range(length - 1, 0, -9):  # parity bits
        del bits[b]
    if length == 45:
        del bits[32:40]  # checksum
        bits[24:24] = ["0"] * 8  # insert byte 3
    else:
        del bits[40:48]
    return 1, bits


def postDemo_FHT80(protocol: Protocol, bits: Bits) -> tuple[int, Bits | None]:  # noqa: N802
    datastart = _first_one(bits)
    if datastart == len(bits):
        return 0, None
    bits = bits[datastart + 1 :]
    if len(bits) == 55:
        bits = bits[:-1]
    if len(bits) != 54:
        return 0, None

    total = 12 + sum(_bits_value(bits[b : b + 8]) for b in range(0, 45, 9))
    checksum = _bits_value(bits[45:53])
    if ((total - 6) & 0xFF) == checksum:  # FS20 remote control
        return 0, None
    if (total & 0xFF) != checksum:
        return 0, None
    for b in range(0, 54, 9):
        if not _parity_ok(bits, b):
            return 0, None
    for b in range(53, 0, -9):
        del bits[b]
    if bits[26] != "1":
        return 0, None
    del bits[40:48]
    bits[24:24] = ["0"] * 8
    return 1, bits


def postDemo_FHT80TF(protocol: Protocol, bits: Bits) -> tuple[int, Bits | None]:  # noqa: N802
    if len(bits) < 46:
        return 0, None
    datastart = _first_one(bits)
    if datastart == len(bits):
        return 0, None
    bits = bits[datastart + 1 :]
    if len(bits) != 45:
        return 0, None

    total = 12 + sum(_bits_value(bits[b : b + 8]) for b in range(0, 36, 9))
    checksum = _bits_value(bits[36:44])
    if (total & 0xFF) != checksum:
        return 0, None
    for b in range(0, 45, 9):
        if not _parity_ok(bits, b):
            return 0, None
    for b in range(44, 0, -9):
        del bits[b]
    if bits[26] != "0":
        return 0, None
    del bits[32:40]
    return 1, bits


WS2000_LENGTHS = (35, 50, 35, 50, 70, 40, 40, 85)


def postDemo_WS2000(protocol: Protocol, bits: Bits) -> tuple[int, Bits | None]:  # noqa: N802
    length = len(bits)
    datastart = _first_one(bits)
    if datastart == length:
        return 0, None

    def rev(start: int) -> list[str]:
        return list(reversed(bits[start : start + 4]))

    datalength = length - datastart
    datalength1 = datalength - (datalength % 5)
    sensor_type = _bits_value(rev(datastart + 1))
    if sensor_type > 7:
        return 0, None
    if sensor_type == 1 and datalength in (45, 46):  # type 1 without sum
        datalength1 += 5
    if WS2000_LENGTHS[sensor_type] != datalength1 or datastart > 10:
        return 0, None

    index = 0
    dataindex = 0
    check = 0
    total = 5
    while True:
        if bits[index + datastart] != "1":  # every 5th bit is 1
            return 0, None
        dataindex = index + datastart + 1
        if length - dataindex < 4:
            return 0, None
        data = _bits_value(rev(dataindex))
        if datalength in (45, 46):
            if index <= datalength - 5:
                check ^= data
        elif index <= datalength - 10:
            check ^= data
            total += data
        index += 5
        if index >= datalength - 1:
            break

    if check != 0:
        return 0, None
    if not 45 <= datalength <= 46 and _bits_value(rev(dataindex)) != (total & 0x0F):
        return 0, None

    datastart += 1
    new_bits: list[str | None] = [""]

    def put(target: int, source: int) -> None:
        if len(new_bits) < target + 4:
            new_bits.extend([None] * (target + 4 - len(new_bits)))
        nibble: list[str | None] = [*rev(datastart + source)]
        new_bits[target : target + 4] = nibble + [None] * (4 - len(nibble))

    put(4, 0)  # type
    put(0, 5)  # address
    put(12, 10)
    put(8, 15)
    if sensor_type in (0, 2):
        put(16, 20)
    else:
        put(20, 20)
        put(16, 25)
        if sensor_type in (1, 3, 4, 7):
            put(28, 30)
            put(24, 35)
            if sensor_type == 4:
                put(36, 40)
                put(32, 45)
                put(44, 50)
                put(40, 55)
    # Unset positions are left out, like undef array elements joined in Perl
    return 1, [bit for bit in new_bits if bit]


def postDemo_WS7035(protocol: Protocol, bits: Bits) -> tuple[int, Bits | None]:  # noqa: N802
    msg = "".join(bits)
    if msg[:8] != "10100000":
        return 0, None
    if sum(int(bit) for bit in msg[15:28]) % 2 != 0:
        return 0, None
    total = sum(int(msg[i : i + 4] or "0", 2) for i in range(0, 39, 4)) & 0x0F
    if total != int(msg[40:44] or "0", 2):
        return 0, None
    return 1, list(msg[:27] + msg[31:])


def postDemo_WS7053(protocol: Protocol, bits: Bits) -> tuple[int, Bits | None]:  # noqa: N802
    msg = "".join(bits)
    msg_start = msg.find("10100000")
    if msg_start > 0:
        msg = msg[msg_start:] + "0"
    if msg_start < 0 or len(msg) < 32:
        return 0, None
    if sum(int(bit) for bit in msg[15:28]) % 2 != 0:
        return 0, None
    return 1, list(msg[:28] + msg[16:24] + msg[28:32])


def postDemo_lengtnPrefix(protocol: Protocol, bits: Bits) -> tuple[int, Bits | None]:  # noqa: N802
    return 1, list(f"{len(bits):08b}") + bits


def Convbit2Arctec(protocol: Protocol, bits: Bits) -> tuple[int, Bits | None]:  # noqa: N802
    return 1, list("".join("01" if bit == "0" else "10" for bit in bits))


def Convbit2itv1(protocol: Protocol, bits: Bits) -> tuple[int, Bits | None]:  # noqa: N802
    msg = "".join(bits).replace("0F", "01")
    if "F" in msg:
        return 0, None
    return 1, list(msg)


def ConvHE800(protocol: Protocol, bits: Bits) -> tuple[int, Bits | None]:  # noqa: N802
    return 1, bits + ["0"] * (40 - len(bits))


def ConvHE_EU(protocol: Protocol, bits: Bits) -> tuple[int, Bits | None]:  # noqa: N802
    return 1, bits + ["0"] * (72 - len(bits))


POST_DEMODULATION: dict[str, Callable[[Protocol, Bits], tuple[int, Bits | None]]] = {
    "ConvHE800": ConvHE800,
    "ConvHE_EU": ConvHE_EU,
    "Convbit2Arctec": Convbit2Arctec,
    "Convbit2itv1": Convbit2itv1,
    "postDemo_EM": postDemo_EM,
    "postDemo_FHT80": postDemo_FHT80,
    "postDemo_FHT80TF": postDemo_FHT80TF,
    "postDemo_FS20": postDemo_FS20,
    "postDemo_Revolt": postDemo_Revolt,
    "postDemo_WS2000": postDemo_WS2000,
    "postDemo_WS7035": postDemo_WS7035,
    "postDemo_WS7053": postDemo_WS7053,
    "postDemo_lengtnPrefix": postDemo_lengtnPrefix,
}


# MU filter functions


def _in_tol(value: float, expected: float, tolerance: float) -> bool:
    return abs(value - expected) <= tolerance


def SIGNALduino_filterMC(  # noqa: N802
    protocol: Protocol, raw_data: str, patterns: dict[str, float]
) -> tuple[str, dict[str, float]]:
    """Turn a Manchester coded MU message into plain bits (Warema)."""
    clockabs = protocol.num("clockabs")
    syncabs = protocol.num("syncabs", 0)
    ht = 0
    bit_data = []
    for pulse in raw_data:
        if pulse not in patterns:
            continue
        duration = patterns[pulse]
        if _in_tol(clockabs, abs(duration), clockabs * 0.5):
            hasbit = ht
            ht ^= 1
        elif _in_tol(clockabs * 2, abs(duration), clockabs * 0.5) or _in_tol(
            syncabs + 2 * clockabs, abs(duration), clockabs * 0.5
        ):
            hasbit = 1
            ht = 1
        else:
            ht = 0
            hasbit = 0
        if hasbit:
            bit_data.append("1" if duration > 0 else "0")
    return "".join(bit_data), {"0": 0, "1": clockabs}


def _compress_patterns(
    raw_data: str, patterns: dict[str, float], factor: float, use_abs: bool
) -> tuple[str, dict[str, float]]:
    if use_abs:
        patterns = {key: abs(value) for key, value in patterns.items()}
    buckets: dict[str, float] = {}
    # Perl iterates its hash in random order; sorting keeps this deterministic
    for key in sorted(patterns):
        for b_key in list(buckets):
            if _in_tol(patterns[key], buckets[b_key], buckets[b_key] * factor):
                raw_data = raw_data.replace(key, b_key)
                buckets[b_key] = (buckets[b_key] + patterns[key]) / 2
                break
        else:
            buckets[key] = patterns[key]
    # Like the Perl original, the merged pattern keeps its original value
    return raw_data, {key: patterns[key] for key in buckets}


def SIGNALduino_filterSign(  # noqa: N802
    protocol: Protocol, raw_data: str, patterns: dict[str, float]
) -> tuple[str, dict[str, float]]:
    return _compress_patterns(raw_data, patterns, 0.25, use_abs=True)


def SIGNALduino_compPattern(  # noqa: N802
    protocol: Protocol, raw_data: str, patterns: dict[str, float]
) -> tuple[str, dict[str, float]]:
    return _compress_patterns(raw_data, patterns, 0.4, use_abs=False)


FILTER_FUNCTIONS: dict[
    str, Callable[[Protocol, str, dict[str, float]], tuple[str, dict[str, float]]]
] = {
    "SIGNALduino_compPattern": SIGNALduino_compPattern,
    "SIGNALduino_filterMC": SIGNALduino_filterMC,
    "SIGNALduino_filterSign": SIGNALduino_filterSign,
}
