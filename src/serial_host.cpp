#include <Arduino.h>

#include "cc1101.h"
#include "config.h"
#include "serial_host.h"
#include "utils.h"

HostSerial hostSerial(Serial);

HostSerial::HostSerial(HardwareSerial &serial) : CommandSerial(serial) {}

static int repeats = 20;
static int repeat_delay = 10;

void _transmitData(const int txLen, const uint16_t *txDelays,
                   const byte *txData) {
  for (int i = 0; i < txLen; i++) {
    PIN_GDO0_PORT = txData[i];
    delayMicroseconds(txDelays[i]);
  }
}

void _transmitDataEasy(const int txLen, const unsigned long txDelay,
                       const byte *txData) {
  for (int i = 0; i < txLen; i++) {
    PIN_GDO0_PORT = txData[i];
    delayMicroseconds(txDelay);
  }
}

void transmitData(const String &buffer) {
  const int txLen = buffer.length() / 5;
  uint16_t *txDelays = new uint16_t[txLen];
  byte *txData = new byte[txLen];

  const byte dataOn = PIN_GDO0_ON;
  const byte dataOff = PIN_GDO0_OFF;
  for (int i = 0; i < txLen; i++) {
    txData[i] = (buffer[i * 5] == '1') ? dataOn : dataOff;
    txDelays[i] = hexInputToShort((i * 5) + 1, buffer);
  }

  cc1101.beginTransmission();
  for (int i = 0; i < repeats; i++) {
    _transmitData(txLen, txDelays, txData);
    PIN_GDO0_PORT = dataOff;
    delayMicroseconds(repeat_delay);
  }
  cc1101.endTransmission();

  delete[] txDelays;
  delete[] txData;
}

void transmitDataEasy(const String &buffer) {
  const int txLen = buffer.length() - 4;
  const uint16_t txDelay = hexInputToShort(0, buffer);
  byte *txData = new byte[txLen];

  const byte dataOn = PIN_GDO0_ON;
  const byte dataOff = PIN_GDO0_OFF;
  for (int i = 0; i < txLen; i++) {
    txData[i] = (buffer[i + 4] == '1') ? dataOn : dataOff;
  }

  cc1101.beginTransmission();
  for (int i = 0; i < repeats; i++) {
    _transmitDataEasy(txLen, txDelay, txData);
    PIN_GDO0_PORT = dataOff;
    delayMicroseconds(repeat_delay);
  }
  cc1101.endTransmission();

  delete[] txData;
}

void HostSerial::handle() {
  int tmpi;
  float tmpf;
  this->buffer.toUpperCase();

  cc1101.select();

  switch (this->command) {
  case 'M': // modulation
    tmpi = this->buffer.toInt();
    CC1101_MAIN.setModulation(tmpi);
    break;
  case 'F': // frequency (MHz)
    tmpf = this->buffer.toFloat();
    CC1101_MAIN.setMHZ(tmpf);
    break;
  case 'T': // repeat delay (time, us)
    repeat_delay = this->buffer.toInt();
    break;
  case 'R': // repeats
    repeats = this->buffer.toInt();
    break;
  case 'E': // "Easy" data
    transmitDataEasy(this->buffer);
    break;
  case 'D': // data
    transmitData(this->buffer);
    break;
  default:
    this->reply(F("BAD Unknown command"));
    return;
  }

  this->reply(F("OK Done"));
}
