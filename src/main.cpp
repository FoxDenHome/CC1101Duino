#include <Arduino.h>

#include <avr/wdt.h>

#include "cc1101.h"
#include "serial_host.h"

void setup() {
  const uint8_t mcusr_mirror = MCUSR;
  MCUSR = 0;
  wdt_disable();

  hostSerial.init();
  cc1101.setup();
  beginReceive();

  hostSerial.echoFirst(F("CC1101Duino ready "));
  hostSerial.sendEnd(String(mcusr_mirror));
  wdt_enable(WDTO_2S);
}

static bool sendMeasure() {
  measure m = thermoReceiver.getNextMeasure();

  switch (m.type) {
    case TEMPERATURE:
      hostSerial.sendFirst("S|T|C|");
      break;
    case HUMIDITY:
      hostSerial.sendFirst("S|H|%rh|");
      break;
    case UNKNOWN:
      return false;
  }

  hostSerial.sendNext(String(m.sensorAddr));
  hostSerial.sendNext("|");
  if (m.sign < 0) {
    hostSerial.sendNext("-");
  }
  hostSerial.sendNext(String(m.units));
  hostSerial.sendNext(".");
  hostSerial.sendEnd(String(m.decimals));

  return true;
}

void loop() {
  wdt_reset();

  hostSerial.loop();

  static unsigned long lastMeasurePoll = 0;
  unsigned long currMs = millis();

  if (currMs - lastMeasurePoll >= 100) {
    lastMeasurePoll = currMs;
    sendMeasure();
  }
}
