#pragma once

#include <Arduino.h>
#include "signalDecoder.h"

#include "serial.h"

void loopRxTiming();
void initRxSystem();

class HostSerial : public CommandSerial {
public:
  HostSerial(HardwareSerial &_serial);

protected:
  void handle() override;
};

extern HostSerial hostSerial;
extern SignalDetectorClass signalDecoder;
