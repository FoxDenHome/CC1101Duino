#pragma once

#include <Arduino.h>
#include "signalDecoder.h"

void beginTransmission(float tx_freq, byte tx_mod);
void endTransmission();

void initRxSystem();
void loopRxSystem();
bool setRxFrequency(float freq);
bool setRxModulation(byte mod);
