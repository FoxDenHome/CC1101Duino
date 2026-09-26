"""Checks the Python protocol port against output captured from the original TypeScript decoder."""

import json
from pathlib import Path

import pytest

from protocol import LineCoder, NotSupportedError

REFERENCE = json.loads((Path(__file__).parent / "fixtures" / "reference.json").read_text())


@pytest.fixture
def coder() -> LineCoder:
    return LineCoder()


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


@pytest.mark.parametrize(
    "line",
    [
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
