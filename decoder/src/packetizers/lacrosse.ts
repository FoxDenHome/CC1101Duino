import { SignalPacketizerFixedVariable } from "./fixed_variable";

export class LacrossePacketizer extends SignalPacketizerFixedVariable {
    constructor() {
        super();
        this.fixedPulse = -975;
        this.zeroPulse = 1400;
        this.onePulse = 550;
        this.minLen = 40;
    }
}
