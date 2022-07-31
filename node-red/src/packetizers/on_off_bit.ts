import { BinarySignal } from "../raw/binary";
import { RawSignal } from "../raw/raw";
import { SignalPacketizerFixed } from "./fixed";

export class SignalPacketizerOnOffBit extends SignalPacketizerFixed {
    constructor() {
        super();
        this.maxConsecutivePulse = 2;
    }

    unpack(rawSignal: RawSignal): BinarySignal[] {
        this.minLen *= 3
        const binSigs = super.unpack(rawSignal);
        this.minLen /= 3;

        const signals = [];
        let curSignal = [];
        for (const binSig of binSigs) {
            const binBits = binSig.bits;

            // Align ourselves
            for (let i = 0; i < binBits.length - 2; i++) {
                if (binBits[i] !== 1 || binBits[i + 1] !== 0) {
                    if (curSignal.length >= this.minLen) {
                        signals.push(new BinarySignal(curSignal));
                    }
                    curSignal = [];
                    continue;
                }
                curSignal.push(binBits[i + 2]);
                i += 2;
            }

            if (curSignal.length >= this.minLen) {
                signals.push(new BinarySignal(curSignal));
            }
            curSignal = [];
        }

        return signals;
    }

    pack(signal: BinarySignal) {
        const bits = [];
        for (const bit of signal.bits) {
            bits.push(1);
            bits.push(0);
            bits.push(bit);
        }
        return super.pack(new BinarySignal(bits));
    }
}
