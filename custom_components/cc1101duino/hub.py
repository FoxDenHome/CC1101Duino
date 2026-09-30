"""Serial connection to a CC1101Duino."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

import serial
import serial_asyncio_fast
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .const import (
    AUTOCREATE_MIN_GAP,
    AUTOCREATE_WINDOW,
    BAUDRATE,
    COMMAND_TIMEOUT,
    DOMAIN,
    EVENT_SIGNAL,
    LEGACY_FIRMWARE_VERSION,
    READY_MESSAGE,
    RECONNECT_INTERVAL,
    VERSION_QUERY_DELAY,
    signal_connection,
    signal_decoded,
    signal_diagnostics,
)
from .firmware import FlashError, can_flash, flash
from .protocol import LineCoder, NotSupportedError, Signal

if TYPE_CHECKING:
    from .classifier import UnknownSignalClassifier

_LOGGER = logging.getLogger(__name__)

LINE_START = "^"
REPLY_PREFIX = "^$"
ECHO_PREFIX = "^<"
SIGNAL_PREFIX = "^S"


@dataclass
class ReceivedSignal:
    """One radio signal reported by the firmware, and what it decoded to."""

    time: datetime
    line: str
    rssi: int | None
    signals: list[Signal] = field(default_factory=list)


@dataclass
class HubDiagnostics:
    """What the hub has heard since it was set up."""

    received: int = 0
    decoded: int = 0
    unrecognized: int = 0
    last_received: ReceivedSignal | None = None
    last_decoded: ReceivedSignal | None = None
    last_unrecognized: ReceivedSignal | None = None
    firmware_message: str | None = None


RSSI_REGEX = re.compile(r";R=(\d+);")
READY_VERSION_REGEX = re.compile(re.escape(READY_MESSAGE) + r" V=([^;]+);")

# Own decoders without a real checksum, whose sensors also need a second reception
UNCHECKED_CODERS = {"nexus"}


def _needs_confirmation(signal: Signal) -> bool:
    return "protocol" in signal or signal.get("coder") in UNCHECKED_CODERS


def _rssi_dbm(line: str) -> int | None:
    """The firmware reports the driver's signed dBm value truncated to a uint8."""
    if (match := RSSI_REGEX.search(line)) is None:
        return None
    rssi = int(match.group(1))
    return rssi - 256 if rssi >= 128 else rssi


async def async_open(device: str) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Open the device, which may be a local port or a pyserial URL (socket://, rfc2217://)."""
    return await serial_asyncio_fast.open_serial_connection(url=device, baudrate=BAUDRATE)


class CC1101DuinoHub:
    """Reads and decodes received signals, and sends commands."""

    def __init__(self, hass: HomeAssistant, entry_id: str, device: str) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.device = device
        self.coder = LineCoder()
        self.connected = False
        self.firmware_version: str | None = None
        self.diagnostics = HubDiagnostics()
        self.classifier: UnknownSignalClassifier | None = None
        # SIGNALduino sensors confirmed by a second reception, and when others were first heard
        self._confirmed: set[tuple[str, str]] = set()
        self._sightings: dict[tuple[str, str], float] = {}
        self._writer: asyncio.StreamWriter | None = None
        self._reader: asyncio.StreamReader | None = None
        self._send_lock = asyncio.Lock()
        self._reply: asyncio.Future[str] | None = None
        self._run_task: asyncio.Task[None] | None = None
        self._version_task: asyncio.Task[None] | None = None

    @property
    def can_flash(self) -> bool:
        return can_flash(self.device)

    async def async_connect(self) -> None:
        """Connect once, raising on failure."""
        self._reader, self._writer = await async_open(self.device)
        self._set_connected(True)
        _LOGGER.info("Connected to CC1101Duino at %s", self.device)
        self._set_firmware_version(None)
        self._version_task = self.hass.async_create_background_task(
            self._async_query_version(), f"{DOMAIN} {self.device} version"
        )

    @callback
    def start(self) -> None:
        """Start reading from the device, after async_connect succeeded once."""
        self._run_task = self.hass.async_create_background_task(
            self.async_run(), f"{DOMAIN} {self.device}"
        )

    async def async_run(self) -> None:
        """Read lines forever, reconnecting whenever the connection drops."""
        while True:
            try:
                if self._reader is None:
                    await self.async_connect()
                assert self._reader is not None
                await self._async_read_lines(self._reader)
                _LOGGER.warning("Connection to %s closed", self.device)
            except (OSError, serial.SerialException) as err:
                if self.connected:
                    _LOGGER.warning("Connection to %s lost: %s", self.device, err)
                else:
                    _LOGGER.debug("Reconnecting to %s failed: %s", self.device, err)
            self._close()
            await asyncio.sleep(RECONNECT_INTERVAL)

    async def async_close(self) -> None:
        tasks = [task for task in (self._run_task, self._version_task) if task is not None]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.wait(tasks)
        self._run_task = self._version_task = None
        self._close()

    async def _async_query_version(self) -> None:
        """Ask for the version when the device did not print it on connecting."""
        await asyncio.sleep(VERSION_QUERY_DELAY)
        if self.firmware_version is not None:
            return
        try:
            reply = await self._async_command("V")
        except HomeAssistantError as err:
            _LOGGER.debug("Querying the firmware version failed: %s", err)
            return
        if reply.startswith("OK "):
            self._set_firmware_version(reply.removeprefix("OK "))
        else:
            # Firmware without versions rejects the command
            self._set_firmware_version(LEGACY_FIRMWARE_VERSION)

    async def async_install_firmware(self, image: bytes, progress: Callable[[int], None]) -> None:
        """Flash firmware, pausing the connection meanwhile.

        progress is called from a worker thread with the percentage done.
        """
        if not self.can_flash:
            raise HomeAssistantError(
                f"Cannot flash {self.device}: starting the bootloader needs a local serial port "
                "or rfc2217:// connection"
            )
        async with self._send_lock:
            await self.async_close()
            try:
                await self.hass.async_add_executor_job(flash, self.device, image, progress)
            except (FlashError, OSError, serial.SerialException) as err:
                raise HomeAssistantError(f"Flashing {self.device} failed: {err}") from err
            finally:
                self.start()

    async def _async_read_lines(self, reader: asyncio.StreamReader) -> None:
        while raw := await reader.readline():
            line = raw.decode("ascii", errors="replace").strip()
            if line:
                self._handle_line(line)

    @callback
    def _handle_line(self, line: str) -> None:
        _LOGGER.debug("Received: %s", line)

        if line.startswith(REPLY_PREFIX):
            if self._reply is not None and not self._reply.done():
                self._reply.set_result(line[len(REPLY_PREFIX) :])
            return

        if line.startswith(ECHO_PREFIX):
            message = line[len(ECHO_PREFIX) :]
            _LOGGER.info("CC1101Duino: %s", message)
            if message.startswith(READY_MESSAGE):
                match = READY_VERSION_REGEX.match(message)
                self._set_firmware_version(match.group(1) if match else LEGACY_FIRMWARE_VERSION)
            self.diagnostics.firmware_message = message
            async_dispatcher_send(self.hass, signal_diagnostics(self.entry_id))
            return

        if not line.startswith(SIGNAL_PREFIX):
            _LOGGER.debug("Ignoring unknown line: %s", line)
            return

        signals = self.coder.process_signal_line(line)
        self._record_signal(ReceivedSignal(dt_util.utcnow(), line, _rssi_dbm(line), signals))
        self._note_sightings(signals)

        for signal in signals:
            _LOGGER.debug("Decoded: %s", signal)
            if signal.pop("repeat", False):
                continue
            async_dispatcher_send(self.hass, signal_decoded(self.entry_id), signal)
            # Sensor readings become entities; everything else (remote buttons, ...) is an event
            if signal.get("type") != "sensor":
                self.hass.bus.async_fire(EVENT_SIGNAL, {**signal, "config_entry_id": self.entry_id})

    def is_confirmed(self, signal: Signal) -> bool:
        """Whether a new sensor may be added for this signal.

        Many protocols have no checksum, so like FHEM's autocreate a sensor of such a
        protocol is only added once it was heard again within a few minutes.
        """
        if not _needs_confirmation(signal):
            return True
        return (signal["coder"], signal["id"]) in self._confirmed

    @callback
    def _note_sightings(self, signals: list[Signal]) -> None:
        now = time.monotonic()
        self._sightings = {
            device: first
            for device, first in self._sightings.items()
            if now - first <= AUTOCREATE_WINDOW
        }
        devices = {
            (signal["coder"], signal["id"])
            for signal in signals
            if signal.get("type") == "sensor" and _needs_confirmation(signal)
        }
        for device in devices - self._confirmed:
            first = self._sightings.get(device)
            if first is None:
                self._sightings[device] = now
            # Repeats within one transmission do not count as a second reception
            elif now - first >= AUTOCREATE_MIN_GAP:
                self._confirmed.add(device)
                del self._sightings[device]

    @callback
    def _record_signal(self, received: ReceivedSignal) -> None:
        diag = self.diagnostics
        diag.received += 1
        diag.last_received = received
        if received.signals:
            diag.decoded += 1
            diag.last_decoded = received
            if self.classifier is not None:
                self.classifier.async_add_decoded(received)
        else:
            _LOGGER.debug("Unrecognized: %s", received.line)
            diag.unrecognized += 1
            diag.last_unrecognized = received
            if self.classifier is not None:
                self.classifier.async_add(received)
        async_dispatcher_send(self.hass, signal_diagnostics(self.entry_id))

    async def async_send_signal(self, signal: Signal) -> None:
        """Encode a signal dict and transmit it."""
        try:
            line = self.coder.create_signal_line(signal)
        except NotSupportedError as err:
            raise HomeAssistantError(f"Cannot encode signal {signal}: {err}") from err
        await self.async_send_line(line)

    async def async_send_line(self, line: str) -> None:
        """Send one command line and wait for the firmware to acknowledge it.

        The firmware blocks while transmitting and its serial buffer is tiny, so
        commands are strictly sequential.
        """
        reply = await self._async_command(line)
        # Replies are the command letter followed by "OK ..." or "BAD ..."
        if reply.startswith("BAD"):
            raise HomeAssistantError(f"{self.device} rejected {line.strip()}: {reply}")

    async def _async_command(self, line: str) -> str:
        """Send one command line, returning the reply after the command letter."""
        if not line.startswith(LINE_START):
            line = LINE_START + line
        line = line.rstrip("\r\n") + "\n"

        async with self._send_lock:
            if self._writer is None:
                raise HomeAssistantError(f"Not connected to {self.device}")

            self._reply = self.hass.loop.create_future()
            try:
                _LOGGER.debug("Sending: %s", line.strip())
                self._writer.write(line.encode("ascii"))
                await self._writer.drain()
                async with asyncio.timeout(COMMAND_TIMEOUT):
                    reply = await self._reply
            except TimeoutError as err:
                raise HomeAssistantError(f"No reply from {self.device} to {line.strip()}") from err
            finally:
                self._reply = None
        return reply[1:]

    @callback
    def _set_connected(self, connected: bool) -> None:
        if connected == self.connected:
            return
        self.connected = connected
        async_dispatcher_send(self.hass, signal_connection(self.entry_id))

    @callback
    def _set_firmware_version(self, version: str | None) -> None:
        if version == self.firmware_version:
            return
        self.firmware_version = version
        async_dispatcher_send(self.hass, signal_diagnostics(self.entry_id))

    @callback
    def _close(self) -> None:
        if self._writer is not None:
            self._writer.close()
        self._writer = None
        self._reader = None
        if self._reply is not None and not self._reply.done():
            self._reply.set_exception(HomeAssistantError(f"Connection to {self.device} lost"))
        self._set_connected(False)
