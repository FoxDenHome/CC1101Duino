import { LineDecoder } from "../raw/line";

export default function (RED: any) {
    const lineDecoder = new LineDecoder();
    lineDecoder.loadAllDecoders();

    function CC1101DuinoDecoderNode(this: any, config: any) {
        const node = this;
        RED.nodes.createNode(node, config);
        node.on('input', function(msg: any) {
            for (const signal of lineDecoder.processSignalLine(msg.payload)) {
                node.send({
                    ...msg,
                    payload: signal,
                });
            }
        });
    }

    RED.nodes.registerType("cc1101duino-decoder", CC1101DuinoDecoderNode);
}
