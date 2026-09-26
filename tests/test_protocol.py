"""Checks the Python protocol port against output captured from the original TypeScript decoder."""

import json
from pathlib import Path

import pytest

from protocol import LineCoder, NotSupportedError

REFERENCE = json.loads((Path(__file__).parent / "fixtures" / "reference.json").read_text())


@pytest.fixture
def coder() -> LineCoder:
    # The reference covers the decoders ported from TypeScript; SIGNALduino has its own tests
    return LineCoder(signalduino=False)


@pytest.mark.parametrize("case", REFERENCE["decoded"], ids=lambda c: c["line"][:40])
def test_decode_matches_reference(coder: LineCoder, case) -> None:
    assert coder.process_signal_line(case["line"]) == case["signals"]


@pytest.mark.parametrize("case", REFERENCE["encoded"], ids=lambda c: c["signal"]["command"])
def test_encode_matches_reference(coder: LineCoder, case) -> None:
    assert coder.create_signal_line(case["signal"]) == case["line"]


@pytest.mark.parametrize("case", REFERENCE["encoded"], ids=lambda c: c["signal"]["command"])
def test_encode_decode_roundtrip(coder: LineCoder, case) -> None:
    # Turn the transmit command into what the receiver would report for it
    fields = dict(f.split("=", 1) for f in case["line"].strip()[3:].split(";") if f)
    received = "^SMU;" + "".join(
        f"{k}={v};" for k, v in fields.items() if k in "DFM" or k.startswith("P")
    )
    command = case["signal"]["command"]
    assert coder.process_signal_line(received) == [
        {
            "coder": "minka_aire",
            "type": "command",
            "id": case["signal"]["id"],
            "command": "light_1" if command == "light" else command,
        }
    ]


# Captured from a Nexus sensor: ID 180, channel 2, 16.8 °C, 60 or 61 %. This is the last packet of
# the transmission, so its final (humidity) bit merges into the silence after it.
NEXUS_D = "03020102020102010102010102010101010201020102010101020202020101020202020104"
NEXUS_LAST = (
    f"^SMU;P0=424;P1=-1070;P2=-2058;P3=-4060;P4=-32001;D={NEXUS_D};CP=0;R=170;F=433.88;M=2;"
)
# A full packet (final bit 0) followed by the start of a repeat
NEXUS_FULL = NEXUS_LAST.replace(NEXUS_D, NEXUS_D[:-2] + "0103" + NEXUS_D[2:40])


def nexus(subtype: str, unit: str, value: float) -> dict:
    return {
        "coder": "nexus",
        "type": "sensor",
        "subtype": subtype,
        "id": "180",
        "unit": unit,
        "value": value,
    }


def test_nexus_last_packet_has_temperature_only(coder: LineCoder) -> None:
    assert coder.process_signal_line(NEXUS_LAST) == [nexus("temperature", "°C", 16.8)]


def test_nexus_full_packet(coder: LineCoder) -> None:
    assert coder.process_signal_line(NEXUS_FULL) == [
        nexus("temperature", "°C", 16.8),
        nexus("humidity", "%", 60),
    ]


def test_nexus_negative_temperature(coder: LineCoder) -> None:
    # -5.0 °C is 0xFCE in 12 bit two's complement
    bits = f"{180:08b}" + "1001" + f"{0xFCE:012b}" + "1111" + f"{55:08b}"
    data = "03" + "".join("02" if bit == "1" else "01" for bit in bits) + "03"
    line = f"^SMU;P0=500;P1=-1000;P2=-2000;P3=-4000;D={data};CP=0;R=170;F=433.92;M=2;"
    assert coder.process_signal_line(line) == [
        nexus("temperature", "°C", -5.0),
        nexus("humidity", "%", 55),
    ]


@pytest.mark.parametrize(
    "line",
    [
        # Heard from the middle, without the sync gap in front
        NEXUS_LAST.replace(NEXUS_D, NEXUS_D[2:]),
        "",
        "garbage",
        "^$SOK Done",
        "^<CC1101Duino ready 0",
        "^SMU;P0=abc;D=00;",
        "^SMU;P0=100;D=01;F=433.88;M=2;",
    ],
)
def test_ignores_non_signal_lines(coder: LineCoder, line: str) -> None:
    assert coder.process_signal_line(line) == []


@pytest.mark.parametrize(
    "signal",
    [
        {"coder": "nope"},
        {"coder": "minka_aire", "id": "0010100", "command": "off"},
        {"coder": "minka_aire", "id": "00101002", "command": "off"},
        {"coder": "minka_aire", "id": "00101001", "command": "nope"},
        {"coder": "lacrosse", "id": "1", "subtype": "temperature"},
    ],
)
def test_encode_rejects_invalid(coder: LineCoder, signal) -> None:
    with pytest.raises(NotSupportedError):
        coder.create_signal_line(signal)
