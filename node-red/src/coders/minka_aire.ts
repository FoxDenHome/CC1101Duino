import { Modulation } from "../modulations";
import { MinkaAirePacketizer } from "../packetizers/minka_aire";
import { BinarySignal } from "../raw/binary";
import { NotSupportedException, NumberRange } from "../util";
import { LoadReturnType, SignalCoder } from "./index";

const COMMANDS: { [key: string]: string } = {
	off:     "10100",
	low:     "00100",
	medium:  "01000",
	high:    "10000",
	light_1: "01010",
	light_2: "10010",
};

const COMMANDS_REV: { [key: string]: string } = {};
for (const [name, bits] of Object.entries(COMMANDS)) {
    COMMANDS_REV[bits] = name;
}

COMMANDS.light = COMMANDS.light_1;

export class MinkaAireSignalCoder extends SignalCoder {
    encode(signal: any): BinarySignal {
        if (signal.type !== "command") {
            throw new NotSupportedException();
        }

        const bits = [];
        for (const i of signal.id) {
            bits.push(i);
        }
        for (const c of COMMANDS[signal.command]) {
            bits.push(c);
        }
        return BinarySignal.fromUntyped(bits);
    }

    decode(signal: BinarySignal): any {
        return {
            coder: this.getName(),
            type: "command",
            id: signal.readBitsAsString(8),
            command: COMMANDS_REV[signal.readBitsAsString(5)],
        }
    }

    getPacketizerClass() {
        return MinkaAirePacketizer;
    }

    getName(): string {
        return "minka_aire";
    }

    getFrequency(): NumberRange {
        return { value: 304.2, tolerance: 1.0 };
    }

    getModulation(): Modulation {
        return Modulation.ASK_OOK;
    }

    getRepetitionDelay(): number {
        return 10000;
    }

    getRepetitions(): number {
        return 10;
    }
}

export function load(): LoadReturnType {
    return [MinkaAireSignalCoder];
}
