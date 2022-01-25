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

  hostSerial.echoFirst(F("CC1101Duino ready "));
  hostSerial.sendEnd(String(mcusr_mirror));
  wdt_enable(WDTO_2S);
}

void loop() {
  wdt_reset();

  hostSerial.loop();
}
