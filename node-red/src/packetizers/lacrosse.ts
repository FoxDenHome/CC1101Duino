import { SignalPacketizerFixedVariable } from "./fixed_variable";

export class LacrossePacketizer extends SignalPacketizerFixedVariable {
    constructor() {
        super();
        this.fixedPulse = { length: -975, tolerance: 300 };
        this.zeroPulse = { length: 1400, tolerance: 200 };
        this.onePulse = { length: 550, tolerance: 200 };
        this.minLen = 40;
    }
}
