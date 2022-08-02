#pragma once

#include <Arduino.h>
#include "signalDecoder.h"

bool beginTransmission(float tx_freq, byte tx_mod);
void endTransmission();

bool validFrequency(float mhz);
bool validModulation(byte mod);

void initRxSystem();
void loopRxSystem();
bool setRxFrequency(float freq);
bool setRxModulation(byte mod);
