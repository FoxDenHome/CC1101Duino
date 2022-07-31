import { readdirSync } from "fs";
import { join } from "path";
import { LoadReturnType, SignalCoder } from "../coders/index";
import { SignalPacketizer } from "../packetizers/index";
import { Signal } from "../signals";
import { NotSupportedException } from "../util";
import { RawSignal } from "./raw";

export class LineCoder {
    packetizers: Map<typeof SignalPacketizer, SignalPacketizer> = new Map();
    codersByPacketizer: Map<SignalPacketizer, SignalCoder[]> = new Map();
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
            const packetizer = new PacketizerClass();
            this.packetizers.set(PacketizerClass, packetizer);
            this.codersByPacketizer.set(packetizer, []);
        }
    
        this.codersByPacketizer.get(this.packetizers.get(PacketizerClass)!)!.push(coder);
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
        const res: Signal[] = [];
    
        const rawSignal = RawSignal.fromString(line);
        if (!rawSignal) {
            return res;
        }

        for (const [packetizer, decoders] of this.codersByPacketizer.entries()) {
            let packetizedSignals;
            try {
                packetizedSignals = packetizer.unpack(rawSignal);
            } catch (e) {
                if (e instanceof NotSupportedException) {
                    continue;
                }
                throw e;
            }
            for (const packetizedSignal of packetizedSignals) {
                for (const decoder of decoders) {
                    const signal = decoder.decode(packetizedSignal);
                    if (signal) {
                        res.push(signal);
                    }
                }
            }
        }
    
        return res;
    }
}
