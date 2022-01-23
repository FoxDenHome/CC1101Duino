#pragma once

#include <Arduino.h>

#define hexCharToNum(c) ((c <= '9') ? c - '0' : c - '7')
inline byte hexInputToByte(const byte offset, const String &data) {
  const byte msn = data[offset];
  const byte lsn = data[offset + 1];
  return (hexCharToNum(msn) << 4) + hexCharToNum(lsn);
}

inline uint16_t hexInputToShort(const byte offset, const String &data) {
  const uint16_t b1 = data[offset];
  const uint16_t b2 = data[offset + 1];
  const uint16_t b3 = data[offset + 2];
  const uint16_t b4 = data[offset + 3];
  return (hexCharToNum(b1) << 12) + (hexCharToNum(b2) << 8) +
         (hexCharToNum(b3) << 4) + hexCharToNum(b4);
}

inline int hexInputToStr(const String &data, byte *out) {
  int imax = data.length() / 2;
  for (int i = 0; i < imax; i++) {
    out[i] = hexInputToByte(i * 2, data);
  }
  return imax;
}
