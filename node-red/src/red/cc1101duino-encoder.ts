import { coder } from "./util";

export default function (RED: any) {
    function CC1101DuinoEncoderNode(this: any, config: any) {
        const node = this;
        RED.nodes.createNode(node, config);
        node.on("input", function(msg: any) {
            node.send({
                ...msg,
                payload: coder.createSignalLine(msg.payload),
            });
        });
    }

    RED.nodes.registerType("cc1101duino-encoder", CC1101DuinoEncoderNode);
}
