import { Modulation } from "../modulations";

export class RawSignal {
    signalType: string;
    clockIndex: number;
    rssi: number;
    timings: number[];
    frequency: number;
    modulation: Modulation;
    uniqueTimings: Set<number>;

    constructor(signalType: string, clockIndex: number, timings: number[], modulation: Modulation = Modulation.INVALID, frequency: number = 0, rssi: number = 0) {
        this.signalType = signalType;
        this.clockIndex = clockIndex;
        this.rssi = rssi;
        this.frequency = frequency;
        this.modulation = modulation;
        this.uniqueTimings = new Set(timings);
        this.timings = timings;
    }

    static fromString(signalStr: string) {
        signalStr = signalStr.trim();
        if (signalStr.length < 3 || !signalStr.startsWith('^S')) {
            return undefined;
        }

        const spl = signalStr.substring(2).split(';');
        if (spl.length < 3) {
            return undefined;
        }

        const signalType = spl.shift()!;
    
        let rssi = -1;
        let clockIndex = -1;
        const timingValues = new Map<string, number>();
        const timings: number[] = [];
        for (const field of spl) {
            const [key, value] = field.split('=', 2);
            if (key.charAt(0) == 'P' && key.length > 1) {
                timingValues.set(key.charAt(1), parseInt(value, 10));
            } else {
                switch (key) {
                    case 'D':
                        for (const char of value) {
                            const tv = timingValues.get(char);
                            if (!tv) {
                                return undefined;
                            }
                            timings.push(tv);
                        }
                        break;
                    case 'CP':
                        clockIndex = parseInt(value, 10);
                        break;
                    case 'R':
                        rssi = parseInt(value, 10);
                        break;
                    default:
                        break;
                }
            }
        }

        if (timings.length < 1) {
            return undefined;
        }
    
        return new RawSignal(signalType, clockIndex, timings, Modulation.ASK_OOK, 433.88, rssi);
    }

    toCommandString(repetitions: number, repetition_delay: number): string {
        const params: { [key: string]: any } = {
            F: this.frequency,
            M: this.modulation,
            R: repetitions,
            S: repetition_delay,
            D: '',
        };

        const packets = new Map<number, number>();

        for (const delay of this.timings) {
            let packet = packets.get(delay);
            if (packet === undefined) {
                const idx = packets.size;
                if (idx >= 10) {
                    throw new Error("More than 10 unique packets");
                }
                params[`P${idx}`] = delay;
                packets.set(delay, idx);
                packet = idx;
            }
            params.D += packet.toString();
        }

        let payload = '^S;';
        for (const [key, value] of Object.entries(params)) {
            if (value === undefined) {
                continue;
            }
            payload += `${key}=${value};`;
        }
        payload += '\n';

        return payload;
    }

    findClosest(timing: number, tolerance: number = 200) {
        let bestTimingDist, bestTiming;
        
        const timingSign = Math.sign(timing);

        for (const haveTiming of this.uniqueTimings) {
            // We never want to turn a low pulse into a high pulse
            if (Math.sign(haveTiming) !== timingSign) {
                continue;
            }

            const timingDist = Math.abs(timing - haveTiming);
            if (timingDist > tolerance) {
                continue;
            }

            if (bestTimingDist === undefined || timingDist < bestTimingDist) {
                bestTiming = haveTiming;
                bestTimingDist = timingDist;
            }
        }

        return bestTiming;
    }
}