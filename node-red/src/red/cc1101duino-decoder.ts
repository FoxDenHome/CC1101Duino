import { coder } from "./util";

export default function (RED: any) {
    function CC1101DuinoDecoderNode(this: any, config: any) {
        const node = this;
        RED.nodes.createNode(node, config);
        node.on('input', function(msg: any) {
            for (const signal of coder.processSignalLine(msg.payload)) {
                node.send({
                    ...msg,
                    payload: signal,
                });
            }
        });
    }

    RED.nodes.registerType("cc1101duino-decoder", CC1101DuinoDecoderNode);
}
