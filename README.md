# CC1101Duino

Arduino Nano + CC1101 firmware that receives and transmits sub-GHz ASK/OOK signals, plus a
[Home Assistant](https://www.home-assistant.io/) integration that decodes them. The firmware
is a trimmed-down [SIGNALDuino](https://github.com/RFD-FHEM/SIGNALDuino) (see `LIBRARIES`).

## Firmware

Built with [PlatformIO](https://platformio.org/) for `nanoatmega328new`: `pio run -t upload`.
Pin assignments and default receive frequency/modulation are in `include/config.h`.

The Home Assistant integration bundles a build of the firmware and can install it (see
[Firmware updates](#firmware-updates)), so after the first upload the firmware can be kept up to
date from Home Assistant. When changing the firmware, bump `FIRMWARE_VERSION` in
`include/version.h` and run `scripts/build_firmware.py`, which builds it into
`custom_components/cc1101duino/firmware/`. CI checks that the bundled build matches the source;
the toolchain and libraries are pinned in `platformio.ini` so that builds are reproducible.

## Home Assistant integration

### Installation

Through [HACS](https://hacs.xyz/): add this repository as a custom repository (type
*Integration*), install **CC1101Duino**, and restart Home Assistant.

Manually: copy `custom_components/cc1101duino` into your Home Assistant `config/custom_components/`.

Then add the integration under *Settings → Devices & services*. The device can be a local serial
port, or any [pyserial URL](https://pyserial.readthedocs.io/en/latest/url_handlers.html) such as
`socket://host:2000` for a CC1101Duino behind ser2net.
USB ports are stored by their stable `/dev/serial/by-id/...` path, so the device survives
renumbering, and *Reconfigure* on the integration lets you move an existing setup to a different
port without losing its sensors.

### Supported protocols

| Protocol | Frequency | Receive | Transmit |
| --- | --- | --- | --- |
| `lacrosse` — LaCrosse TX temperature / humidity sensors | 433.88 MHz | sensor entities | – |
| `nexus` — Nexus temperature / humidity sensors, also sold under other brands | 433.92 MHz | sensor entities | – |
| `minka_aire` — Minka Aire ceiling fan remotes | 304.2 MHz | `cc1101duino_signal` event | `cc1101duino.send_signal` |
| [SIGNALduino](#signalduino-protocols) — everything FHEM's SIGNALduino receives over ASK/OOK | mostly 433.92 MHz | sensor entities or `cc1101duino_signal` event | – |

The receiver listens on one frequency at a time (433.88 MHz by default); change it with
`cc1101duino.send_raw` and `line: F304.2`.

#### SIGNALduino protocols

Since the firmware is a SIGNALDuino, its messages are also run through a Python port of
[FHEM's SIGNALduino module](https://github.com/RFD-FHEM/RFFHEM): the protocol list and
demodulation (MS, MU and MC messages), and the FHEM modules that decode weather sensors:

| FHEM module | Sensors |
| --- | --- |
| `SD_WS` | Many weather sensors: Auriol, Bresser 7009994 / Temeo, EuroChron EFTH-800, Fine Offset WH2, TFA (30.3208, 30.3212, 30.3221, 30.3222, 30.3233, 30.3251, 30.3255, 35.1077), TS-FT002, Sainlogic, ADE WS1907, EMOS E06016, BBQ thermometers, ... |
| `CUL_TCM97001` | TCM 97001, ABS700, Prologue, Mebus, GT-WT-02, NC-WS, Rubicson, Auriol, KW9010, Ventus W044 / W132 / W174, PFR-130, ... |
| `Hideki` | Bresser, Cresta, TFA, Hama and other Hideki sensors (thermo/hygro, wind, rain) |
| `OREGON` | Oregon Scientific v1, v2 and v3 sensors |
| `SD_WS07`, `SD_WS09`, `CUL_TX`, `CUL_WS`, `SD_WS_Maverick` | Eurochron / Hama TS36E, WH1080 / CTW600, LaCrosse TX2 / TX3, ELV S300 / WS2000 / WS7000, Maverick ET-732 |

Messages of other SIGNALduino protocols, such as remotes, doorbells, switches and blinds (IT,
SD_UT, SD_BELL, Somfy, FS20, ...), fire a [`cc1101duino_signal` event](#events) with the
demodulated message as FHEM would pass it on. xFSK protocols (Bresser 5-in-1, LaCrosse IT+,
WMBus, ...) cannot be received by this firmware.

### Sensors

Each sensor that is heard gets a device with entities for what it reports: temperature,
humidity, pressure, wind, rain, UV, illuminance, and a battery warning. Since that includes your
neighbours' sensors, you can turn *Automatically add new sensors* off in the integration options
once yours have shown up, and delete unwanted devices. Many sensors pick a new ID when their
batteries are changed.

Many protocols have no checksum, so noise sometimes looks like a sensor. As in FHEM, a
SIGNALduino (or Nexus) sensor is only added once it has been heard a second time within three
minutes. SIGNALduino sensors are named by their FHEM device code, e.g. `SD_WS_27_TH_2`.

### Diagnostics

The CC1101Duino device itself has diagnostic entities: whether the serial connection is up, when
the last signal, last decoded signal and last unrecognized signal were received (the raw line,
its RSSI and what it decoded to are in their attributes), the RSSI of the last signal, counters
of received / decoded / unrecognized signals since startup, and the last status message from the
firmware. The firmware prints `RX initialized F=<MHz>;M=<n>` when it starts, so that message shows
which frequency it is listening on. The frequency is kept across restarts of the firmware.

### Firmware updates

The *Firmware* update entity of the CC1101Duino device shows the firmware version the device
reports and the version bundled with the integration, and offers to install the bundled firmware
when they differ. Firmware from before versions were introduced shows up as version `0`.
Installing resets the Arduino into its bootloader through DTR, like `avrdude -c arduino`, so it
needs a local serial port or an `rfc2217://` connection (ser2net in telnet mode). Over a plain
`socket://` connection the entity only shows the versions.

### Events

Decoded non-sensor signals, such as remote button presses, fire a `cc1101duino_signal` event:

```yaml
event_type: cc1101duino_signal
data:
  coder: minka_aire
  type: command
  id: "00101001"
  command: light_1
  config_entry_id: 01J...
```

SIGNALduino messages carry the protocol and the demodulated message. A message repeated within
two seconds fires only one event, since remotes send each press several times:

```yaml
event_type: cc1101duino_signal
data:
  coder: signalduino
  type: message
  protocol: "3"
  name: chip xx2260 / xx2262
  data: iF99726
  config_entry_id: 01J...
```

### Services

`cc1101duino.send_signal` encodes and transmits a signal. Besides `coder`, it takes the same
fields the event reports:

```yaml
action: cc1101duino.send_signal
data:
  coder: minka_aire
  id: "00101001"
  command: light  # off, low, medium, high, light (= light_1), light_2
```

`cc1101duino.send_raw` sends a raw firmware command, without the leading `^`:

| Command | Meaning |
| --- | --- |
| `F<MHz>` | Set receive frequency |
| `M<n>` | Set receive modulation (0 = 2-FSK, 1 = GFSK, 2 = ASK/OOK, 3 = 4-FSK, 4 = MSK) |
| `V` | Report the firmware version |
| `S;F=..;M=..;R=..;S=..;P0=..;D=..;` | Transmit pulses, as in [SIGNALDuino `SR`](https://github.com/RFD-FHEM/SIGNALDuino/wiki/Commands#sendraw--sr), plus `F` frequency, `M` modulation, `S` spacing between repeats (µs) |

If more than one CC1101Duino is set up, pass `config_entry_id` to either service.

### Adding a protocol

Protocols live in `custom_components/cc1101duino/protocol/`, which has no Home Assistant
dependencies. A coder (see `coders/lacrosse.py`) picks a packetizer that turns pulse timings into
bits, and decodes those bits into a signal dict. Register it in `coders/__init__.py`. Sensor
signals (`type: sensor`) with a `subtype` listed in `sensor.py` or `binary_sensor.py` become
entities, and everything else becomes an event.

The SIGNALduino port is in `protocol/signalduino/`. Its protocol list, `protocols.json`, is
generated from RFFHEM by `scripts/import_signalduino_protocols.pl`, and the functions it refers to
are in `functions.py`. FHEM client modules are ported in `clients/`, and `coder.py` maps their
readings to signals.

### Development

```sh
uv run --with-requirements requirements_test.txt pytest
```

`tests/fixtures/reference.json` holds output captured from the original Node-RED/TypeScript
decoder, which the Python port is tested against. `tests/fixtures/signalduino.json` holds FHEM's
test data, from raw firmware messages to readings, collected by
`scripts/import_signalduino_testdata.py`; the SIGNALduino port is tested against it.
