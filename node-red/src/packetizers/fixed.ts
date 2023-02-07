import { BinarySignal } from "../raw/binary";
import { RawSignal } from "../raw/raw";
import { NumberRange, NUMER_RANGE_ZERO } from "../util";
import { SignalPacketizer } from "./index";

export class SignalPacketizerFixed extends SignalPacketizer {
    minLen: number;
    pulse: NumberRange;
    maxConsecutivePulse: number;

    constructor() {
        super();
        this.pulse = NUMER_RANGE_ZERO;
        this.minLen = 5;
        this.maxConsecutivePulse = 3;
    }

    unpack(rawSignal: RawSignal): BinarySignal[] {
        const actualAbsPulseLen = rawSignal.findClosestAbs(this.pulse);

        if (!actualAbsPulseLen) {
            return [];
        }

        let signals = [];
        let curSignal = [];

        for (const timing of rawSignal.timings) {
            const pulseCount = Math.round(Math.abs(timing) / actualAbsPulseLen);
            const pulseBit = (Math.sign(timing) > 0) ? 1 : 0;
            if (pulseCount < 1 || pulseCount > this.maxConsecutivePulse) {
                if (curSignal.length >= this.minLen) {
                    signals.push(new BinarySignal(curSignal));
                }
                curSignal = [];
                continue;
            }
            
            for (let i = 0; i < pulseCount; i++) {
                curSignal.push(pulseBit);
            }
        }

        if (curSignal.length >= this.minLen) {
            signals.push(new BinarySignal(curSignal));
        }

        return signals;
    }

    pack(signal: BinarySignal) {
        const timings = [];
        for (const bit of signal.bits) {
            timings.push(bit ? this.pulse.value : -this.pulse.value);
        }
        return new RawSignal("MU", 0, timings);
    }
}
