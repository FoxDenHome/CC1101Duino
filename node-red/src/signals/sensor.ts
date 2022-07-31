import { Signal } from "./index";

export class SensorSignal extends Signal {
    constructor(public coder: string, public sensorType: string, public sensorId: string, public unit: string, public value: number) {
        super();
    }
}
