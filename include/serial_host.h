#pragma once

#include <Arduino.h>
#include "LacrosseReceiver.h"

#include "serial.h"

void beginReceive();

class HostSerial : public CommandSerial {
public:
  HostSerial(HardwareSerial &_serial);

protected:
  void handle() override;
};

extern HostSerial hostSerial;
extern LacrosseReceiver thermoReceiver;
