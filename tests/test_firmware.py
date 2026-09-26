"""Tests of the bundled firmware and the Optiboot flasher against a simulated bootloader."""

from pathlib import Path
from unittest.mock import patch

import pytest

from custom_components.cc1101duino.firmware import (
    PAGE_SIZE,
    FlashError,
    Programmer,
    can_flash,
    flash,
    load_firmware,
    parse_hex,
)

VERSION_HEADER = Path(__file__).parent.parent / "include" / "version.h"


class FakeOptiboot:
    """A serial port with an ATmega328P running Optiboot behind it."""

    def __init__(self, signature: bytes = b"\x1e\x95\x0f", resettable: bool = True) -> None:
        self.signature = signature
        self.resettable = resettable
        self.flash = bytearray(b"\xff" * 32768)
        self._dtr = True
        self.rts = True
        self.in_bootloader = False
        self.left_bootloader = False
        self.corrupt_address: int | None = None
        self._address = 0
        self._output = bytearray()

    @property
    def dtr(self) -> bool:
        return self._dtr

    @dtr.setter
    def dtr(self, value: bool) -> None:
        # Asserting DTR after releasing it resets the Arduino into Optiboot
        if value and not self._dtr and self.resettable:
            self.in_bootloader = True
        self._dtr = value

    def reset_input_buffer(self) -> None:
        self._output.clear()

    def read(self, size: int) -> bytes:
        data = bytes(self._output[:size])
        del self._output[:size]
        return data

    def write(self, data: bytes) -> None:
        if not self.in_bootloader:
            return
        assert data[-1] == 0x20
        command, args = data[0], data[1:-1]
        reply = b""
        if command == 0x75:
            reply = self.signature
        elif command == 0x55:
            self._address = int.from_bytes(args[:2], "little") * 2
        elif command == 0x64:
            assert args[:3] == bytes([0, PAGE_SIZE, ord("F")])
            assert self._address % PAGE_SIZE == 0
            self.flash[self._address : self._address + PAGE_SIZE] = args[3:]
            if self._address == self.corrupt_address:
                self.flash[self._address] ^= 0xFF
        elif command == 0x74:
            reply = bytes(self.flash[self._address : self._address + args[1]])
        elif command == 0x51:
            self.in_bootloader = False
            self.left_bootloader = True
        self._output += b"\x14" + reply + b"\x10"


def test_parse_hex() -> None:
    hex_file = """
:0400000001020304F2
:02000004000AF0
:020010000506E3
:00000001FF
:0400000009090909D8
"""
    image = parse_hex(hex_file)
    assert image[:4] == b"\x01\x02\x03\x04"
    assert image[0xA0010:] == b"\x05\x06"
    assert image[4:8] == b"\xff" * 4

    with pytest.raises(ValueError, match="line 2"):
        parse_hex(":0400000001020304F2\n:0400000001020304F0")


def test_bundled_firmware() -> None:
    firmware = load_firmware()
    version = VERSION_HEADER.read_text().split('#define FIRMWARE_VERSION "')[1].split('"')[0]
    assert firmware.version == version
    assert 1000 < len(firmware.image) < 30720


def test_can_flash() -> None:
    assert can_flash("/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0")
    assert can_flash("rfc2217://host:2217")
    assert not can_flash("socket://host:2000")


def test_flash() -> None:
    image = bytes(range(256)) * 3 + b"\x01\x02"
    port = FakeOptiboot()
    progress: list[int] = []
    with patch("time.sleep"):
        Programmer(port).flash(image, progress.append)

    assert port.flash[: len(image)] == image
    assert port.flash[len(image) :] == b"\xff" * (32768 - len(image))
    assert port.left_bootloader
    assert progress == sorted(progress)
    assert progress[0] == 0
    assert progress[-1] == 100


def test_flash_wrong_device() -> None:
    port = FakeOptiboot(signature=b"\x1e\x95\x14")
    with patch("time.sleep"), pytest.raises(FlashError, match="signature"):
        Programmer(port).flash(b"\x00", lambda _: None)


def test_flash_verification_fails() -> None:
    port = FakeOptiboot()
    port.corrupt_address = PAGE_SIZE
    with patch("time.sleep"), pytest.raises(FlashError, match="0x0080"):
        Programmer(port).flash(b"\x00" * 2 * PAGE_SIZE, lambda _: None)
    assert not port.left_bootloader


def test_flash_no_bootloader() -> None:
    # Without DTR, as over a socket, the Arduino never enters its bootloader
    port = FakeOptiboot(resettable=False)
    with patch("time.sleep"), pytest.raises(FlashError, match="No response"):
        Programmer(port).flash(b"\x00", lambda _: None)


def test_flash_too_large() -> None:
    with pytest.raises(FlashError, match="does not fit"):
        flash("/dev/null", b"\x00" * 30721, lambda _: None)
