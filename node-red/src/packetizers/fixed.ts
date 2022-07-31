import { BinarySignal } from "../raw/binary";
import { RawSignal } from "../raw/raw";
import { SignalPacketizer } from "./index";

export class SignalPacketizerFixed extends SignalPacketizer {
    tolerance: number;
    minLen: number;
    pulseLen: number;
    maxConsecutivePulse: number;

    constructor() {
        super();
        this.tolerance = 200;
        this.minLen = 5;
        this.pulseLen = 0;
        this.maxConsecutivePulse = 3;
    }

    unpack(rawSignal: RawSignal): BinarySignal[] {
        const actualAbsPulseLen = rawSignal.findClosestAbs(this.pulseLen, this.tolerance);

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
            timings.push(bit ? this.pulseLen : -this.pulseLen);
        }
        return new RawSignal("MU", 0, timings);
    }
}
