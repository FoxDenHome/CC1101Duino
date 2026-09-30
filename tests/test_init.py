"""Integration tests against a fake serial port."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.update import UpdateEntityFeature
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_DEVICE, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from custom_components.cc1101duino.claude import AuthenticationFailed, ClassificationError
from custom_components.cc1101duino.config_flow import _list_ports
from custom_components.cc1101duino.const import (
    CONF_API_KEY,
    CONF_AUTOMATIC_ADD,
    CONF_CLASSIFY_AUTOMATICALLY,
    CONF_MAX_CLASSIFICATIONS_PER_DAY,
    CONF_MIN_TRANSMISSIONS,
    CONF_MODEL,
    DEFAULT_MAX_CLASSIFICATIONS_PER_DAY,
    DEFAULT_MIN_TRANSMISSIONS,
    DEFAULT_MODEL,
    DOMAIN,
    EVENT_SIGNAL,
)
from custom_components.cc1101duino.firmware import FlashError, load_firmware

LACROSSE_TEMP = "^SMU;P0=19800;P1=-1086;P2=1412;P3=618;P4=-8096;P5=164;P6=-552;D=0121212131213121212121212131313121212121213121312131213121313121213121312131213131213134565;CP=3;R=190;F=433.88;M=2;"
NOISE = "^SMU;P0=-188;P1=-921;P2=739;P3=268;P4=-406;P5=566;P6=-299;P7=350;D=12121213434563434343434343434347656505034745;CP=3;R=186;F=433.88;M=2;"
# EuroChron EFTH-800 (SIGNALduino protocol 27), 15.5 °C / 48 %
EFTH800 = "^SMU;P0=-224;P1=258;P2=-487;P3=505;P4=-4884;P5=743;P6=-718;D=0121212301212303030301212123012123012123030123030121212121230121230121212121212121230301214565656561212123012121230121230303030121212301212301212303012303012121212123012123012121212121212123030121;CP=1;R=53;F=433.92;M=2;"
# Intertek / ELRO remote (SIGNALduino protocol 3)
IT_REMOTE = "^SMS;P1=-12556;P2=1219;P3=-406;P4=412;P5=-1205;D=41232323232345452323454523452323234545234545232345;CP=4;SP=1;R=35;O;m2;F=433.92;M=2;"
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
    with (
        patch(
            "custom_components.cc1101duino.hub.async_open",
            AsyncMock(return_value=(fake.reader, fake.writer)),
        ),
        # Tests that want the version queried lower this
        patch("custom_components.cc1101duino.hub.VERSION_QUERY_DELAY", 3600),
    ):
        yield fake


def remote_sensors(hass: HomeAssistant, entry: MockConfigEntry) -> list[er.RegistryEntry]:
    """Entities of wireless sensors, leaving out the hub's own diagnostics."""
    return [
        reg_entry
        for reg_entry in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if reg_entry.entity_category is None
    ]


def hub_entity(hass: HomeAssistant, entry: MockConfigEntry, domain: str, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}-{key}")
    assert entity_id is not None
    return entity_id


async def setup_entry(
    hass: HomeAssistant, device: str = "/dev/ttyFAKE", **options
) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_DEVICE: device}, options=options)
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

    entities = remote_sensors(hass, entry)
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
    assert remote_sensors(hass, entry) == []


async def test_diagnostics(hass: HomeAssistant, fake_serial: FakeSerial) -> None:
    entry = await setup_entry(hass)

    def state(domain: str, key: str):
        return hass.states.get(hub_entity(hass, entry, domain, key))

    assert state("binary_sensor", "connected").state == STATE_ON
    assert state("sensor", "signals_received").state == "0"
    assert state("sensor", "last_signal").state == "unknown"

    fake_serial.feed("^<RX initialized F=433.88;M=2")
    fake_serial.feed(LACROSSE_TEMP)
    fake_serial.feed(NOISE)
    await hass.async_block_till_done()

    assert state("sensor", "firmware_message").state == "RX initialized F=433.88;M=2"
    assert state("sensor", "signals_received").state == "2"
    assert state("sensor", "signals_decoded").state == "1"
    assert state("sensor", "signals_unrecognized").state == "1"
    assert state("sensor", "signal_strength").state == "-70"

    last = state("sensor", "last_signal")
    assert last.attributes["line"] == NOISE
    assert last.attributes["signals"] == []

    decoded = state("sensor", "last_decoded_signal")
    assert decoded.attributes["line"] == LACROSSE_TEMP
    assert decoded.attributes["rssi"] == -66
    assert decoded.attributes["signals"][0]["value"] == 5.6

    unrecognized = state("sensor", "last_unrecognized_signal")
    assert unrecognized.attributes["line"] == NOISE
    assert unrecognized.state == last.state

    fake_serial.reader.feed_eof()
    await hass.async_block_till_done()
    assert state("binary_sensor", "connected").state == STATE_OFF


async def test_signalduino_sensor(hass: HomeAssistant, fake_serial: FakeSerial) -> None:
    entry = await setup_entry(hass)
    now = 1000.0

    async def feed(line: str, at: float) -> None:
        nonlocal now
        now = at
        fake_serial.feed(line)
        await hass.async_block_till_done()

    with patch("custom_components.cc1101duino.hub.time.monotonic", side_effect=lambda: now):
        # Heard once, or twice within one transmission, is not enough to add a sensor
        await feed(EFTH800, 1000)
        await feed(EFTH800, 1001)
        assert remote_sensors(hass, entry) == []

        await feed(EFTH800, 1060)

    registry = er.async_get(hass)
    entity_ids = {
        reg_entry.unique_id.rsplit("-", 1)[1]: reg_entry.entity_id
        for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id)
        if "SD_WS_27_TH_2" in reg_entry.unique_id
    }
    assert set(entity_ids) == {"temperature", "humidity", "battery_low"}
    assert hass.states.get(entity_ids["temperature"]).state == "15.5"
    assert hass.states.get(entity_ids["humidity"]).state == "48"
    assert hass.states.get(entity_ids["battery_low"]).state == "off"
    assert registry.async_get(entity_ids["battery_low"]).entity_category == "diagnostic"

    device = dr.async_get(hass).async_get(registry.async_get(entity_ids["temperature"]).device_id)
    assert device.name == "SD_WS_27_TH_2"
    assert device.model == "EFTH-800, EFS-3110A"


async def test_signalduino_message_fires_event(
    hass: HomeAssistant, fake_serial: FakeSerial
) -> None:
    entry = await setup_entry(hass)
    events = async_capture_events(hass, EVENT_SIGNAL)
    fake_serial.feed(IT_REMOTE)
    # The remote repeats the press
    fake_serial.feed(IT_REMOTE)
    await hass.async_block_till_done()

    assert [e.data for e in events if e.data["protocol"] == "3"] == [
        {
            "coder": "signalduino",
            "type": "message",
            "protocol": "3",
            "name": "chip xx2260 / xx2262",
            "data": "iF99726",
            "config_entry_id": entry.entry_id,
        }
    ]
    # Both receptions count as decoded
    assert hass.states.get(hub_entity(hass, entry, "sensor", "signals_decoded")).state == "2"


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
        result["flow_id"], {CONF_AUTOMATIC_ADD: True, CONF_API_KEY: "sk-ant-test"}
    )
    assert result["type"] == "create_entry"
    assert entry.options == {
        CONF_AUTOMATIC_ADD: True,
        CONF_API_KEY: "sk-ant-test",
        CONF_MODEL: DEFAULT_MODEL,
        CONF_CLASSIFY_AUTOMATICALLY: True,
        CONF_MIN_TRANSMISSIONS: DEFAULT_MIN_TRANSMISSIONS,
        CONF_MAX_CLASSIFICATIONS_PER_DAY: DEFAULT_MAX_CLASSIFICATIONS_PER_DAY,
    }

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


async def test_firmware_version_from_ready_message(
    hass: HomeAssistant, fake_serial: FakeSerial
) -> None:
    entry = await setup_entry(hass)
    update = hub_entity(hass, entry, "update", "firmware")
    bundled = load_firmware().version

    state = hass.states.get(update)
    assert state.state == "unknown"
    assert state.attributes["latest_version"] == bundled
    assert state.attributes["supported_features"] & UpdateEntityFeature.INSTALL

    fake_serial.feed(f"^<CC1101Duino ready V={bundled};R=0")
    await hass.async_block_till_done()
    state = hass.states.get(update)
    assert state.state == STATE_OFF
    assert state.attributes["installed_version"] == bundled

    # Firmware from before versions
    fake_serial.feed("^<CC1101Duino ready 0")
    await hass.async_block_till_done()
    state = hass.states.get(update)
    assert state.state == STATE_ON
    assert state.attributes["installed_version"] == "0"


@pytest.mark.parametrize(("reply", "version"), [("^$VOK 7", "7"), ("^$VBAD Unknown command", "0")])
async def test_firmware_version_query(
    hass: HomeAssistant, fake_serial: FakeSerial, reply: str, version: str
) -> None:
    fake_serial.reply = reply
    with patch("custom_components.cc1101duino.hub.VERSION_QUERY_DELAY", 0):
        entry = await setup_entry(hass, device="socket://host:2000")
        await asyncio.sleep(0.01)
        await hass.async_block_till_done()

    assert fake_serial.written == ["^V\n"]
    state = hass.states.get(hub_entity(hass, entry, "update", "firmware"))
    assert state.attributes["installed_version"] == version
    # Over ser2net the bootloader cannot be started
    assert not state.attributes["supported_features"] & UpdateEntityFeature.INSTALL


async def test_firmware_install(hass: HomeAssistant, fake_serial: FakeSerial) -> None:
    entry = await setup_entry(hass)
    update = hub_entity(hass, entry, "update", "firmware")
    fake_serial.feed("^<CC1101Duino ready 0")
    await hass.async_block_till_done()

    flashed = []

    def flash(device, image, progress) -> None:
        progress(50)
        flashed.append((device, image))

    with patch("custom_components.cc1101duino.hub.flash", flash):
        await hass.services.async_call("update", "install", {"entity_id": update}, blocking=True)
    await hass.async_block_till_done()
    assert flashed == [("/dev/ttyFAKE", load_firmware().image)]

    # Reconnected, and waiting for the new firmware to report its version
    assert hass.states.get(hub_entity(hass, entry, "binary_sensor", "connected")).state == STATE_ON
    state = hass.states.get(update)
    assert state.attributes["in_progress"] is False
    assert state.attributes["installed_version"] is None

    fake_serial.feed(f"^<CC1101Duino ready V={load_firmware().version};R=0")
    await hass.async_block_till_done()
    assert hass.states.get(update).state == STATE_OFF

    fake_serial.feed("^<CC1101Duino ready 0")
    await hass.async_block_till_done()

    def broken_flash(device, image, progress) -> None:
        raise FlashError("No response from the bootloader")

    with (
        patch("custom_components.cc1101duino.hub.flash", broken_flash),
        pytest.raises(HomeAssistantError, match="No response from the bootloader"),
    ):
        await hass.services.async_call("update", "install", {"entity_id": update}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(hub_entity(hass, entry, "binary_sensor", "connected")).state == STATE_ON


def pwm_line(bits: str, short: int = 640, long: int = 1920, sync: int = -7040) -> str:
    """A made-up PWM protocol that no decoder knows, sent three times after a sync gap."""
    data = ("4" + "".join("21" if bit == "1" else "03" for bit in bits)) * 3
    return f"^SMU;P0={short};P1=-{short};P2={long};P3=-{long};P4={sync};D={data};CP=0;R=200;F=433.92;M=2;"


UNKNOWN_A = pwm_line("1011001110001111000010100101")
UNKNOWN_B = pwm_line("1011001110001111000011110000")
OTHER_UNKNOWN = pwm_line("1011001110001111000010100101", short=300, long=900, sync=-9000)

CLASSIFICATION = {
    "is_noise": False,
    "category": "temperature_sensor",
    "device": "Made-up sensor",
    "protocol": "none",
    "confidence": "medium",
    "summary": "A PWM temperature sensor.",
    "encoding": "PWM",
    "packet_structure": "28 bits",
    "decoded_samples": [],
    "decoder_hint": "SignalPacketizerFixedVariable",
    "model": "claude-opus-5-5",
}


@pytest.fixture
def mock_classify():
    with patch(
        "custom_components.cc1101duino.classifier.async_classify",
        AsyncMock(return_value=CLASSIFICATION),
    ) as mock:
        yield mock


async def feed_at(hass: HomeAssistant, fake_serial: FakeSerial, freezer, line: str, delay: float):
    freezer.tick(delay)
    fake_serial.feed(line)
    await hass.async_block_till_done()
    # Classifying runs in background tasks
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        if tasks := list(entry.runtime_data.classifier._tasks.values()):
            await asyncio.wait(tasks)
    await hass.async_block_till_done()


async def test_unknown_signal_classified_once(
    hass: HomeAssistant, fake_serial: FakeSerial, freezer, mock_classify
) -> None:
    entry = await setup_entry(hass, **{CONF_API_KEY: "sk-ant-test"})
    events = async_capture_events(hass, "cc1101duino_unknown_signal_classified")
    sensor = hub_entity(hass, entry, "sensor", "unknown_signal_types")

    # Repeats within one transmission count once, noise is not collected at all
    await feed_at(hass, fake_serial, freezer, UNKNOWN_A, 0)
    await feed_at(hass, fake_serial, freezer, UNKNOWN_A, 0.5)
    await feed_at(hass, fake_serial, freezer, NOISE, 0.5)
    await feed_at(hass, fake_serial, freezer, UNKNOWN_B, 30)
    assert hass.states.get(sensor).state == "0"
    mock_classify.assert_not_called()

    # The third transmission, with other data, has it classified
    await feed_at(hass, fake_serial, freezer, UNKNOWN_B, 30)
    mock_classify.assert_called_once()
    _, model, record = mock_classify.call_args.args
    assert model == DEFAULT_MODEL
    assert record["transmissions"] == 3
    assert record["count"] == 4
    assert record["intervals"] == [30.5, 30.0]
    assert [sample["line"] for sample in record["samples"]] == [UNKNOWN_A, UNKNOWN_B]

    assert len(events) == 1
    assert events[0].data["device"] == "Made-up sensor"
    assert events[0].data["config_entry_id"] == entry.entry_id
    state = hass.states.get(sensor)
    assert state.state == "1"
    assert state.attributes["signal_types"][0]["status"] == "classified"
    assert state.attributes["signal_types"][0]["device"] == "Made-up sensor"

    # Once determined, the same kind of signal is never sent again, also after a reload
    await feed_at(hass, fake_serial, freezer, UNKNOWN_A, 30)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await feed_at(hass, fake_serial, freezer, UNKNOWN_B, 30)
    assert mock_classify.call_count == 1

    response = await hass.services.async_call(
        DOMAIN, "list_unknown_signals", {}, blocking=True, return_response=True
    )
    (listed,) = response["signals"]
    assert listed["transmissions"] == 5
    assert listed["result"]["summary"] == "A PWM temperature sensor."

    # A signal with other timings is a new type
    for _ in range(3):
        await feed_at(hass, fake_serial, freezer, OTHER_UNKNOWN, 30)
    assert mock_classify.call_count == 2


async def test_unknown_signal_daily_limit(
    hass: HomeAssistant, fake_serial: FakeSerial, freezer, mock_classify
) -> None:
    await setup_entry(
        hass,
        **{CONF_API_KEY: "sk-ant-test", CONF_MAX_CLASSIFICATIONS_PER_DAY: 1},
    )
    for line in (UNKNOWN_A, OTHER_UNKNOWN) * 3:
        await feed_at(hass, fake_serial, freezer, line, 10)
    assert mock_classify.call_count == 1

    # Waits for the next reception after a day
    freezer.tick(86400)
    await feed_at(hass, fake_serial, freezer, OTHER_UNKNOWN, 10)
    assert mock_classify.call_count == 2


async def test_unknown_signal_without_api_key(
    hass: HomeAssistant, fake_serial: FakeSerial, freezer, mock_classify
) -> None:
    await setup_entry(hass)
    for _ in range(3):
        await feed_at(hass, fake_serial, freezer, UNKNOWN_A, 10)
    mock_classify.assert_not_called()

    # Still collected, to be listed
    response = await hass.services.async_call(
        DOMAIN, "list_unknown_signals", {}, blocking=True, return_response=True
    )
    (listed,) = response["signals"]
    assert listed["status"] == "collecting"
    with pytest.raises(ServiceValidationError, match="API key"):
        await hass.services.async_call(
            DOMAIN,
            "classify_unknown_signal",
            {"signal_id": listed["id"]},
            blocking=True,
            return_response=True,
        )


async def test_unknown_signal_retry(
    hass: HomeAssistant, fake_serial: FakeSerial, freezer, mock_classify
) -> None:
    await setup_entry(hass, **{CONF_API_KEY: "sk-ant-test"})
    mock_classify.side_effect = ClassificationError("overloaded")
    for _ in range(4):
        await feed_at(hass, fake_serial, freezer, UNKNOWN_A, 10)
    assert mock_classify.call_count == 1

    # Retried with the next reception an hour later
    mock_classify.side_effect = None
    freezer.tick(3600)
    await feed_at(hass, fake_serial, freezer, UNKNOWN_A, 10)
    assert mock_classify.call_count == 2
    response = await hass.services.async_call(
        DOMAIN, "list_unknown_signals", {}, blocking=True, return_response=True
    )
    assert response["signals"][0]["status"] == "classified"


async def test_unknown_signal_bad_api_key(
    hass: HomeAssistant, fake_serial: FakeSerial, freezer, mock_classify
) -> None:
    await setup_entry(hass, **{CONF_API_KEY: "sk-ant-test"})
    mock_classify.side_effect = AuthenticationFailed("Anthropic rejected the API key")
    for line in (UNKNOWN_A, OTHER_UNKNOWN) * 3:
        await feed_at(hass, fake_serial, freezer, line, 10)
    # Stops trying rather than failing for every signal type
    assert mock_classify.call_count == 1


async def test_unknown_signal_services(
    hass: HomeAssistant, fake_serial: FakeSerial, freezer, mock_classify
) -> None:
    await setup_entry(hass, **{CONF_API_KEY: "sk-ant-test", CONF_CLASSIFY_AUTOMATICALLY: False})
    for _ in range(3):
        await feed_at(hass, fake_serial, freezer, UNKNOWN_A, 10)
    mock_classify.assert_not_called()

    response = await hass.services.async_call(
        DOMAIN, "list_unknown_signals", {}, blocking=True, return_response=True
    )
    signal_id = response["signals"][0]["id"]
    response = await hass.services.async_call(
        DOMAIN,
        "classify_unknown_signal",
        {"signal_id": signal_id},
        blocking=True,
        return_response=True,
    )
    assert response["result"]["device"] == "Made-up sensor"
    mock_classify.assert_called_once()

    mock_classify.side_effect = ClassificationError("overloaded")
    with pytest.raises(HomeAssistantError, match="overloaded"):
        await hass.services.async_call(
            DOMAIN,
            "classify_unknown_signal",
            {"signal_id": signal_id},
            blocking=True,
            return_response=True,
        )

    await hass.services.async_call(
        DOMAIN, "forget_unknown_signal", {"signal_id": signal_id}, blocking=True
    )
    response = await hass.services.async_call(
        DOMAIN, "list_unknown_signals", {}, blocking=True, return_response=True
    )
    assert response["signals"] == []
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "forget_unknown_signal", {"signal_id": signal_id}, blocking=True
        )
