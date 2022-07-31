const signalStrings = `
^SMU;P0=19800;P1=-1086;P2=1412;P3=618;P4=-8096;P5=164;P6=-552;D=0121212131213121212121212131313121212121213121312131213121313121213121312131213131213134565;CP=3;R=190;
^SMU;P0=-7768;P1=-104;P2=148;P3=-152;P4=24460;P5=-1074;P6=1442;P7=619;D=1234565656575657565656565656575757565656565657565756575657565757565657565756575657575657570;CP=7;R=190;
^SMU;P0=100;P1=-1073;P2=1428;P3=681;P4=-9146;P6=-164;P7=508;D=121212171213121313131212131313121212121213121312131312121212121213121312131312121312134063;CP=3;R=190;
^SMU;P0=8692;P1=-825;P2=854;P3=252;P4=-483;P5=512;P6=-219;D=01212121343456343434343434343434343456563434565656343456343456343434565634563456565634343421212121343456343434343434343434343456563434565656343456343456343434565634563456565634343421212121343456343434343434343434343456563434565656343456343456343434565634;CP=3;R=188;O;
^SMU;P0=489;P1=-235;P2=251;P3=-481;P4=853;P5=-823;D=0123010101232323454545452323012323232323232323232323010123230101012323012323012323230101230;CP=2;R=187;
^SMU;P0=-240;P1=-829;P2=851;P3=253;P4=-467;P5=492;P6=-324;D=12121213434563434343434343434343434505034345050503434503434503434345050345034505050343450212121213434503434343434343434343434505034345050503434503434503434345050345034505050343434212121213434503434343434343434343434505034345050503434503434503434345050345;CP=3;R=187;O;
^SMU;P0=-224;P1=253;P2=-474;P3=511;P4=860;P5=-818;D=0123030301212304545454512123012121212121212121212123030121230303012123012123012121230301230;CP=1;R=187;
^SMU;P0=-202;P1=-804;P2=870;P3=276;P4=-451;P5=521;P6=-320;P7=176;D=12121213434567474743434343434343434505034345050503434503434503434345034503450345034343434212121213434503434343434343434343434505034345050503434503434503434345034503450345034343434212121213434503434343434343434343434505034345050503434503434503434345034503;CP=3;R=188;O;
^SMU;P0=-455;P1=510;P2=-222;P3=270;P4=869;P5=-805;P6=-4488;P7=100;D=012301230303030454545453030123030303030303030303030121230301212123030123030123030301230123030167;CP=3;R=186;
^SMU;P0=8020;P1=-821;P2=850;P3=247;P4=-479;P5=491;P6=-232;D=01212121343456343434343434343434343456563434565656343456343456343434563456345634563434345621212121343456343434343434343434343456563434565656343456343456343434563456345634563434343421212121343456343434343434343434343456563434565656343456343456343434563456;CP=3;R=187;O;
^SMU;P0=253;P1=-489;P2=515;P3=-230;P4=867;P5=-808;P6=-6520;D=01230123010101234545454501012301010101010101010101012323010123232301012301012301010123012301010106;CP=0;R=186;
^SMU;P0=1410;P1=-1096;P2=589;P3=-7928;D=0101010121012101010101010121212101010101012101210121012101212101012101210121012121012123;CP=2;R=191;
^SMU;P0=-7576;P2=328;P3=-148;P4=24196;P5=-1087;P6=1419;P7=599;D=234565656575657565656565656575757565656565657565756575657565757565657565756575657575657570;CP=7;R=190;
^SMU;P0=788;P1=-1077;P2=1426;P3=599;P4=-8032;P5=152;P6=-248;D=012121213121312131313121213131312121213121312131213131312121212121312131213131313121212456;CP=3;R=191;
^SMU;P0=128;P1=-124;P2=24276;P3=-1082;P4=1414;P5=594;P6=-7876;D=012343434353435343535353434353535343434353435343534353535343434343435343534353535353434346;CP=5;R=191;
^SMU;P0=26396;P1=-780;P2=892;P3=287;P4=-440;P5=550;P6=-181;D=01212121343456343434343434343434343456563434565656345634343456343434565656343456345656343421212121343456343434343434343434343456563434565656345634343456343434565656343456345656343421212121343456343434343434343434343456563434565656345634343456343434565656;CP=3;R=187;O;
^SMU;P0=288;P1=-449;P2=528;P3=-190;P4=881;P5=-798;D=0101230123230101454545450101230101010101010101010101232301012323230123010101230101012323230;CP=0;R=184;
^SMU;P0=243;P1=-950;P2=719;P4=-455;P5=531;P6=-332;P7=-216;D=12121210404560404040404040404040404575704045757570457040404570404045757570404570457570457;CP=0;R=186;
^SMU;P0=899;P1=-788;P2=277;P3=-455;P4=523;P5=-200;D=010101012323452323232323232323232323454523234545452345232325;CP=2;R=187;
^SMU;P0=-212;P1=526;P2=274;P3=-453;P4=886;P5=-786;P6=-3140;D=0102323231010102323102310102323454545452323102323232323232323232323101023231010102310232323102323231010102323102310102310454545452323102323232323232323232323101023231010102310232323102323231010102323102310102326;CP=2;R=187;
^SMU;P0=31368;P1=-1054;P2=1424;P3=607;P4=-7736;P5=164;D=0121212131213121212121212131313121212121213121312131213121312131213121312131213131213124515;CP=3;R=189;
^SMU;P0=1441;P1=-1076;P3=615;P4=-6796;P5=176;P6=-752;D=010101013101310131313101013131310101013101310131013131310101010101310131013131313101010456;CP=3;R=189;
^SMU;P0=-376;P1=100;P2=-124;P3=26244;P4=-1085;P5=1416;P6=599;P7=-6276;D=0123454545464546454646464545464646454545464546454645464646454545454546454645464646464545457;CP=6;R=188;
^SMU;P0=-186;P1=-938;P2=817;P3=292;P4=-461;P5=533;P6=-324;D=121212134345634343434343434343434345050343450505034503434345034343450505034345034505034342;CP=3;R=187;
^SMU;P0=-446;P1=879;P2=-803;P3=292;P5=534;P6=-196;D=01212123030563030303030303030303030565630305656563056303030563030305656563030563056563030121212123030563030303030303030303030565630305656563056303030563030305656563030563056563030121212123030563030303030303030303030565630305656563056303030563030305656563;CP=3;R=187;O;
^SMU;P0=-206;P1=-788;P2=889;P3=140;P4=-433;P5=527;P6=-328;P7=288;D=12121213434567474747474747474747474505074745050507450747474507474745050507474507450507450212121217474507474747474747474747474505074745050507450747474507474745050507474507450507474212121217474507474747474747474747474505074745050507450747474507474745050507;CP=7;R=187;O;
^SMU;P0=-454;P1=286;P2=547;P3=-184;P4=893;P5=-785;D=0102310232310234545454510102310101010101010101010102323101023232310231010102310101023232310;CP=1;R=184;
^SMU;P0=23992;P1=-1076;P2=1421;P3=620;P4=-7136;D=0121212131213121212121212131313121212121213121312131213121312131213121312131213131213124;CP=3;R=189;
^SMU;P0=-276;P1=100;P2=-200;P3=-1076;P4=1426;P5=614;P6=-7636;P7=280;D=3434343534353434343434343535353434343434353435343534353435343534353435343534353534353467012;CP=5;R=189;
^SMU;P0=31620;P1=-1065;P2=1438;P3=628;P4=-6932;D=0121212131213121313131212131313121212131213121312131313121212121213121312131313131212124;CP=3;R=189;
^SMU;P0=-248;P1=-1070;P2=1429;P3=628;P4=-6604;P5=252;P6=-176;P7=352;D=1212121312131213131312121313131212121312131213121313131212121212131213121313131312121245670;CP=3;R=189;
^SMU;P0=-188;P1=-921;P2=739;P3=268;P4=-406;P5=566;P6=-299;P7=350;D=12121213434563434343434343434347656505034745;CP=3;R=185;
^SMU;P0=-191;P1=-923;P2=750;P3=292;P4=-418;P5=526;P6=-272;D=1212121343456343434343434343434343450503430;CP=3;R=185;
^SMU;P0=339;P1=-392;P2=207;P3=578;P4=-197;P6=-292;P7=-145;D=01012121212121010101343401013434340134340631370101013737370;CP=0;R=186;
^SMU;P0=6564;P1=-1057;P2=1451;P3=621;P4=-6068;D=0121212131213121212121212131313121212121213121312131213121312131213121312131213131213124;CP=3;R=189;
^SMU;P0=-376;P1=200;P2=27212;P3=-1068;P4=1423;P5=629;P6=-5876;P7=100;D=2343434353435343434343434353535343434343435343534353435343534353435343534353435353435346701;CP=5;R=189;
^SMU;P0=229;P1=-1070;P2=1440;P3=622;P4=-6020;P5=-376;D=0121212131213121313131212131313121212121213121312131312121212121213121312131312121312134050;CP=3;R=188;
^SMU;P0=-780;P1=352;P2=-252;P3=-1073;P4=1444;P5=602;P6=-4780;P7=148;D=3434343534353435353534343535353434343434353435343535343434343434353435343535343435343567012;CP=5;R=188;
^SMU;P0=-202;P1=-956;P2=720;P3=155;P4=-429;P5=537;P6=-296;P7=306;D=12121213434567434347474747474747474505074745050507450747474507474745;CP=7;R=185;
^SMU;P0=551;P1=-178;P2=312;P3=-417;P4=-244;D=010123012423230123232301010123230123010121;CP=2;R=186;
^SMU;P0=-166;P1=318;P2=-438;P3=552;P4=148;P6=424;P7=-320;D=012121230301210403030301230121212301212123030301212306730301212;CP=1;R=186;
^SMU;P0=-195;P1=-924;P2=737;P3=298;P4=-443;P5=527;P6=-300;D=1212121343456343434343434343434343450503434505050345036;CP=3;R=186;
^SMU;P0=-178;P1=288;P2=-424;P3=-300;P4=540;P5=-128;P6=388;P7=-96;D=01213404012124040401240121212401212124040456217;CP=1;R=186;
^SMU;P0=5100;P1=-1062;P2=1449;P3=623;P4=-5340;D=0121212131213121212121212131313121212121213121312131213121312131213121312131213131213124;CP=3;R=186;
^SMU;P0=626;P1=-152;P2=29684;P3=-1180;P4=1442;P6=-4108;P7=100;D=234343430343034343434343430303034343434343034303430343034303430343034303430343030343034673012;CP=0;R=187;
^SMU;P0=1448;P1=-1064;P2=619;P3=-3832;P4=152;P5=-600;P6=226;P7=-112;D=0101010121012101212121010121212101010101012101210121210101010101012101210121210101210123456767;CP=2;R=186;
^SMU;P0=28568;P1=-1072;P2=1442;P3=621;P4=-4604;D=0121212131213121313131212131313121212121213121312131312121212121213121312131312121312134;CP=3;R=186;
^SMU;P0=-148;P1=-925;P2=741;P3=301;P4=-447;P5=494;P6=-300;P7=-214;D=1212121343456343434343434343434343457573430;CP=3;R=185;
^SMU;P0=-321;P1=318;P2=552;P3=-168;P4=-429;P5=-232;P6=724;D=0102323141423232314231414156314141423232310142314232313;CP=1;R=186;
`.trim().split('\n');

class EndOfSignalError extends Error { }

class BinarySignal {
    bits: number[];
    offset: number;
    readerHook?: (bit: number, offset: number) => void;

    constructor(bits: number[]) {
        this.bits = bits;
        this.offset = 0;
        this.readerHook = undefined;
    }

    matchAndStripHeader(header: number[], headerOffset: number = 0) {
        const headerCheckLength = header.length - headerOffset;

        for (let i = 0; i < headerCheckLength; i++) {
            if (this.bits[i] !== header[i + headerOffset]) {
                return false;
            }
        }

        this.offset += headerCheckLength;
        return true;
    }

    // headerMissingAllowed is so we can catch packets with part of the header cut off, as usually happens
    matchAndStripHeaderFuzzy(header: number[], headerMissingAllowed: number = 1) {
        for (let i = 0; i <= headerMissingAllowed; i++) {
            if (this.matchAndStripHeader(header, i)) {
                return true;
            }
        }
        return false;
    }

    readBit() {
        if (this.offset >= this.bits.length) {
            throw new EndOfSignalError();
        }

        const bit = this.bits[this.offset];
        if (this.readerHook) {
            this.readerHook(bit, this.offset);
        }
        this.offset++;
        return bit;
    }

    readBits(num: number) {
        const res = [];
        for (let i = 0; i < num; i++) {
            res.push(this.readBit());
        }
        return res;
    }

    readNumberLSBFirst(bits: number) {
        let res = 0;
        for (let i = 0; i < bits; i++) {
            res |= this.readBit() << i;
        }
        return res;
    }

    readNumberMSBFirst(bits: number) {
        let res = 0;
        for (let i = bits - 1; i >= 0; i--) {
            res |= this.readBit() << i;
        }
        return res;
    }
}

class RawSignal {
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

class NotImplementedError extends Error { } 

interface Signal {

}

abstract class SignalDecoder {
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

abstract class SignalPacketizer {
    abstract packetize(rawSignal: RawSignal): BinarySignal[];
}

class SignalPacketizerFixedVariable extends SignalPacketizer {
    tolerance: number;
    minLen: number;
    fixedPulse: number;
    zeroPulse: number;
    onePulse: number;

    constructor() {
        super();
        this.tolerance = 200;
        this.minLen = 5;
        this.fixedPulse = 0;
        this.zeroPulse = 0;
        this.onePulse = 0;
    }

    packetize(rawSignal: RawSignal) {
        const actualFixedPulse = rawSignal.findClosest(this.fixedPulse, this.tolerance);
        const actualZeroPulse = rawSignal.findClosest(this.zeroPulse, this.tolerance);
        const actualOnePulse = rawSignal.findClosest(this.onePulse, this.tolerance);

        if (!actualFixedPulse || !actualZeroPulse || !actualOnePulse) {
            return [];
        }

        const defaultPulse = (actualFixedPulse < 0) ? actualFixedPulse : actualZeroPulse;

        let signals = [];
        let curSignal = [];
        let lastTiming = defaultPulse;

        looptimings:
        for (const timing of rawSignal.timings) {
            if (timing != actualFixedPulse && timing != actualZeroPulse && timing != actualOnePulse) {
                if (curSignal.length >= this.minLen) {
                    signals.push(new BinarySignal(curSignal));
                }
                curSignal = [];
                lastTiming = defaultPulse;
                continue;
            }
            
            if (lastTiming == actualFixedPulse) {
                switch (timing) {
                    case actualFixedPulse:
                        continue looptimings;
                    case actualOnePulse:
                        curSignal.push(1);
                        break;
                    case actualZeroPulse:
                        curSignal.push(0);
                        break;
                }
            } else if (timing !== actualFixedPulse) {
                if (curSignal.length >= this.minLen) {
                    signals.push(new BinarySignal(curSignal));
                }
                curSignal = [];
            }

            lastTiming = timing;
        }

        if (curSignal.length > this.minLen) {
            signals.push(new BinarySignal(curSignal));
        }

        return signals;
    }
}

class LacrossePacketizer extends SignalPacketizerFixedVariable {
    constructor() {
        super();
        this.fixedPulse = -975;
        this.zeroPulse = 1400;
        this.onePulse = 550;
        this.minLen = 40;
    }
}

class SensorSignal implements Signal {
    constructor(public origin: string, public sensorType: string, public sensorId: string, public unit: string, public value: number) {

    }
}

class LacrosseSignalDecoder extends SignalDecoder {
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
                return new SensorSignal('lacrosse', 'temperature', sensorId, 'C', rawValue - 50.0);
            case 0b1110:
                return new SensorSignal('lacrosse', 'humidity', sensorId, '%', rawValue);
            default:
                return undefined;
        }
    }

    getPacketizerClass() {
        return LacrossePacketizer;
    }
}

function loadDecoders(decoders: SignalDecoder[]) {
    const packetizers = new Map();
    const decodersByPacketizer = new Map();
    
    for (const decoder of decoders) {
        const PacketizerClass = decoder.getPacketizerClass();
    
        if (!packetizers.has(PacketizerClass)) {
            const packetizer = new PacketizerClass();
            packetizers.set(PacketizerClass, packetizer);
            decodersByPacketizer.set(packetizer, []);
        }
    
        decodersByPacketizer.get(packetizers.get(PacketizerClass)).push(decoder);
    }

    return decodersByPacketizer;
}

const decodersByPacketizer = loadDecoders([new LacrosseSignalDecoder()]);

function processSignalLine(line: string) {
    const res = [];

    const rawSignal = RawSignal.fromString(line);
    for (const [packetizer, decoders] of decodersByPacketizer.entries()) {
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

for (const signalStr of signalStrings) {
    const res = processSignalLine(signalStr);
    for (const signal of res) {
        console.log(signal);
    }
}
