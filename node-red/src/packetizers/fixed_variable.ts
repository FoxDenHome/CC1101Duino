import { BinarySignal } from "../raw/binary";
import { RawSignal } from "../raw/raw";
import { NumberRange, NUMER_RANGE_ZERO } from "../util";
import { SignalPacketizer } from "./index";

export class SignalPacketizerFixedVariable extends SignalPacketizer {
    minLen: number;
    fixedPulse: NumberRange;
    zeroPulse: NumberRange;
    onePulse: NumberRange;

    constructor() {
        super();
        this.minLen = 5;
        this.fixedPulse = NUMER_RANGE_ZERO;
        this.zeroPulse = NUMER_RANGE_ZERO;
        this.onePulse = NUMER_RANGE_ZERO;
    }

    unpack(rawSignal: RawSignal) {
        const actualFixedPulse = rawSignal.findClosest(this.fixedPulse);
        const actualZeroPulse = rawSignal.findClosest(this.zeroPulse);
        const actualOnePulse = rawSignal.findClosest(this.onePulse);

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

        if (curSignal.length >= this.minLen) {
            signals.push(new BinarySignal(curSignal));
        }

        return signals;
    }

    pack(signal: BinarySignal) {
        const timings = [];
        for (const bit of signal.bits) {
            timings.push(this.fixedPulse.value);
            timings.push(bit ? this.onePulse.value : this.zeroPulse.value);
        }
        return new RawSignal("MU", 0, timings);
    }
}
