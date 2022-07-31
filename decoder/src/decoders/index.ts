import { SignalPacketizer } from "../packetizers/index";
import { BinarySignal } from "../raw/binary";
import { EndOfSignalError } from "../raw/index";
import { Signal } from "../signals/index";

export abstract class SignalDecoder {
    decode(signal: BinarySignal) {
        try {
            return this.decodeInternal(signal);
        } catch (e) {
            if (e instanceof EndOfSignalError) {
                return undefined;
            }
            throw e;
        }
    }

    abstract decodeInternal(signal: BinarySignal): Signal | undefined;

    abstract getPacketizerClass(): { new(): SignalPacketizer };
}
