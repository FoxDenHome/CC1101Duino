import { coder } from "./util";

export default function (RED: any) {
    function CC1101DuinoDecoderNode(this: any, config: any) {
        const node = this;
        RED.nodes.createNode(node, config);
        node.on("input", function(msg: any) {
            const signals = coder.processSignalLine(msg.payload);

            if (signals.length < 1) {
                node.send([null, msg]);
                return;
            }

            for (const signal of signals) {
                node.send([{
                    ...msg,
                    payload: signal,
                }, null]);
            }
        });
    }

    RED.nodes.registerType("cc1101duino-decoder", CC1101DuinoDecoderNode);
}
