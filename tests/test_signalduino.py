"""Checks the SIGNALduino port against FHEM's own test data (tests/fixtures/signalduino.json).

See scripts/import_signalduino_testdata.py for where the data comes from.
"""

import json
from pathlib import Path

import pytest

from protocol import LineCoder
from protocol.signalduino import Demodulator, Message, load_protocols
from protocol.signalduino.clients import CLIENTS, cul_tcm97001, parse
from protocol.signalduino.clients.base import perl_str
from protocol.signalduino.coder import SignalduinoCoder, reading_signals

CASES = json.loads((Path(__file__).parent / "fixtures" / "signalduino.json").read_text())
PROTOCOLS = load_protocols()

# Cases from the SIGNALduino_TOOL device list that FHEM itself no longer produces
STALE_DMSG = {
    ("64", "W64#FE97615C94381C"),  # the last bit is reconstructed since
    ("127", "P127#3603AA50"),  # an MS message for a MU protocol
    ("128", "P128#8A7FF7"),
}
STALE_READINGS = {
    "W64#FE97615C94381C",  # fails the WH2A checksum added since
    "K747431381558",  # pressure from an older CUL_WS
}


def _protocol(case: dict) -> str:
    return case["id"] if case["id"] in PROTOCOLS else case["id"].split(".")[0]


def _demodulation_cases():
    for case in CASES:
        if "rmsg" not in case or "dmsg" not in case or case["id"] not in PROTOCOLS:
            continue
        if PROTOCOLS[case["id"]].message_type == "MN":
            continue  # xFSK, which this firmware cannot receive
        stale = (case["id"], case["dmsg"]) in STALE_DMSG
        # The LTECH protocol's preamble is u31# since
        stale |= case["dmsg"].startswith("P31#")
        marks = [pytest.mark.xfail(strict=True)] if stale else []
        yield pytest.param(case, id=f"{case['id']}-{case['dmsg']}", marks=marks)


@pytest.mark.parametrize("case", _demodulation_cases())
def test_demodulation(case: dict) -> None:
    """Like FHEM's 08_DeviceData_rmsg.t: with only the protocol enabled, the dmsg is found."""
    messages = Demodulator({case["id"]}).demodulate(case["rmsg"])
    assert case["dmsg"] in [message.dmsg for message in messages]


def _reading_cases():
    for case in CASES:
        if case["module"] not in CLIENTS or "dmsg" not in case:
            continue
        if PROTOCOLS[_protocol(case)].message_type == "MN":
            continue
        # Readings that depend on attributes a FHEM user sets are not ported, except for
        # CUL_TCM97001's model, which is found automatically here
        attributes = case.get("attributes", {})
        if case["module"] == "CUL_TCM97001":
            attributes = {key: value for key, value in attributes.items() if key != "model"}
        if attributes:
            continue
        marks = [pytest.mark.xfail(strict=True)] if case["dmsg"] in STALE_READINGS else []
        yield pytest.param(case, id=f"{case['source']}-{case['dmsg']}", marks=marks)


@pytest.mark.parametrize("case", _reading_cases())
def test_client_readings(case: dict) -> None:
    message = Message(PROTOCOLS[_protocol(case)], case["dmsg"])
    model = case.get("attributes", {}).get("model")
    if case["module"] == "CUL_TCM97001" and model:
        reading = None if model == "Unknown" else cul_tcm97001.decode(case["dmsg"][1:], model)
    else:
        reading = parse(message)

    expected = {
        name: perl_str(value)
        for name, value in case.get("readings", {}).items()
        # state is FHEM's summary, readings starting with . are internal
        if name != "state" and not name.startswith(".")
    }
    if case.get("rejected") or not expected or model == "Unknown":
        assert reading is None
        return

    assert reading is not None
    assert {name: perl_str(reading.readings.get(name)) for name in expected} == expected
    if definition := case.get("internals", {}).get("DEF"):
        # Some tests define the device with its module; FHEM's code of CUL_TX / CUL_WS is
        # just the number
        device = definition.split(" ")[0]
        assert reading.device in (device, f"{reading.device.rsplit('_', 1)[0]}_{device}")


def test_cul_tcm97001_detects_model() -> None:
    """New sensors get the model FHEM would autocreate them as."""
    assert cul_tcm97001.detect_model("916001A0A000") == "Prologue"
    assert cul_tcm97001.detect_model("5410AC5F9800") == "GT_WT_02"
    assert cul_tcm97001.detect_model("6AB20000") is None


# EuroChron EFTH-800 as this firmware sends it, 15.5 °C / 48 %
EFTH800 = "^SMU;P0=-224;P1=258;P2=-487;P3=505;P4=-4884;P5=743;P6=-718;D=0121212301212303030301212123012123012123030123030121212121230121230121212121212121230301214565656561212123012121230121230303030121212301212301212303012303012121212123012123012121212121212123030121;CP=1;R=53;F=433.92;M=2;"
# Intertek / ELRO remote (IT protocol, not ported, so it becomes an event)
IT_REMOTE = "^SMS;P1=-12556;P2=1219;P3=-406;P4=412;P5=-1205;D=41232323232345452323454523452323234545234545232345;CP=4;SP=1;R=35;O;m2;F=433.92;M=2;"


def test_sensor_signals() -> None:
    signals = SignalduinoCoder().process_line(EFTH800)
    base = {
        "coder": "sd_ws",
        "type": "sensor",
        "id": "SD_WS_27_TH_2",
        "model": "EFTH-800, EFS-3110A",
        "protocol": "27",
    }
    assert signals == [
        {**base, "subtype": "temperature", "value": 15.5, "unit": "°C"},
        {**base, "subtype": "humidity", "value": 48, "unit": "%"},
        {**base, "subtype": "battery_low", "value": False},
    ]


def test_message_signals_and_repeats() -> None:
    now = 0.0
    coder = SignalduinoCoder(clock=lambda: now)
    event = {
        "coder": "signalduino",
        "type": "message",
        "protocol": "3",
        "name": "chip xx2260 / xx2262",
        "data": "iF99726",
    }
    assert event in coder.process_line(IT_REMOTE)
    # A remote repeats itself; only the first reception should trigger something
    assert {**event, "repeat": True} in coder.process_line(IT_REMOTE)
    now = 5.0
    assert event in coder.process_line(IT_REMOTE)


def test_other_modulation_is_ignored() -> None:
    assert SignalduinoCoder().process_line(EFTH800.replace("M=2;", "M=0;")) == []


def test_wind_units() -> None:
    """Wind speeds are converted to m/s from the units the FHEM modules report."""
    protocol = PROTOCOLS["12"]
    hideki = Message(protocol, "P12#7585B2C471BF71BFFDF0029C605C03")
    reading = parse(hideki)
    assert reading is not None
    signals = {s["subtype"]: s["value"] for s in reading_signals(hideki, reading)}
    assert signals["wind_speed"] == round(float(reading.readings["windSpeed"]) * 0.044704, 2)


def test_own_decoders_take_precedence() -> None:
    """A LaCrosse TX signal is only reported by the own decoder, not by SIGNALduino again."""
    line = "^SMU;P0=19800;P1=-1086;P2=1412;P3=618;P4=-8096;P5=164;P6=-552;D=0121212131213121212121212131313121212121213121312131213121313121213121312131213131213134565;CP=3;R=190;F=433.88;M=2;"
    assert {signal["coder"] for signal in LineCoder().process_signal_line(line)} == {"lacrosse"}
