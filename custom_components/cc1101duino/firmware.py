"""The firmware bundled with the integration, and flashing it through the Arduino's bootloader."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import serial

from .const import BAUDRATE, READY_MESSAGE

FIRMWARE_FILE = Path(__file__).parent / "firmware" / "nanoatmega328new.hex"
# The version is compiled into the ready message, whose string is stored as is in flash
VERSION_REGEX = re.compile(re.escape(READY_MESSAGE).encode() + rb" V=([^;\x00]+);")

# Arduino Nano (ATmega328P) with the Optiboot bootloader, as avrdude -c arduino programs it
SIGNATURE = b"\x1e\x95\x0f"
PAGE_SIZE = 128
FLASH_SIZE = 30720

STK_OK = 0x10
STK_INSYNC = 0x14
CRC_EOP = 0x20
STK_GET_SYNC = 0x30
STK_ENTER_PROGMODE = 0x50
STK_LEAVE_PROGMODE = 0x51
STK_LOAD_ADDRESS = 0x55
STK_PROG_PAGE = 0x64
STK_READ_PAGE = 0x74
STK_READ_SIGN = 0x75
MEMTYPE_FLASH = ord("F")

SYNC_ATTEMPTS = 10


class FlashError(Exception):
    """The bootloader did not respond as expected."""


@dataclass(frozen=True)
class Firmware:
    version: str
    image: bytes


def parse_hex(text: str) -> bytes:
    """The flash contents of an Intel HEX file, starting at address 0."""
    data = bytearray()
    base = 0
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            record = bytes.fromhex(line.removeprefix(":"))
        except ValueError as err:
            raise ValueError(f"Invalid record on line {number}") from err
        if not line.startswith(":") or len(record) != record[0] + 5 or sum(record) & 0xFF:
            raise ValueError(f"Invalid record on line {number}")
        kind, payload = record[3], record[4:-1]
        if kind == 0x00:
            address = base + int.from_bytes(record[1:3])
            end = address + len(payload)
            data.extend(b"\xff" * (end - len(data)))
            data[address:end] = payload
        elif kind == 0x01:
            break
        elif kind == 0x02:
            base = int.from_bytes(payload) << 4
        elif kind == 0x04:
            base = int.from_bytes(payload) << 16
        # 0x03 and 0x05 are start addresses, which do not matter for flashing
    return bytes(data)


@cache
def load_firmware() -> Firmware:
    """Read the bundled firmware. Does file I/O, and is cached afterwards."""
    image = parse_hex(FIRMWARE_FILE.read_text())
    if (match := VERSION_REGEX.search(image)) is None:
        raise ValueError(f"No firmware version found in {FIRMWARE_FILE}")
    return Firmware(match.group(1).decode("ascii"), image)


def can_flash(device: str) -> bool:
    """Whether the bootloader can be started, which needs control over DTR.

    That rules out socket:// connections to ser2net, but not RFC 2217 ones.
    """
    return "://" not in device or device.startswith("rfc2217://")


def flash(device: str, image: bytes, progress: Callable[[int], None]) -> None:
    """Write an image to the device and verify it. Blocking."""
    if len(image) > FLASH_SIZE:
        raise FlashError(f"Firmware of {len(image)} bytes does not fit into {FLASH_SIZE} bytes")
    with serial.serial_for_url(device, baudrate=BAUDRATE, timeout=1) as port:
        Programmer(port).flash(image, progress)


class Programmer:
    """Speaks the STK500v1 subset that Optiboot implements."""

    def __init__(self, port: serial.SerialBase) -> None:
        self._port = port

    def flash(self, image: bytes, progress: Callable[[int], None]) -> None:
        self.reset()
        self.sync()
        signature = self.command(bytes([STK_READ_SIGN]), 3)
        if signature != SIGNATURE:
            raise FlashError(f"Unexpected device signature {signature.hex()}, not an ATmega328P")
        self.command(bytes([STK_ENTER_PROGMODE]))

        pages = [
            (address, image[address : address + PAGE_SIZE].ljust(PAGE_SIZE, b"\xff"))
            for address in range(0, len(image), PAGE_SIZE)
        ]
        # Writing and verifying each count for half of the progress
        steps = 2 * len(pages)
        for step, (address, page) in enumerate(pages):
            self.load_address(address)
            self.command(bytes([STK_PROG_PAGE, 0, PAGE_SIZE, MEMTYPE_FLASH]) + page)
            progress(100 * step // steps)
        for step, (address, page) in enumerate(pages, len(pages)):
            self.load_address(address)
            if self.command(bytes([STK_READ_PAGE, 0, PAGE_SIZE, MEMTYPE_FLASH]), PAGE_SIZE) != page:
                raise FlashError(f"Verification failed at address {address:#06x}")
            progress(100 * step // steps)

        # Optiboot starts the new firmware right after this
        self.command(bytes([STK_LEAVE_PROGMODE]))
        progress(100)

    def reset(self) -> None:
        """Reset the Arduino into its bootloader through DTR/RTS, like avrdude."""
        self._port.dtr = False
        self._port.rts = False
        time.sleep(0.25)
        self._port.dtr = True
        self._port.rts = True
        time.sleep(0.05)
        self._port.reset_input_buffer()

    def sync(self) -> None:
        for _ in range(SYNC_ATTEMPTS):
            self._port.write(bytes([STK_GET_SYNC, CRC_EOP]))
            if self._port.read(2) == bytes([STK_INSYNC, STK_OK]):
                return
            self._port.reset_input_buffer()
        raise FlashError("No response from the bootloader")

    def load_address(self, address: int) -> None:
        word = address // 2
        self.command(bytes([STK_LOAD_ADDRESS, word & 0xFF, word >> 8]))

    def command(self, command: bytes, response_length: int = 0) -> bytes:
        self._port.write(command + bytes([CRC_EOP]))
        response = self._port.read(response_length + 2)
        if (
            len(response) != response_length + 2
            or response[0] != STK_INSYNC
            or response[-1] != STK_OK
        ):
            raise FlashError(f"Bad response to command {command[0]:#04x}: {response.hex()}")
        return response[1:-1]
