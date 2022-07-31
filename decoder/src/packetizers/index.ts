import { BinarySignal } from "../raw/binary";
import { RawSignal } from "../raw/raw";

export abstract class SignalPacketizer {
    abstract packetize(rawSignal: RawSignal): BinarySignal[];
}
