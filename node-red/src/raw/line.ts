import { readdirSync } from "fs";
import { join } from "path";
import { LoadReturnType, SignalCoder } from "../coders/index";
import { SignalPacketizer } from "../packetizers/index";
import { NotSupportedException } from "../util";
import { BinarySignal } from "./binary";
import { RawSignal } from "./raw";

export class LineCoder {
    packetizers: Map<typeof SignalPacketizer, SignalPacketizer> = new Map();
    coderByName: Map<string, SignalCoder> = new Map();

    constructor() {
        
    }

    loadAllCoders() {
        const coderPath = join(__dirname, "../coders/");
        for (const coderFile of readdirSync(coderPath)) {
            if (!coderFile.endsWith(".ts") && !coderFile.endsWith(".js")) {
                continue;
            }
            const mod = require(join(coderPath, coderFile));
            const loader = mod.load as () => LoadReturnType;
            for (const CoderClass of loader()) {
                this.loadCoder(new CoderClass());
            }
        }
    }

    loadCoder(coder: SignalCoder) {
        const PacketizerClass = coder.getPacketizerClass();
        
        if (!this.packetizers.has(PacketizerClass)) {
            this.packetizers.set(PacketizerClass, new PacketizerClass());
        }

        this.coderByName.set(coder.getName(), coder);
    }

    createSignalLine(signal: any) {
        if (!signal.coder) {
            throw new NotSupportedException();
        }

        const coder = this.coderByName.get(signal.coder);
        if (!coder) {
            throw new NotSupportedException();
        }

        const packetizer = this.packetizers.get(coder.getPacketizerClass())!;
        
        const binSig = coder.encode(signal);
        const rawSig = packetizer.pack(binSig);
        rawSig.frequency = coder.getFrequency();
        rawSig.modulation = coder.getModulation();

        return rawSig.toCommandString(coder.getRepetitions(), coder.getRepetitionDelay());
    }

    processSignalLine(line: string) {
        const res: any[] = [];
    
        const rawSignal = RawSignal.fromString(line);
        if (!rawSignal) {
            return res;
        }

        const packetizerResults = new Map<typeof SignalPacketizer, BinarySignal[]>();

        for (const coder of this.coderByName.values()) {
            if (Math.abs(rawSignal.frequency - coder.getFrequency()) > coder.getFrequencyTolerance()) {
                continue;
            }

            if (rawSignal.modulation !== coder.getModulation()) {
                continue;
            }

            const PacketizerClass = coder.getPacketizerClass();
            let packetizedSignals = packetizerResults.get(PacketizerClass);
            if (packetizedSignals === undefined) {
                packetizedSignals = this.packetizers.get(PacketizerClass)!.unpack(rawSignal);
                packetizerResults.set(PacketizerClass, packetizedSignals);
            }

            for (const packetizedSignal of packetizedSignals) {
                const signal = coder.decode(packetizedSignal);
                if (signal) {
                    res.push(signal);
                }
            }
        }

        return res;
    }
}
