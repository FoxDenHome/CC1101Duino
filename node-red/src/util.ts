export class NotSupportedException extends Error { }

export interface NumberRange {
    value: number;
    tolerance: number;
}

export const NUMER_RANGE_ZERO: NumberRange = {
    value: 0,
    tolerance: 0,
};
