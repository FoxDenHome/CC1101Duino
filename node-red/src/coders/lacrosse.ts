import { Modulation } from "../modulations";
import { LacrossePacketizer } from "../packetizers/lacrosse";
import { BinarySignal } from "../raw/binary";
import { SensorSignal } from "../signals/sensor";
import { LoadReturnType, SignalCoder } from "./index";

export class LacrosseSignalCoder extends SignalCoder {
    decodeInternal(signal: BinarySignal) {
        if (!signal.matchAndStripHeaderFuzzy([0, 0, 0, 0, 1, 0, 1, 0], 2)) {
            return undefined;
        }

        const offsetZero = signal.offset;
        let measuredParityTmp = 0;
        let measuredChecksumTmp = 0b0000 + 0b1010;
        signal.readerHook = (bit, offset) => {
            if (bit) {
                offset -= offsetZero;
                measuredParityTmp = 1 - measuredParityTmp;
                measuredChecksumTmp += 1 << (3 - (offset % 4));
            }
        };

        // Relevant for just checksum
        const sensorType = signal.readNumberMSBFirst(4);
        const sensorId = signal.readNumberMSBFirst(7).toString();
        const parity = signal.readBit();

        // Relevant for parity + checksum
        measuredParityTmp = 0;
        const tens = signal.readNumberMSBFirst(4);
        const ones = signal.readNumberMSBFirst(4);
        const tenths = signal.readNumberMSBFirst(4);
        
        // Relevant for just checksum
        const measuredParity = measuredParityTmp;
        const tens2 = signal.readNumberMSBFirst(4);
        const ones2 = signal.readNumberMSBFirst(4);
        
        // Not relevant for either integrity mechanism
        signal.readerHook = undefined;
        const checksum = signal.readNumberMSBFirst(4);

        const measuredChecksum = measuredChecksumTmp & 0b1111;

        if (tens !== tens2 || ones !== ones2 || parity !== measuredParity || checksum !== measuredChecksum) {
            return undefined;
        }

        const rawValue = (tens * 10) + ones + (tenths / 10);

        switch (sensorType) {
            case 0b0000:
                return new SensorSignal(this.getName(), "temperature", sensorId, "C", rawValue - 50.0);
            case 0b1110:
                return new SensorSignal(this.getName(), "humidity", sensorId, "%", rawValue);
            default:
                return undefined;
        }
    }

    getPacketizerClass() {
        return LacrossePacketizer;
    }

    getName(): string {
        return "lacrosse";
    }

    getFrequency(): number {
        return 433.88;
    }

    getModulation(): Modulation {
        return Modulation.ASK_OOK;
    }
}

export function load(): LoadReturnType {
    return [LacrosseSignalCoder];
}
