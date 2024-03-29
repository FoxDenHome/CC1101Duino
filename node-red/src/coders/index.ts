import { Modulation } from "../modulations";
import { SignalPacketizer } from "../packetizers/index";
import { BinarySignal } from "../raw/binary";
import { EndOfSignalError } from "../raw/index";
import { NotSupportedException, NumberRange } from "../util";

export type LoadReturnType = { new(): SignalCoder }[];

export abstract class SignalCoder {
    decode(signal: BinarySignal): any | undefined {
        try {
            return this.decodeInternal(signal);
        } catch (e) {
            if (e instanceof EndOfSignalError || e instanceof NotSupportedException) {
                return undefined;
            }
            throw e;
        }
    }

    decodeInternal(_signal: BinarySignal): any | undefined {
        throw new NotSupportedException();
    }

    encode(_signal: any): BinarySignal {
        throw new NotSupportedException();
    }

    abstract getPacketizerClass(): { new(): SignalPacketizer };

    abstract getName(): string;

    abstract getFrequency(): NumberRange;

    abstract getModulation(): Modulation;

    getRepetitions(): number {
        return 1;
    }

    getRepetitionDelay(): number {
        return 10000;
    }
}

export function load(): LoadReturnType {
    return [];
}
