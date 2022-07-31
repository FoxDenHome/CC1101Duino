import { BinarySignal } from "../raw/binary";
import { RawSignal } from "../raw/raw";
import { SignalPacketizer } from "./index";

export class SignalPacketizerFixedVariable extends SignalPacketizer {
    tolerance: number;
    minLen: number;
    fixedPulse: number;
    zeroPulse: number;
    onePulse: number;

    constructor() {
        super();
        this.tolerance = 200;
        this.minLen = 5;
        this.fixedPulse = 0;
        this.zeroPulse = 0;
        this.onePulse = 0;
    }

    unpack(rawSignal: RawSignal) {
        const actualFixedPulse = rawSignal.findClosest(this.fixedPulse, this.tolerance);
        const actualZeroPulse = rawSignal.findClosest(this.zeroPulse, this.tolerance);
        const actualOnePulse = rawSignal.findClosest(this.onePulse, this.tolerance);

        if (!actualFixedPulse || !actualZeroPulse || !actualOnePulse) {
            return [];
        }

        const defaultPulse = (actualFixedPulse < 0) ? actualFixedPulse : actualZeroPulse;

        let signals = [];
        let curSignal = [];
        let lastTiming = defaultPulse;

        looptimings:
        for (const timing of rawSignal.timings) {
            if (timing != actualFixedPulse && timing != actualZeroPulse && timing != actualOnePulse) {
                if (curSignal.length >= this.minLen) {
                    signals.push(new BinarySignal(curSignal));
                }
                curSignal = [];
                lastTiming = defaultPulse;
                continue;
            }
            
            if (lastTiming == actualFixedPulse) {
                switch (timing) {
                    case actualFixedPulse:
                        continue looptimings;
                    case actualOnePulse:
                        curSignal.push(1);
                        break;
                    case actualZeroPulse:
                        curSignal.push(0);
                        break;
                }
            } else if (timing !== actualFixedPulse) {
                if (curSignal.length >= this.minLen) {
                    signals.push(new BinarySignal(curSignal));
                }
                curSignal = [];
            }

            lastTiming = timing;
        }

        if (curSignal.length > this.minLen) {
            signals.push(new BinarySignal(curSignal));
        }

        return signals;
    }

    pack(signal: BinarySignal) {
        const timings = [];
        for (const bit of signal.bits) {
            timings.push(this.fixedPulse);
            timings.push(bit ? this.onePulse : this.zeroPulse);
        }
        return new RawSignal("MU", 0, timings);
    }
}
