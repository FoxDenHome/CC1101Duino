"""Serial connection to a CC1101Duino."""

from __future__ import annotations

import asyncio
import logging

import serial
import serial_asyncio_fast
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    BAUDRATE,
    COMMAND_TIMEOUT,
    EVENT_SIGNAL,
    RECONNECT_INTERVAL,
    signal_connection,
    signal_decoded,
)
from .protocol import LineCoder, NotSupportedError, Signal

_LOGGER = logging.getLogger(__name__)

LINE_START = "^"
REPLY_PREFIX = "^$"
ECHO_PREFIX = "^<"


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
        self._writer: asyncio.StreamWriter | None = None
        self._reader: asyncio.StreamReader | None = None
        self._send_lock = asyncio.Lock()
        self._reply: asyncio.Future[str] | None = None

    async def async_connect(self) -> None:
        """Connect once, raising on failure."""
        self._reader, self._writer = await async_open(self.device)
        self._set_connected(True)
        _LOGGER.info("Connected to CC1101Duino at %s", self.device)

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
        self._close()

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
            _LOGGER.info("CC1101Duino: %s", line[len(ECHO_PREFIX) :])
            return

        for signal in self.coder.process_signal_line(line):
            _LOGGER.debug("Decoded: %s", signal)
            async_dispatcher_send(self.hass, signal_decoded(self.entry_id), signal)
            # Sensor readings become entities; everything else (remote buttons, ...) is an event
            if signal.get("type") != "sensor":
                self.hass.bus.async_fire(EVENT_SIGNAL, {**signal, "config_entry_id": self.entry_id})

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

        # Replies are the command letter followed by "OK ..." or "BAD ..."
        if reply[1:].startswith("BAD"):
            raise HomeAssistantError(f"{self.device} rejected {line.strip()}: {reply[1:]}")

    @callback
    def _set_connected(self, connected: bool) -> None:
        if connected == self.connected:
            return
        self.connected = connected
        async_dispatcher_send(self.hass, signal_connection(self.entry_id))

    @callback
    def _close(self) -> None:
        if self._writer is not None:
            self._writer.close()
        self._writer = None
        self._reader = None
        if self._reply is not None and not self._reply.done():
            self._reply.set_exception(HomeAssistantError(f"Connection to {self.device} lost"))
        self._set_connected(False)
