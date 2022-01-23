#pragma once

#include <Arduino.h>

#include "serial.h"

class HostSerial : public CommandSerial {
public:
    HostSerial(HardwareSerial& _serial);

protected:
    void handle() override;
};

extern HostSerial hostSerial;
