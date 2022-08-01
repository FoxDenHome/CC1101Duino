#include "rf.h"

#include <EEPROM.h>
#include <Arduino.h>
#include <TimerOne.h>
#include "SimpleFIFO.h"
#include "signalDecoder.h"
#include "config.h"
#include "cc1101.h"
#include "serial_host.h"

#define EEPROM_MODULATION 1
#define EEPROM_FREQUENCY 2

#define FIFO_LENGTH 90    // 150
#define minPulse    90
#define PIN_RX      PIN_GDO2

static SignalDetectorClass signalDecoder;
static SimpleFIFO<int,FIFO_LENGTH> fifo; //store FIFO_LENGTH # ints

float rx_freq = DEFAULT_FREQUENCY;
int rx_mod = DEFAULT_MODULATION;

bool in_rx;

static uint8_t rssiCallback() {
  cc1101.select();
  return CC1101_MAIN.getRssi();
}

// handleRxInterrupt, timer1RxSystem and loopRxtiming come from SIGNALDuino
unsigned long lastRxTime;
static void handleRxInterrupt() {
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
    if (isHigh(PIN_RX)) { // Wenn jetzt high ist, dann muss vorher low gewesen sein, und dafuer gilt die gemessene Dauer.
      sDuration = -sDuration;
    }
    
    fifo.enqueue(sDuration);
  } // else => trash
  sei();
}

void timer1RxSystem() {
  cli();
  const unsigned long  duration = micros() - lastRxTime;

  Timer1.setPeriod(maxPulse);

  if (duration >= maxPulse) { //Auf Maximalwert pruefen.
    int sDuration = maxPulse;
    if (isLow(PIN_RX)) { // Wenn jetzt low ist, ist auch weiterhin low
      sDuration = -sDuration;
    }
    fifo.enqueue(sDuration);
    lastRxTime = micros();
  } else if (duration > 10000) {
    Timer1.setPeriod(maxPulse-duration+16);
  }
  sei();
}

void loopRxSystem() {
  int val;
  while (fifo.count() > 0) {               // Puffer auslesen und an Dekoder uebergeben
    val = fifo.dequeue();
    signalDecoder.decode(&val);
  }
}

static size_t writeCallback(const uint8_t *buf, uint8_t len) {
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
        hostSerial.sendNext("F=");
        hostSerial.sendNext(String(rx_freq));
        hostSerial.sendNext(";M=");
        hostSerial.sendNext(String(rx_mod));
        hostSerial.sendEnd(";");
        return 1;
    }
  }

  return Serial.write(buf,len);  
}

void initRxSystem() {
  EEPROM.begin();

  rx_mod = EEPROM.read(EEPROM_MODULATION);
  EEPROM.get(EEPROM_FREQUENCY, rx_freq);
  hostSerial.echoFirst(F("RX initialized F="));
  hostSerial.sendNext(String(rx_freq));
  hostSerial.sendNext(F(";M="));
  hostSerial.sendEnd(String(rx_mod));
  Timer1.initialize(maxPulse);
  Timer1.attachInterrupt(timer1RxSystem);

  signalDecoder.setRSSICallback(rssiCallback);
  signalDecoder.setStreamCallback(writeCallback);
  signalDecoder.MredEnabled = false;
  signalDecoder.MCenabled = true;
  signalDecoder.MSenabled = true;
  signalDecoder.MUenabled = true;
  endTransmission();
}

static void refreshRxConfig() {
  if (rx_freq < 1 || rx_freq > 1000) {
    rx_freq = DEFAULT_FREQUENCY;
  }
  if (rx_mod > 4) {
    rx_mod = DEFAULT_MODULATION;
  }

  if (!in_rx) {
    return;
  }
  cc1101.endTransmission();
  CC1101_MAIN.setMHZ(rx_freq);
  CC1101_MAIN.setModulation(rx_mod);
  cc1101.endTransmission();
}

void beginTransmission(float tx_freq, byte tx_mod) {
  if (!in_rx) {
    return;
  }
  in_rx = false;

  cli();
  detachInterrupt(digitalPinToInterrupt(PIN_GDO2));
  signalDecoder.reset();
  fifo.flush();
  sei();

  CC1101_MAIN.setMHZ(tx_freq);
  CC1101_MAIN.setModulation(tx_mod);
  cc1101.beginTransmission();
}

void endTransmission() {
  if (in_rx) {
    return;
  }
  in_rx = true;

  refreshRxConfig();

  cli();
  signalDecoder.reset();
  fifo.flush();
  attachInterrupt(digitalPinToInterrupt(PIN_GDO2), handleRxInterrupt, CHANGE);
  sei();
}

void setRxFrequency(float freq) {
  rx_freq = freq;
  refreshRxConfig();
  EEPROM.put(EEPROM_FREQUENCY, freq);
}

void setRxModulation(byte mod) {
  rx_mod = mod;
  refreshRxConfig();
  EEPROM.write(EEPROM_MODULATION, mod);
}
