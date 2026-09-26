"""Integration tests against a fake serial port."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_DEVICE, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from custom_components.cc1101duino.config_flow import _list_ports
from custom_components.cc1101duino.const import CONF_AUTOMATIC_ADD, DOMAIN, EVENT_SIGNAL

LACROSSE_TEMP = "^SMU;P0=19800;P1=-1086;P2=1412;P3=618;P4=-8096;P5=164;P6=-552;D=0121212131213121212121212131313121212121213121312131213121313121213121312131213131213134565;CP=3;R=190;F=433.88;M=2;"
MINKA_OFF = "^SMU;P0=417;P1=-417;D=011011010011010011011010010011010011011;F=304.2;M=2;"


class FakeSerial:
    def __init__(self) -> None:
        self.reader = asyncio.StreamReader()
        self.writer = MagicMock()
        self.writer.drain = AsyncMock()
        self.written: list[str] = []
        self.reply = "^$SOK Done\r\n"

        def write(data: bytes) -> None:
            self.written.append(data.decode())
            if self.reply:
                self.feed(self.reply)

        self.writer.write.side_effect = write

    def feed(self, line: str) -> None:
        self.reader.feed_data((line.rstrip("\r\n") + "\r\n").encode())


@pytest.fixture
def fake_serial():
    fake = FakeSerial()
    with patch(
        "custom_components.cc1101duino.hub.async_open",
        AsyncMock(return_value=(fake.reader, fake.writer)),
    ):
        yield fake


async def setup_entry(hass: HomeAssistant, **options) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_DEVICE: "/dev/ttyFAKE"}, options=options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_lacrosse_sensor_auto_added(hass: HomeAssistant, fake_serial: FakeSerial) -> None:
    entry = await setup_entry(hass)
    assert entry.state is ConfigEntryState.LOADED

    fake_serial.feed("^<CC1101Duino ready 0")
    fake_serial.feed(LACROSSE_TEMP)
    await hass.async_block_till_done()

    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert len(entities) == 1
    state = hass.states.get(entities[0].entity_id)
    assert state.state == "5.6"
    assert state.attributes["unit_of_measurement"] == "°C"

    # Survives a reload through the entity registry, with the restored value
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(entities[0].entity_id).state == "5.6"

    # Connection drop makes sensors unavailable
    fake_serial.reader.feed_eof()
    await hass.async_block_till_done()
    assert hass.states.get(entities[0].entity_id).state == STATE_UNAVAILABLE


async def test_automatic_add_disabled(hass: HomeAssistant, fake_serial: FakeSerial) -> None:
    entry = await setup_entry(hass, **{CONF_AUTOMATIC_ADD: False})
    fake_serial.feed(LACROSSE_TEMP)
    await hass.async_block_till_done()
    assert er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id) == []


async def test_command_fires_event(hass: HomeAssistant, fake_serial: FakeSerial) -> None:
    entry = await setup_entry(hass)
    events = async_capture_events(hass, EVENT_SIGNAL)
    fake_serial.feed(LACROSSE_TEMP)
    fake_serial.feed(MINKA_OFF)
    await hass.async_block_till_done()

    assert [e.data for e in events] == [
        {
            "coder": "minka_aire",
            "type": "command",
            "id": "00101001",
            "command": "off",
            "config_entry_id": entry.entry_id,
        }
    ]


async def test_send_signal(hass: HomeAssistant, fake_serial: FakeSerial) -> None:
    await setup_entry(hass)
    await hass.services.async_call(
        DOMAIN,
        "send_signal",
        {"coder": "minka_aire", "id": "00101001", "command": "light"},
        blocking=True,
    )
    assert fake_serial.written == [
        "^S;F=304.2;M=2;R=10;S=10000;D=011011010011010011011010011010011010011;P0=417;P1=-417;\n"
    ]

    await hass.services.async_call(DOMAIN, "send_raw", {"line": "F433.92"}, blocking=True)
    assert fake_serial.written[-1] == "^F433.92\n"


async def test_send_errors(hass: HomeAssistant, fake_serial: FakeSerial) -> None:
    await setup_entry(hass)

    with pytest.raises(HomeAssistantError, match="Cannot encode"):
        await hass.services.async_call(
            DOMAIN,
            "send_signal",
            {"coder": "minka_aire", "id": "1", "command": "off"},
            blocking=True,
        )

    fake_serial.reply = "^$FBAD Invalid parameters"
    with pytest.raises(HomeAssistantError, match="rejected"):
        await hass.services.async_call(DOMAIN, "send_raw", {"line": "Fnope"}, blocking=True)

    fake_serial.reply = None
    with (
        patch("custom_components.cc1101duino.hub.COMMAND_TIMEOUT", 0.01),
        pytest.raises(HomeAssistantError, match="No reply"),
    ):
        await hass.services.async_call(DOMAIN, "send_raw", {"line": "F433.92"}, blocking=True)


async def test_setup_retry_when_port_missing(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.cc1101duino.hub.async_open", AsyncMock(side_effect=OSError("nope"))
    ):
        entry = MockConfigEntry(domain=DOMAIN, data={CONF_DEVICE: "/dev/ttyFAKE"})
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


BY_ID = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"


def fake_by_id(device: str) -> str:
    return BY_ID if device == "/dev/ttyUSB0" else device


def test_list_ports() -> None:
    usb_port = MagicMock(
        device="/dev/ttyUSB0",
        serial_number=None,
        manufacturer="QinHeng Electronics",
        description="USB Serial",
        vid=0x1A86,
        pid=0x7523,
    )
    legacy = MagicMock(device="/dev/ttyS0", vid=None, pid=None, description="n/a")
    uart = MagicMock(
        device="/dev/ttyAMA0",
        serial_number=None,
        manufacturer=None,
        description="ttyAMA0",
        vid=None,
        pid=None,
    )
    with (
        patch("serial.tools.list_ports.comports", return_value=[legacy, usb_port, uart]),
        patch("homeassistant.components.usb.get_serial_by_id", side_effect=fake_by_id),
    ):
        ports = _list_ports()
    assert ports == [
        {
            "value": BY_ID,
            "label": f"USB Serial - {BY_ID}, s/n: n/a - QinHeng Electronics - 1A86:7523",
        },
        {"value": "/dev/ttyAMA0", "label": "ttyAMA0 - /dev/ttyAMA0, s/n: n/a"},
    ]


@pytest.fixture
def mock_ports():
    with (
        patch(
            "custom_components.cc1101duino.config_flow._list_ports",
            return_value=[{"value": BY_ID, "label": "USB Serial"}],
        ),
        patch("homeassistant.components.usb.get_serial_by_id", side_effect=fake_by_id),
    ):
        yield


async def test_config_flow(hass: HomeAssistant, fake_serial: FakeSerial, mock_ports) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "form"

    with patch(
        "custom_components.cc1101duino.config_flow.async_open",
        AsyncMock(side_effect=OSError),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_DEVICE: BY_ID, CONF_AUTOMATIC_ADD: True}
        )
    assert result["errors"] == {"base": "cannot_connect"}

    with patch(
        "custom_components.cc1101duino.config_flow.async_open",
        AsyncMock(return_value=(None, MagicMock())),
    ):
        # A typed unstable path is stored as its /dev/serial/by-id path
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_DEVICE: "/dev/ttyUSB0", CONF_AUTOMATIC_ADD: False}
        )
    assert result["type"] == "create_entry"
    assert result["data"] == {CONF_DEVICE: BY_ID}
    assert result["options"] == {CONF_AUTOMATIC_ADD: False}
    await hass.async_block_till_done()

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.unique_id == BY_ID
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_AUTOMATIC_ADD: True}
    )
    assert result["type"] == "create_entry"
    assert entry.options == {CONF_AUTOMATIC_ADD: True}

    # The same port cannot be added twice, whichever path is typed
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE: "/dev/ttyUSB0", CONF_AUTOMATIC_ADD: True}
    )
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


async def test_reconfigure(hass: HomeAssistant, fake_serial: FakeSerial, mock_ports) -> None:
    entry = await setup_entry(hass)
    other = MockConfigEntry(
        domain=DOMAIN, unique_id="socket://other:2000", data={CONF_DEVICE: "socket://other:2000"}
    )
    other.add_to_hass(hass)

    # Keeping the current port works although it is already open
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] == "form"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE: "/dev/ttyFAKE"}
    )
    assert result["reason"] == "reconfigure_successful"

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE: "socket://other:2000"}
    )
    assert result["reason"] == "already_configured"

    result = await entry.start_reconfigure_flow(hass)
    with patch(
        "custom_components.cc1101duino.config_flow.async_open",
        AsyncMock(return_value=(None, MagicMock())),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_DEVICE: "/dev/ttyUSB0"}
        )
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.data == {CONF_DEVICE: BY_ID}
    assert entry.unique_id == BY_ID
    assert entry.title == BY_ID
    assert entry.state is ConfigEntryState.LOADED
