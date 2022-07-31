import { BinarySignal } from "../raw/binary";
import { RawSignal } from "../raw/raw";
import { NotSupportedException } from "../util";

export abstract class SignalPacketizer {
    unpack(_rawSignal: RawSignal): BinarySignal[] {
        throw new NotSupportedException();
    }
    
    pack(_binarySignal: BinarySignal): RawSignal {
        throw new NotSupportedException();
    }
}
