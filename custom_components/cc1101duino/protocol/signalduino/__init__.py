"""SIGNALduino demodulation of MS / MU / MC messages.

A port of the demodulation in RFFHEM's FHEM/00_SIGNALduino.pm, driven by the protocol list
in protocols.json (see scripts/import_signalduino_protocols.pl). It turns a received line
into SIGNALduino "dmsg" strings such as ``W27#113C49B04806``, which the client modules in
the clients package decode into readings.
"""

from __future__ import annotations

import itertools
import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from .functions import (
    FILTER_FUNCTIONS,
    MC_METHODS,
    POST_DEMODULATION,
    bin_to_hex,
    length_in_range,
)

PROTOCOLS_FILE = Path(__file__).parent / "protocols.json"

# Symbols the one / zero / float / sync patterns demodulate to
SYMBOLS = {"one": "1", "zero": "0", "float": "F", "sync": "", "start": ""}

MAX_MU_DISPATCHES = 4

MS_REGEX = re.compile(
    r"^MS;(?:P[0-7]=-?\d+;){3,8}D=[0-7]+;(?:[CS]P=[0-7];){2}"
    r"((?:R=\d+;)|(?:O;)?|(?:m=?[0-9];)|(?:[sbeECA=0-9]+;))*$"
)
MU_REGEX = re.compile(
    r"^(?=.*D=\d+)(?:MU;(?:P[0-7]=-?[0-9]{1,5};){2,8}"
    r"((?:D=\d{2,};)|(?:CP=\d;)|(?:R=\d+;)?|(?:O;)?|(?:e;)?|(?:p;)?|(?:w=\d;)?)*)$"
)
MC_REGEX = re.compile(r"^M[cC];LL=-\d+;LH=\d+;SL=-\d+;SH=\d+;D=[0-9A-F]+;C=\d+;L=\d+;(?:R=\d+;)?$")


def perl_round(value: float, digits: int) -> float:
    """FHEM::Core::Utils::Math::round, which is sprintf("%.Nf")."""
    return float(f"{value:.{digits}f}")


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


@dataclass(frozen=True)
class Protocol:
    """One entry of the SIGNALduino protocol list."""

    id: str
    props: dict[str, Any]

    def get(self, key: str, default: Any = None) -> Any:
        return self.props.get(key, default)

    def num(self, key: str, default: float | None = None) -> float:
        value = _number(self.props.get(key))
        if value is None:
            if default is None:
                raise KeyError(key)
            return default
        return value

    @property
    def name(self) -> str:
        return self.props.get("name", self.id)

    @property
    def message_type(self) -> str | None:
        """Which kind of firmware message the protocol is found in, as in SIGNALduino_IdList."""
        if self.get("format") == "manchester":
            return "MC"
        if self.get("modulation") is not None:
            return "MN"  # xFSK, not received by this firmware
        if self.get("sync") is not None:
            return "MS"
        if self.get("clockabs") is not None:
            return "MU"
        return None


@dataclass(frozen=True)
class Message:
    """A demodulated message, as SIGNALduino would dispatch it to a client module."""

    protocol: Protocol
    dmsg: str

    @property
    def client(self) -> str | None:
        return self.protocol.get("clientmodule")


@cache
def load_protocols() -> dict[str, Protocol]:
    data = json.loads(PROTOCOLS_FILE.read_text())
    protocols = {}
    for protocol_id, props in data["protocols"].items():
        props = dict(props)
        # SD_Protocols::setDefaults
        if (
            props.get("format") != "manchester"
            and props.get("sync") is None
            and props.get("clockabs") is not None
            and props.get("length_min") is None
        ):
            props["length_min"] = 8
        if props.get("format") == "manchester" and props.get("method") is None:
            props["method"] = "MCRAW"
        protocols[protocol_id] = Protocol(protocol_id, props)
    return protocols


def _split_message(parts: list[str]) -> dict[str, Any]:
    """SIGNALduino_Split_Message."""
    msg: dict[str, Any] = {"pattern": {}}
    for part in parts:
        if re.match(r"^M.", part):
            msg["messagetype"] = part
        elif re.match(r"^P\d=-?\d{2,}", part) or re.match(r"^[SL][LH]=-?\d{2,}", part):
            part = re.sub(r"^P+", "", part)
            key, _, value = part.partition("=")
            msg["pattern"][key] = int(value)
        elif re.search(r"D=\d+", part) or re.match(r"^D=Y?[A-F0-9]+", part):
            msg["rawData"] = part.replace("D=", "", 1)
        elif m := re.match(r"^SP=([0-9])$", part):
            msg["syncidx"] = m.group(1)
        elif m := re.match(r"^CP=([0-9])$", part):
            msg["clockidx"] = m.group(1)
        elif re.match(r"^L=\d", part):
            msg["mcbitnum"] = part.split("=")[1]
        elif re.match(r"^C=\d+", part):
            msg["clockabs"] = part.replace("C=", "", 1)
        elif re.match(r"^R=\d+", part):
            msg["rssi"] = part.replace("R=", "", 1)
    return msg


def _is_number(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9]+", value) is not None


def _pattern_tolerance(value: float) -> float:
    """At least 1, and relatively tighter for long pulses."""
    if abs(value) > 3:
        return abs(value * 0.18) if abs(value) > 16 else abs(value * 0.3)
    return 1


def pattern_exists(search: list[float], patterns: dict[str, float], raw_data: str) -> str | None:
    """SIGNALduino_PatternExists: the pattern indexes of ``search`` as found in ``raw_data``.

    Every searched value may match several patterns within tolerance. All combinations are
    tried, closest first, and the first one that occurs in the data wins.
    """
    order: list[float] = []
    candidates: list[list[str]] = []
    for value in search:
        if value in order:
            continue
        tol = _pattern_tolerance(value)
        gaps = {key: abs(p - value) for key, p in patterns.items() if abs(p - value) <= tol}
        if not gaps:
            return None
        order.append(value)
        candidates.append(sorted(gaps, key=lambda key: (gaps[key], key)))

    # Same order as the Perl cartesian_product: the last list varies slowest
    for combination in itertools.product(*reversed(candidates)):
        combination = combination[::-1]
        if len(set(combination)) != len(combination):
            continue
        mapping = dict(zip(order, combination, strict=True))
        pstr = "".join(mapping[value] for value in search)
        if pstr in raw_data:
            return pstr
    return None


class Demodulator:
    """Turns received lines into SIGNALduino dmsg strings."""

    def __init__(self, enabled_ids: set[str] | None = None) -> None:
        """By default all stable protocols are enabled, as without a SIGNALduino whitelist.

        ``enabled_ids`` works like the whitelist: only those, including development ones.
        """
        self.protocols = load_protocols()
        self.enabled_ids = enabled_ids
        self._lists: dict[str, list[Protocol]] = {"MS": [], "MU": [], "MC": []}
        for protocol_id in sorted(self.protocols, key=float):
            protocol = self.protocols[protocol_id]
            develop_id = protocol.get("developId")
            if enabled_ids is not None:
                if protocol_id not in enabled_ids:
                    continue
            elif develop_id in ("y", "p"):
                continue
            if protocol.message_type in self._lists:
                self._lists[protocol.message_type].append(protocol)

    def _dispatchable(self, protocol: Protocol, dmsg: str) -> bool:
        """SIGNALduino_moduleMatch: check modulematch, and hold back unfinished protocols."""
        modulematch = protocol.get("modulematch")
        if modulematch is not None and not re.search(modulematch, dmsg):
            return False
        # Protocols without a finished client module are only used when enabled explicitly
        return self.enabled_ids is not None or protocol.get("developId") != "m"

    def demodulate(self, line: str) -> list[Message]:
        """Demodulate one message, e.g. ``MS;P0=...;D=...;CP=1;SP=3;R=220;``."""
        message_type = line[:2].upper()
        if message_type == "MS":
            return self._parse_ms(line)
        if message_type == "MU":
            return self._parse_mu(line)
        if message_type == "MC":
            return self._parse_mc(line)
        return []

    def _parse_ms(self, line: str) -> list[Message]:
        if not MS_REGEX.match(line):
            return []
        msg = _split_message(line.split(";"))
        if not all(_is_number(msg.get(key)) for key in ("clockidx", "syncidx", "rawData")):
            return []
        raw_data: str = msg["rawData"]
        clockabs = msg["pattern"].get(msg["clockidx"])
        if not clockabs:
            return []
        patterns = {key: perl_round(value / clockabs, 1) for key, value in msg["pattern"].items()}

        results = []
        for protocol in self._lists["MS"]:
            proto_clock = protocol.num("clockabs", 0)
            if proto_clock > 0 and not abs(proto_clock - clockabs) <= clockabs * 0.30:
                continue

            lookup: dict[str, str] = {}
            end_lookup: dict[str, str] = {}
            width = len(protocol.get("one"))
            message_start = 0
            found_all = True
            for key in ("sync", "one", "zero", "float"):
                search = protocol.get(key)
                if search is None:
                    continue
                pstr = pattern_exists(search, patterns, raw_data)
                if pstr is None:
                    if key != "float":
                        found_all = False
                        break
                    continue
                lookup[pstr] = SYMBOLS[key]
                end_lookup.setdefault(pstr[:-1], SYMBOLS[key])
                if key == "sync":
                    message_start = raw_data.index(pstr) + len(pstr)
                    bit_length = (len(raw_data) - message_start) / width
                    if protocol.num("length_min", -1) > bit_length:
                        found_all = False
                        break
                    end_lookup.clear()
            if not found_all or not lookup:
                continue

            bits: list[str] = []
            for i in range(message_start, len(raw_data), width):
                chunk = raw_data[i : i + width]
                if chunk in lookup:
                    if lookup[chunk] != "":
                        bits.append(lookup[chunk])
                elif protocol.get("reconstructBit") is not None:
                    if len(chunk) == width:
                        chunk = chunk[:-1]
                    if chunk in end_lookup:
                        bits.append(end_lookup[chunk])
                    break
                else:
                    break

            ok, _ = length_in_range(protocol, len(bits))
            if not ok:
                continue
            bits = self._pad(protocol, bits)
            post = self._post_demodulate(protocol, bits)
            if post is None:
                continue
            dmsg = protocol.get("preamble", "") + (bin_to_hex("".join(post)) or "")
            dmsg += protocol.get("postamble", "")
            if self._dispatchable(protocol, dmsg):
                results.append(Message(protocol, dmsg))
        return results

    def _parse_mu(self, line: str) -> list[Message]:
        if not MU_REGEX.match(line):
            return []
        msg = _split_message(line.split(";"))
        if not all(_is_number(msg.get(key)) for key in ("clockidx", "rawData")):
            return []

        results = []
        for protocol in self._lists["MU"]:
            clockabs = protocol.num("clockabs")
            raw_data: str = msg["rawData"]
            raw_patterns: dict[str, float] = msg["pattern"]
            if (filter_name := protocol.get("filterfunc")) is not None:
                filter_fn = FILTER_FUNCTIONS.get(filter_name)
                if filter_fn is None:
                    continue
                raw_data, raw_patterns = filter_fn(protocol, raw_data, dict(raw_patterns))
            patterns = {key: perl_round(value / clockabs, 1) for key, value in raw_patterns.items()}

            start_str = ""
            if isinstance(start := protocol.get("start"), list):
                start_str = pattern_exists(start, patterns, raw_data)
                if start_str is None:
                    continue
                raw_data = raw_data[raw_data.index(start_str) :]

            lookup: dict[str, str] = {}
            end_lookup: dict[str, str] = {}
            alternatives = []
            found_all = True
            for key in ("one", "zero", "float"):
                search = protocol.get(key)
                if search is None:
                    continue
                pstr = pattern_exists(search, patterns, raw_data)
                if pstr is None:
                    if key != "float":
                        found_all = False
                        break
                    continue
                lookup[pstr] = SYMBOLS[key]
                end_lookup.setdefault(pstr[:-1], SYMBOLS[key])
                # Perl merges identical alternatives; Python would backtrack exponentially
                if pstr not in alternatives:
                    alternatives.append(pstr)
            if not found_all:
                continue

            width = len(protocol.get("one"))
            length_min = int(protocol.num("length_min"))
            length_max = protocol.get("length_max")
            signal_regex = f"(?:{'|'.join(alternatives)}){{{length_min},}}"
            if protocol.get("reconstructBit") is not None:
                signal_regex += f"(?:{'|'.join(end_lookup)})?"

            dispatched = 0
            for match in re.finditer(f"(?:{start_str})({signal_regex})", raw_data):
                part = match.group(1)
                pairs = [part[i : i + width] for i in range(0, len(part), width)]
                if length_max not in (None, "") and len(pairs) > int(float(length_max)):
                    continue

                bits = []
                for pair in pairs:
                    if pair in lookup:
                        bits.append(lookup[pair])
                    elif protocol.get("reconstructBit") is not None and pair in end_lookup:
                        bits.append(end_lookup[pair])

                post = self._post_demodulate(protocol, bits)
                if post is None:
                    continue
                post = self._pad(protocol, post)
                data = "".join(post)
                if not protocol.get("dispatchBin"):
                    data = bin_to_hex(data) or ""
                if protocol.get("remove_zero"):
                    data = data.lstrip("0")
                dmsg = protocol.get("preamble", "") + data + protocol.get("postamble", "")
                if self._dispatchable(protocol, dmsg):
                    results.append(Message(protocol, dmsg))
                    dispatched += 1
                    if dispatched == MAX_MU_DISPATCHES:
                        break
        return results

    def _parse_mc(self, line: str) -> list[Message]:
        if not MC_REGEX.match(line):
            return []
        msg = _split_message(line.split(";"))
        if not _is_number(msg.get("clockabs")) or not _is_number(msg.get("mcbitnum")):
            return []
        raw_data: str = msg.get("rawData", "")
        if re.fullmatch(r"[0-9A-Fa-f]+", raw_data) is None:
            return []
        clock = int(msg["clockabs"])
        mcbitnum = int(msg["mcbitnum"])
        inverted = raw_data.translate(str.maketrans("0123456789ABCDEF", "FEDCBA9876543210"))
        bit_length = len(raw_data) * 4

        results = []
        for protocol in self._lists["MC"]:
            low, high = (float(value) for value in protocol.get("clockrange"))
            if not (low < clock < high and bit_length >= protocol.num("length_min")):
                continue
            invert = protocol.get("polarity") == "invert"
            if msg["messagetype"] == "Mc":
                invert = not invert
            bits = f"{int(inverted if invert else raw_data, 16):0{bit_length}b}"

            method = MC_METHODS.get(protocol.get("method"))
            if method is None:
                continue
            rcode, res = method(protocol, bits, min(mcbitnum, len(bits)))
            if rcode == -1:
                continue
            dmsg = protocol.get("preamble", "") + (res or "")
            if self._dispatchable(protocol, dmsg):
                results.append(Message(protocol, dmsg))
        return results

    @staticmethod
    def _pad(protocol: Protocol, bits: list[str]) -> list[str]:
        """Pad to full nibbles, or to full bytes if the protocol asks for it."""
        pad_with = int(protocol.num("paddingbits", 4))
        return bits + ["0"] * (-len(bits) % pad_with)

    @staticmethod
    def _post_demodulate(protocol: Protocol, bits: list[str]) -> list[str] | None:
        name = protocol.get("postDemodulation")
        if name is None:
            return bits
        func = POST_DEMODULATION.get(name)
        if func is None:
            return None
        rcode, result = func(protocol, list(bits))
        if rcode < 1 or result is None:
            return None
        return result
