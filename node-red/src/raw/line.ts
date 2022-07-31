import { readdirSync } from "fs";
import { join } from "path";
import { LoadReturnType, SignalDecoder } from "../decoders/index";
import { SignalPacketizer } from "../packetizers/index";
import { Signal } from "../signals";
import { RawSignal } from "./raw";

export class LineDecoder {
    packetizers: Map<typeof SignalPacketizer, SignalPacketizer> = new Map();
    decodersByPacketizer: Map<SignalPacketizer, SignalDecoder[]> = new Map();

    constructor() {
        
    }

    loadAllDecoders() {
        const decoderPath = join(__dirname, "../decoders/");
        for (const decoderFile of readdirSync(decoderPath)) {
            if (!decoderFile.endsWith('.ts') && !decoderFile.endsWith('.js')) {
                continue;
            }
            const mod = require(join(decoderPath, decoderFile));
            const loader = mod.load as () => LoadReturnType;
            for (const DecoderClass of loader()) {
                this.loadDecoder(new DecoderClass());
            }
        }
    }

    loadDecoder(decoder: SignalDecoder) {
        const PacketizerClass = decoder.getPacketizerClass();
        
        if (!this.packetizers.has(PacketizerClass)) {
            const packetizer = new PacketizerClass();
            this.packetizers.set(PacketizerClass, packetizer);
            this.decodersByPacketizer.set(packetizer, []);
        }
    
        this.decodersByPacketizer.get(this.packetizers.get(PacketizerClass)!)!.push(decoder);
    }

    loadDecoders(decoders: SignalDecoder[]) {
        for (const decoder of decoders) {
            this.loadDecoder(decoder);
        }
    }

    processSignalLine(line: string) {
        const res: Signal[] = [];
    
        const rawSignal = RawSignal.fromString(line);
        if (!rawSignal) {
            return res;
        }

        for (const [packetizer, decoders] of this.decodersByPacketizer.entries()) {
            for (const packetizedSignal of packetizer.packetize(rawSignal)) {
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