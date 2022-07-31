import { Modulation } from "../modulations";
import { MinkaAirePacketizer } from "../packetizers/minka_aire";
import { BinarySignal } from "../raw/binary";
import { LoadReturnType, SignalCoder } from "./index";

const COMMANDS: { [key: string]: string } = {
	off:     '10100',
	low:     '00100',
	medium:  '01000',
	high:    '10000',
	light_1: '01010',
	light_2: '10010',
};
COMMANDS.light = COMMANDS.light_1;

export class MinkaAireSignalCoder extends SignalCoder {
    encode(signal: any): BinarySignal {
        const bits = [];
        for (const dip of signal.dip) {
            bits.push(dip);
        }
        for (const c of COMMANDS[signal.command]) {
            bits.push(c);
        }
        return new BinarySignal(bits);
    }

    getPacketizerClass() {
        return MinkaAirePacketizer;
    }

    getName(): string {
        return "minka_aire";
    }

    getFrequency(): number {
        return 304.2;
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
