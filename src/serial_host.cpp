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

static bool transmitDataSD(const String& buffer) {
  const char* buf = buffer.c_str();
  const byte len = buffer.length();
  byte offset = 0;

  const byte dataOn = PIN_GDO0_ON;
  const byte dataOff = PIN_GDO0_OFF;

  char key = 0;
  char key_val = 0;

  byte val_start = 0;

  float frequency = 433.88; // Default
  byte modulation = 2; // ASK/OOK
  uint32_t packets[10];
  byte packet_pincfg[10];
  byte data[128];
  byte data_length = 0;
  int repeats = 5;
  int repeat_delay = 1000;

  for (byte offset = 0; offset < len; offset++) {
    const char c = buf[offset];
    switch (c) {
      case ';': {
        if (!val_start) {
          if (!key && !key_val) {
            break;
          }
          return false;
        }

        String val = buffer.substring(val_start, offset);
        byte val_length = val.length();

        switch (key) {
          case 'P': { // P# = Time for #
            byte key_val_normalized = key_val - '0';
            if (key_val_normalized > 10) {
              return false;
            }

            int val_int = val.toInt();

            if (val_int < 0) {
              packet_pincfg[key_val_normalized] = dataOff;
              val_int = -val_int;
            } else {
              packet_pincfg[key_val_normalized] = dataOn;
            }

            packets[key_val_normalized] = val_int;
            break;
          }
          case 'R': // R = Repeats
            repeats = val.toInt();
            break;
          case 'S': // S = Spacing between repeats
            repeat_delay = val.toInt();
            break;
          case 'D': // D = Data
            if (val_length > sizeof(data)) {
              return false;
            }
            for (byte i = 0; i < val_length; i++) {
              data[i] = val.charAt(i) - '0';
              if (data[i] >= 10) {
                return false;
              }
            }
            data_length = val_length;
            break;
          case 'F': // F = Frequency
            frequency = val.toFloat();
            break;
          case 'M': // M = Modulation
            modulation = val.toInt();
            break;
        }

        key = 0;
        key_val = 0;
        val_start = 0;
        break;
      }
      case '=':
        if (!key || !key_val || val_start) {
          return false;
        }
        val_start = offset + 1;
        break;
      default:
        if (val_start) {
          break;
        }
        if (key) {
          if (!key_val) {
            key_val = c;
            break;
          }
          return false;
        }
        key = c;
        if (key != 'P') {
          key_val = 0xFF;
        }
    }
  }

  tx_freq = frequency;
  tx_mod = modulation;

  beginTransmission();
  for (byte i = 0; i < repeats; i++) {
    for (offset = 0; offset < data_length; offset++) {
      const byte d = data[offset];
      PIN_GDO0_PORT = packet_pincfg[d];
      delayMicroseconds(packets[d]);
    }
    PIN_GDO0_PORT = dataOff;
    delayMicroseconds(repeat_delay);
  }
  endTransmission();

  return true;
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
    case 'S': {
      if (!transmitDataSD(this->buffer)) {
        this->reply(F("BAD Invalid parameters"));
        return;
      }
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
