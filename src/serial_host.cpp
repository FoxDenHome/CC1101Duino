#include <Arduino.h>
#include <ELECHOUSE_CC1101_SRC_DRV.h>

#include "cc1101.h"
#include "config.h"
#include "serial_host.h"
#include "utils.h"
#include "rf.h"

HostSerial hostSerial(Serial);

HostSerial::HostSerial(HardwareSerial &serial) : CommandSerial(serial) {}

static bool transmitData(const String& buffer) {
  const char* buf = buffer.c_str();
  const byte len = buffer.length();
  byte offset = 0;

  const byte dataOn = PIN_GDO0_ON;
  const byte dataOff = PIN_GDO0_OFF;

  char key = 0;
  char key_val = 0;

  byte val_start = 0;

  float frequency = DEFAULT_FREQUENCY;
  byte modulation = DEFAULT_MODULATION;
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

  beginTransmission(frequency, modulation);
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
    case 'S': { // Transmit data, same format as SIGNALDuino raw ( https://github.com/RFD-FHEM/SIGNALDuino/wiki/Commands#sendraw--sr ), plus F=frequency, M=modulation, S=repeat spacing
      if (!transmitData(this->buffer)) {
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
