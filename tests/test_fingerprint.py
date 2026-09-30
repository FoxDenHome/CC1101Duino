"""Fingerprints of unrecognized signals, checked against FHEM's SIGNALduino test data."""

import json
from pathlib import Path

import pytest

from protocol.fingerprint import Fingerprint

SIGNALDUINO = json.loads((Path(__file__).parent / "fixtures" / "signalduino.json").read_text())

# Two Intertechno remotes of one model, with different buttons pressed
IT_PRESSES = [
    case["rmsg"]
    for case in SIGNALDUINO
    if case.get("module") == "IT" and case["dmsg"].startswith(("i0BC6", "iD8E8"))
]
NOISE = "^SMU;P0=-188;P1=-921;P2=739;P3=268;P4=-406;P5=566;P6=-299;P7=350;D=12121213434563434343434343434347656505034745;CP=3;R=186;F=433.88;M=2;"
LACROSSE = "^SMU;P0=19800;P1=-1086;P2=1412;P3=618;P4=-8096;P5=164;P6=-552;D=0121212131213121212121212131313121212121213121312131213121313121213121312131213131213134565;CP=3;R=190;F=433.88;M=2;"
IT_REMOTE = "^SMS;P1=-12556;P2=1219;P3=-406;P4=412;P5=-1205;D=41232323232345452323454523452323234545234545232345;CP=4;SP=1;R=35;O;m2;F=433.92;M=2;"
OREGON = "^SMC;LL=-1018;LH=958;SL=-506;SH=475;D=AAAAAAAA66959A5A9A9AA5599665;C=493;L=112;R=14;F=433.92;M=2;"


def fingerprint(line: str) -> Fingerprint:
    result = Fingerprint.from_line(line)
    assert result is not None
    return result


def test_same_model_different_data() -> None:
    prints = [fingerprint("^S" + line + "F=433.92;M=2;") for line in IT_PRESSES]
    assert len(prints) == 5
    assert all(prints[0].similar(other) for other in prints)


def test_different_devices() -> None:
    lacrosse = fingerprint(LACROSSE)
    it_remote = fingerprint(IT_REMOTE)
    oregon = fingerprint(OREGON)
    assert not lacrosse.similar(it_remote)
    assert not it_remote.similar(oregon)
    assert oregon.kind == "manchester"
    assert oregon.pulses == (493,)


def test_other_frequency() -> None:
    assert not fingerprint(IT_REMOTE).similar(fingerprint(IT_REMOTE.replace("433.92", "868.35")))


@pytest.mark.parametrize(
    "line",
    [
        NOISE,
        "^SMU;P0=500;P1=-500;D=0101;F=433.92;M=2;",
        "^SMU;P0=500;D=0000000000000000000000000000000;F=433.92;M=2;",
        "^SMC;LL=-1018;LH=958;SL=-506;SH=475;D=AA;C=493;L=8;F=433.92;M=2;",
        "^SMU;P0=x;D=00;F=433.92;M=2;",
        "^<CC1101Duino ready",
    ],
)
def test_noise_rejected(line: str) -> None:
    assert Fingerprint.from_line(line) is None


def test_dict_roundtrip() -> None:
    original = fingerprint(LACROSSE)
    assert Fingerprint.from_dict(json.loads(json.dumps(original.as_dict()))) == original
