#include <Arduino.h>
#include <ELECHOUSE_CC1101_SRC_DRV.h>
#include "signalDecoder.h"
#include "SimpleFIFO.h"

#include "cc1101.h"
#include "config.h"
#include "serial_host.h"
#include "utils.h"

#define FIFO_LENGTH 90    // 150
#define minPulse    90

SignalDetectorClass signalDecoder;
SimpleFIFO<int,FIFO_LENGTH> fifo; //store FIFO_LENGTH # ints

HostSerial hostSerial(Serial);

HostSerial::HostSerial(HardwareSerial &serial) : CommandSerial(serial) {}

static int repeats = 20;
static int repeat_delay = 10;

static float tx_freq = 0;
static int tx_mod = 0;

const float rx_freq = 433.88;
const int rx_mod = 2;

static uint8_t rssiCallback() {
  cc1101.select();
  return CC1101_MAIN.getRssi();
}

// handleInterrupt and loopRxtiming come from SIGNALDuino
unsigned long lastRxTime;
void handleInterrupt() {
  cli();
  const unsigned long curTime = micros();
  const unsigned long duration = curTime - lastRxTime;
  lastRxTime = curTime;
  if (duration >= minPulse) {//kleinste zulaessige Pulslaenge
    int sDuration;
    if (duration < maxPulse) {//groesste zulaessige Pulslaenge, max = 32000
      sDuration = int(duration); //das wirft bereits hier unnoetige Nullen raus und vergroessert den Wertebereich
    }
    else {
      sDuration = maxPulse; // Maximalwert set to maxPulse defined in lib.
    }
    if (digitalRead(PIN_GDO2) == HIGH) { // Wenn jetzt high ist, dann muss vorher low gewesen sein, und dafuer gilt die gemessene Dauer.
      sDuration = -sDuration;
    }
    fifo.enqueue(sDuration);
  } // else => trash
  sei();
}

void loopRxTiming() {
  cli();
  const unsigned long  duration = micros() - lastRxTime;

  if (duration >= maxPulse) { //Auf Maximalwert pruefen.
    int sDuration = maxPulse;
    if (digitalRead(PIN_GDO2) == LOW) { // Wenn jetzt low ist, ist auch weiterhin low
      sDuration = -sDuration;
    }
    fifo.enqueue(sDuration);
    lastRxTime = micros();
  }
  sei();

  int val;
  while (fifo.count() > 0) {               // Puffer auslesen und an Dekoder uebergeben
    val = fifo.dequeue();
    signalDecoder.decode(&val);
  }
}

static void beginTransmission() {
  cli();
  detachInterrupt(digitalPinToInterrupt(PIN_GDO2));
  signalDecoder.reset();
  fifo.flush();
  sei();

  CC1101_MAIN.setMHZ(tx_freq);
  CC1101_MAIN.setModulation(tx_mod);
  cc1101.beginTransmission();
}

static void endTransmission() {
  cc1101.endTransmission();
  CC1101_MAIN.setMHZ(rx_freq);
  CC1101_MAIN.setModulation(rx_mod);
  cc1101.endTransmission();

  cli();
  signalDecoder.reset();
  fifo.flush();
  attachInterrupt(digitalPinToInterrupt(PIN_GDO2), handleInterrupt, CHANGE);
  sei();
}

size_t writeCallback(const uint8_t *buf, uint8_t len) {
  while (!Serial.availableForWrite()) {
    yield();
  }

  if (len == 1) {
    switch (buf[0]) {
      case '\r':
      case '\n':
        return 1;
      case MSG_START:
        hostSerial.sendFirst("S");
        return 1;
      case MSG_END:
        hostSerial.sendEnd();
        return 1;
    }
  }

  return Serial.write(buf,len);  
}

void initRxSystem() {
  signalDecoder.setRSSICallback(rssiCallback);
  signalDecoder.setStreamCallback(writeCallback);
  signalDecoder.MredEnabled = false;
  signalDecoder.MCenabled = true;
  signalDecoder.MSenabled = true;
  signalDecoder.MUenabled = true;
  endTransmission();
}

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
