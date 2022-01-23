#pragma once

#include <Arduino.h>
#include <ELECHOUSE_CC1101_SRC_DRV.h>

#define CC1101_MAIN ELECHOUSE_cc1101

class CC1101Transceiver {
public:
  CC1101Transceiver(byte SCK, byte MISO, byte MOSI, byte CSN, byte GDO0, byte GDO2);
  void setup();
  void beginTransmission();
  void endTransmission(); 
  byte getTXPin();
  void select();

protected:
  byte SCK;
  byte MISO;
  byte MOSI;
  byte CSN;
  byte GDO0;
  byte GDO2;
  byte moduleNumber;
};

extern CC1101Transceiver cc1101;
