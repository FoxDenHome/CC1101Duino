import { SignalPacketizerOnOffBit } from "./on_off_bit";

export class MinkaAirePacketizer extends SignalPacketizerOnOffBit {
    constructor() {
        super();
        this.minLen = 13;
        this.pulse = { value: 417, tolerance: 100 };
    }
}
