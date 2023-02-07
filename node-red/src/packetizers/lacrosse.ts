import { SignalPacketizerFixedVariable } from "./fixed_variable";

export class LacrossePacketizer extends SignalPacketizerFixedVariable {
    constructor() {
        super();
        this.fixedPulse = { value: -1075, tolerance: 200 };
        this.zeroPulse = { value: 1400, tolerance: 200 };
        this.onePulse = { value: 550, tolerance: 200 };
        this.minLen = 40;
    }
}
