import { Modulation } from "../modulations";
import { LacrossePacketizer } from "../packetizers/lacrosse";
import { BinarySignal } from "../raw/binary";
import { NumberRange } from "../util";
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
                return this.makeSignal("temperature", sensorId, "°C", rawValue - 50.0);
            case 0b1110:
                return this.makeSignal("humidity", sensorId, "%", rawValue);
            default:
                return undefined;
        }
    }

    makeSignal(sensorType: string, sensorId: string, unit: string, value: number) {
        return {
            coder: this.getName(),
            type: "sensor",
            subtype: sensorType,
            id: sensorId,
            unit,
            value,
        };
    }

    getPacketizerClass() {
        return LacrossePacketizer;
    }

    getName(): string {
        return "lacrosse";
    }

    getFrequency(): NumberRange {
        return { value: 433.88, tolerance: 1.0 };
    }

    getModulation(): Modulation {
        return Modulation.ASK_OOK;
    }
}

export function load(): LoadReturnType {
    return [LacrosseSignalCoder];
}
