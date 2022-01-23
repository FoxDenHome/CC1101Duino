#include <Arduino.h>

#include "cc1101.h"
#include "serial_host.h"

void setup() {
  hostSerial.init();
  cc1101.setup();
  hostSerial.echo(F("CC1101-duino ready"));
}

void loop() {
  hostSerial.loop();
}
