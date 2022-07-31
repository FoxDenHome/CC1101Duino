import { BinarySignal } from "../raw/binary";
import { RawSignal } from "../raw/raw";
import { SignalPacketizer } from "./index";

export class SignalPacketizerOnOffBit extends SignalPacketizer {
    tolerance: number;
    minLen: number;
    pulseLen: number;

    constructor() {
        super();
        this.tolerance = 200;
        this.minLen = 5;
        this.pulseLen = 0;
    }

    pack(signal: BinarySignal) {
        const timings = [];
        for (const bit of signal.bits) {
            timings.push(this.pulseLen);
            timings.push(-this.pulseLen);
            timings.push(bit ? this.pulseLen : -this.pulseLen);
        }
        return new RawSignal("MU", 0, timings);
    }
}
