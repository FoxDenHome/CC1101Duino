import { EndOfSignalError } from "./index";

export class BinarySignal {
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
