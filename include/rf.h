#pragma once

#include <Arduino.h>
#include "signalDecoder.h"

void loopRxSystem();
void initRxSystem();
void endTransmission();
void beginTransmission();

extern float tx_freq;
extern int tx_mod;
extern SignalDetectorClass signalDecoder;
