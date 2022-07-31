#pragma once

#include <Arduino.h>
#include "signalDecoder.h"

void loopRxSystem();
void initRxSystem();
void endTransmission();
void beginTransmission(float tx_freq, byte tx_mod);

extern float tx_freq;
extern int tx_mod;
extern SignalDetectorClass signalDecoder;
