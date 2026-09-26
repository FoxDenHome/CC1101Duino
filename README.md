# CC1101Duino

Arduino Nano + CC1101 firmware that receives and transmits sub-GHz ASK/OOK signals, plus a
[Home Assistant](https://www.home-assistant.io/) integration that decodes them. The firmware
is a trimmed-down [SIGNALDuino](https://github.com/RFD-FHEM/SIGNALDuino) (see `LIBRARIES`).

## Firmware

Built with [PlatformIO](https://platformio.org/) for `nanoatmega328new`: `pio run -t upload`.
Pin assignments and default receive frequency/modulation are in `include/config.h`.

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
| `minka_aire` — Minka Aire ceiling fan remotes | 304.2 MHz | `cc1101duino_signal` event | `cc1101duino.send_signal` |

The receiver listens on one frequency at a time (433.88 MHz by default); change it with
`cc1101duino.send_raw` and `line: F304.2`.

### Sensors

Each sensor that is heard gets a device with temperature and/or humidity entities. Since that
includes your neighbours' sensors, you can turn *Automatically add new sensors* off in the
integration options once yours have shown up, and delete unwanted devices. LaCrosse sensors pick
a new ID when their batteries are changed.

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
| `S;F=..;M=..;R=..;S=..;P0=..;D=..;` | Transmit pulses, as in [SIGNALDuino `SR`](https://github.com/RFD-FHEM/SIGNALDuino/wiki/Commands#sendraw--sr), plus `F` frequency, `M` modulation, `S` spacing between repeats (µs) |

If more than one CC1101Duino is set up, pass `config_entry_id` to either service.

### Adding a protocol

Protocols live in `custom_components/cc1101duino/protocol/`, which has no Home Assistant
dependencies. A coder (see `coders/lacrosse.py`) picks a packetizer that turns pulse timings into
bits, and decodes those bits into a signal dict. Register it in `coders/__init__.py`. Sensor
signals (`type: sensor`) with a `subtype` listed in `sensor.py` become entities, and everything
else becomes an event.

### Development

```sh
uv run --with-requirements requirements_test.txt pytest
```

`tests/fixtures/reference.json` holds output captured from the original Node-RED/TypeScript
decoder, which the Python port is tested against.
