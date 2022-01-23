#include <Arduino.h>

#include "cc1101.h"
#include "serial_host.h"

void setup() {
  hostSerial.init();
  cc1101.setup();
}

void loop() {
  hostSerial.loop();
}
