#include <Arduino.h>
#include <ELECHOUSE_CC1101_SRC_DRV.h>

#include "cc1101.h"
#include "config.h"
#include "serial_host.h"
#include "utils.h"
#include "rf.h"

HostSerial hostSerial(Serial);

HostSerial::HostSerial(HardwareSerial &serial) : CommandSerial(serial) {}

static int repeats = 20;
static int repeat_delay = 10;

static void _transmitData(const int txLen, const uint16_t *txDelays,
                   const byte *txData) {
  for (int i = 0; i < txLen; i++) {
    PIN_GDO0_PORT = txData[i];
    delayMicroseconds(txDelays[i]);
  }
}

static void _transmitDataEasy(const int txLen, const unsigned long txDelay,
                       const byte *txData) {
  for (int i = 0; i < txLen; i++) {
    PIN_GDO0_PORT = txData[i];
    delayMicroseconds(txDelay);
  }
}

static void transmitData(const String &buffer) {
  const int txLen = buffer.length() / 5;
  uint16_t *txDelays = new uint16_t[txLen];
  byte *txData = new byte[txLen];

  const byte dataOn = PIN_GDO0_ON;
  const byte dataOff = PIN_GDO0_OFF;
  for (int i = 0; i < txLen; i++) {
    txData[i] = (buffer[i * 5] == '1') ? dataOn : dataOff;
    txDelays[i] = hexInputToShort((i * 5) + 1, buffer);
  }

  beginTransmission();
  for (int i = 0; i < repeats; i++) {
    _transmitData(txLen, txDelays, txData);
    PIN_GDO0_PORT = dataOff;
    delayMicroseconds(repeat_delay);
  }
  endTransmission();

  delete[] txDelays;
  delete[] txData;
}

static void transmitDataEasy(const String &buffer) {
  const int txLen = buffer.length() - 4;
  const uint16_t txDelay = hexInputToShort(0, buffer);
  byte *txData = new byte[txLen];

  const byte dataOn = PIN_GDO0_ON;
  const byte dataOff = PIN_GDO0_OFF;
  for (int i = 0; i < txLen; i++) {
    txData[i] = (buffer[i + 4] == '1') ? dataOn : dataOff;
  }

  beginTransmission();
  for (int i = 0; i < repeats; i++) {
    _transmitDataEasy(txLen, txDelay, txData);
    PIN_GDO0_PORT = dataOff;
    delayMicroseconds(repeat_delay);
  }
  endTransmission();

  delete[] txData;
}

void HostSerial::handle() {
  this->buffer.toUpperCase();

  cc1101.select();

  switch (this->command) {
    case 'M': { // modulation
      int mod = this->buffer.toInt();
      tx_mod = mod;
      break;
    }
    case 'F': { // frequency (MHz)
      float mhz = this->buffer.toFloat();
      if (mhz > 0) {
        tx_freq = mhz;
      }
      break;
    }
    case 'T': { // repeat delay (time, us)
      repeat_delay = this->buffer.toInt();
      break;
    }
    case 'R': { // repeats
      repeats = this->buffer.toInt();
      break;
    }
    case 'E': { // "Easy" data
      transmitDataEasy(this->buffer);
      break;
    }
    case 'D': { // data
      transmitData(this->buffer);
      break;
    }
    case '$':
    case '>': {
      break;
    }
    default: {
      this->reply(F("BAD Unknown command"));
      return;
    }
  }

  this->reply(F("OK Done"));
}
