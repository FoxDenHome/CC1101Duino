#pragma once

#include <Arduino.h>
#include "signalDecoder.h"

void beginTransmission(float tx_freq, byte tx_mod);
void endTransmission();

void initRxSystem();
void loopRxSystem();
void setRxFrequency(float freq);
void setRxModulation(byte mod);
