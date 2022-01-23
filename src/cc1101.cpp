#include <Arduino.h>
#include <ELECHOUSE_CC1101_SRC_DRV.h>

#include "cc1101.h"
#include "config.h"

CC1101Transceiver cc1101(PIN_CLK, PIN_MISO, PIN_MOSI, PIN_CS, PIN_GDO0,
                         PIN_GDO2);

static byte CC1101Transceiver_module_number = 0;

CC1101Transceiver::CC1101Transceiver(byte SCK, byte MISO, byte MOSI, byte CSN,
                                     byte GDO0, byte GDO2) {
  this->SCK = SCK;
  this->MISO = MISO;
  this->MOSI = MOSI;
  this->CSN = CSN;
  this->GDO0 = GDO0;
  this->GDO2 = GDO2;
  this->moduleNumber = CC1101Transceiver_module_number++;
}

void CC1101Transceiver::setup() {
  pinMode(this->GDO0, OUTPUT);
  pinMode(this->GDO2, INPUT);
  digitalWrite(this->GDO0, LOW);
  CC1101_MAIN.addSpiPin(this->SCK, this->MISO, this->MOSI, this->CSN,
                        this->moduleNumber);
  CC1101_MAIN.addGDO(this->GDO0, this->GDO2, this->moduleNumber);
  this->select();
  CC1101_MAIN.Init();
  CC1101_MAIN.setCCMode(false);
  CC1101_MAIN.setPktFormat(
      3); // Format of RX and TX data. 0 = Normal mode, use FIFOs for RX and TX.
          // 1 = Synchronous serial mode, Data in on GDO0 and data out on either
          // of the GDOx pins. 2 = Random TX mode; sends random data using PN9
          // generator. Used for test. Works as normal mode, setting 0 (00), in
          // RX. 3 = Asynchronous serial mode, Data in on GDO0 and data out on
          // either of the GDOx pins.
  CC1101_MAIN.setSyncMode(0);
  CC1101_MAIN.SpiWriteReg(CC1101_IOCFG0, 0x2E);
  CC1101_MAIN.SpiWriteReg(CC1101_IOCFG1, 0x2E);
  CC1101_MAIN.SpiWriteReg(CC1101_IOCFG2, 0x0D);
  CC1101_MAIN.SetRx();
}

void CC1101Transceiver::beginTransmission() {
  this->select();
  digitalWrite(this->GDO0, LOW);
  CC1101_MAIN.SetTx();
}

void CC1101Transceiver::endTransmission() {
  this->select();
  digitalWrite(this->GDO0, LOW);
  CC1101_MAIN.SetRx();
  CC1101_MAIN.SetRx(); // yes, twice
}

byte CC1101Transceiver::getTXPin() { return this->GDO0; }
void CC1101Transceiver::select() { CC1101_MAIN.setModul(this->moduleNumber); }
