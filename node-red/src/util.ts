export class NotSupportedException extends Error { }

export interface PulseDefinition {
    length: number;
    tolerance: number;
}

export const PULSE_ZERO = {
    length: 0,
    tolerance: 0,
};
