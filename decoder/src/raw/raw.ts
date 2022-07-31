export class RawSignal {
    signalType: string;
    clockIndex: number;
    rssi: number;
    timings: number[];
    uniqueTimings: Set<number>;

    constructor(signalType: string, clockIndex: number, rssi: number, timings: number[]) {
        this.signalType = signalType;
        this.clockIndex = clockIndex;
        this.rssi = rssi;
        this.uniqueTimings = new Set(timings);
        this.timings = timings;
    }

    static fromString(signalStr: string) {
        const spl = signalStr.substring(2).split(';');
        const signalType = spl.shift()!;
    
        let rssi = -1;
        let clockIndex = -1;
        const timingValues = new Map<string, number>();
        const timings: number[] = [];
        for (const field of spl) {
            const [key, value] = field.split('=', 2);
            if (key.charAt(0) == 'P') {
                timingValues.set(key.charAt(1), parseInt(value, 10));
            } else {
                switch (key) {
                    case 'D':
                        for (const char of value) {
                            timings.push(timingValues.get(char)!);
                        }
                        break;
                    case 'CP':
                        clockIndex = parseInt(value, 10);
                        break;
                    case 'R':
                        rssi = parseInt(value, 10);
                        break;
                }
            }
        }
    
        return new RawSignal(signalType, clockIndex, rssi, timings);
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
