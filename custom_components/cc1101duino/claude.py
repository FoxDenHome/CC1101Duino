"""Asks Claude what kind of device an unrecognized signal comes from."""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

_LOGGER = logging.getLogger(__name__)

MAX_TOKENS = 64000
# Code execution pauses the turn after a number of server-side steps
MAX_CONTINUATIONS = 5
# fallbacks is not a parameter of older SDKs, such as the one Home Assistant's own Anthropic
# integration pins, so it is sent as extra_body
FALLBACK_BETA = "server-side-fallback-2026-07-01"

SYSTEM_PROMPT = """\
You analyze sub-GHz radio signals received by a CC1101 receiver that runs a SIGNALduino \
firmware and is attached to Home Assistant. The integration already decodes every ASK/OOK \
protocol of FHEM's SIGNALduino module (RFFHEM) and its client modules, plus LaCrosse TX, Nexus \
and Minka Aire, so the signals you get matched none of them: they are an unknown protocol, a \
variant of a known one that fails its checks, or noise. The receiver only demodulates ASK/OOK; \
FSK transmitters show up as noise or not at all.

Received lines use the SIGNALduino message format, prefixed with ^S and followed by this \
firmware's F=<MHz>;M=<modulation> (2 = ASK/OOK):
- MU (unsynced) and MS (synced) messages: P<n>=<µs> defines pulse n, positive for a high \
(carrier on) pulse and negative for a low one. D=<digits> is the sequence of pulses as received, \
by index. CP is the index of the clock pulse, SP that of the sync pulse. R is the RSSI as the \
firmware reports it.
- MC (Manchester) messages: LL/LH/SL/SH are the long/short low/high pulse lengths in µs, D is \
the demodulated data in hex, C the clock in µs and L the length in bits.

All samples you get have similar pulse timings, so they most likely come from one kind of \
device (or noise that happens to look alike); several devices of the same model may be among \
them. Use code execution to demodulate the pulses: find the encoding (PWM, PPM, Manchester, \
...), split the samples into packets, decode their bits, and compare the samples to find which \
bits are fixed (preamble, ID, type) and which vary (readings, button codes, counters, \
checksums). Check candidate checksums and CRCs. Relate the result to protocols you know from \
rtl_433, SIGNALduino, pilight, RFLink, or datasheets of common encoder chips (PT2262, EV1527, \
HT12E, ...). How often the device transmits tells sensors (periodic) from remotes, doorbells \
and alarms (on demand).

Say plainly what you are unsure about. If the samples are noise or interference, say so.
"""

RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "is_noise": {
            "type": "boolean",
            "description": "Whether the samples are noise or interference rather than data",
        },
        "category": {
            "type": "string",
            "enum": [
                "weather_sensor",
                "temperature_sensor",
                "remote_control",
                "doorbell",
                "door_window_sensor",
                "motion_sensor",
                "smoke_detector",
                "water_leak_sensor",
                "energy_meter",
                "tire_pressure_sensor",
                "car_key",
                "garage_door",
                "blinds",
                "switch",
                "other",
                "unknown",
                "noise",
            ],
        },
        "device": {
            "type": "string",
            "description": "Most likely device, manufacturer or model family",
        },
        "protocol": {
            "type": "string",
            "description": "Closest known protocol or decoder (e.g. rtl_433 decoder name)",
        },
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "summary": {
            "type": "string",
            "description": "One or two sentences for the user on what this signal is",
        },
        "encoding": {
            "type": "string",
            "description": "Modulation and bit encoding, with the pulse timings of each symbol",
        },
        "packet_structure": {
            "type": "string",
            "description": "Preamble, sync, fields with bit positions, checksum, repeats",
        },
        "decoded_samples": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sample": {"type": "integer", "description": "Index of the sample"},
                    "bits": {"type": "string"},
                    "hex": {"type": "string"},
                    "interpretation": {"type": "string"},
                },
                "required": ["sample", "bits", "hex", "interpretation"],
                "additionalProperties": False,
            },
        },
        "decoder_hint": {
            "type": "string",
            "description": "How to write a decoder for it: packetizer, bit layout, checks",
        },
    },
    "required": [
        "is_noise",
        "category",
        "device",
        "protocol",
        "confidence",
        "summary",
        "encoding",
        "packet_structure",
        "decoded_samples",
        "decoder_hint",
    ],
    "additionalProperties": False,
}


class ClassificationError(Exception):
    """Claude could not be asked, or gave no usable answer."""


class AuthenticationFailed(ClassificationError):
    """The API key was rejected; retrying will not help."""


def build_prompt(record: dict[str, Any]) -> str:
    """Describe one unknown signal type, with its samples, for Claude."""
    lines = [
        f"Received {record['count']} times in {record['transmissions']} separate "
        f"transmissions between {record['first_seen']} and {record['last_seen']}.",
    ]
    if intervals := record.get("intervals"):
        lines.append(
            "Seconds between consecutive transmissions: "
            + ", ".join(f"{interval:.0f}" for interval in intervals)
        )
    lines.append("")
    lines.append("Samples (time, RSSI in dBm, line):")
    for index, sample in enumerate(record["samples"]):
        lines.append(f"{index}. {sample['time']} RSSI={sample['rssi']} {sample['line']}")
    return "\n".join(lines)


async def async_classify(
    client: anthropic.AsyncAnthropic, model: str, record: dict[str, Any]
) -> dict[str, Any]:
    """Ask Claude to classify an unknown signal type, returning its RESULT_SCHEMA answer."""
    messages: list[dict[str, Any]] = [{"role": "user", "content": build_prompt(record)}]
    try:
        for _ in range(MAX_CONTINUATIONS + 1):
            async with client.beta.messages.stream(
                model=model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=messages,
                thinking={"type": "adaptive"},
                output_config={
                    "effort": "high",
                    "format": {"type": "json_schema", "schema": RESULT_SCHEMA},
                },
                tools=[{"type": "code_execution_20260521", "name": "code_execution"}],
                betas=[FALLBACK_BETA],
                extra_body={"fallbacks": "default"},
            ) as stream:
                response = await stream.get_final_message()
            _LOGGER.debug("Classification response %s: %s", response.id, response.usage)
            if response.stop_reason != "pause_turn":
                break
            # Resume the paused server-side tool loop where it stopped; consecutive assistant
            # messages are joined into one turn
            messages.append(
                {"role": "assistant", "content": [block.to_dict() for block in response.content]}
            )
    except anthropic.AuthenticationError as err:
        raise AuthenticationFailed(f"Anthropic rejected the API key: {err.message}") from err
    except anthropic.APIStatusError as err:
        raise ClassificationError(f"Anthropic API error {err.status_code}: {err.message}") from err
    except anthropic.APIConnectionError as err:
        raise ClassificationError(f"Cannot reach the Anthropic API: {err}") from err

    if response.stop_reason == "refusal":
        raise ClassificationError("Claude declined to classify the signal")
    if response.stop_reason == "max_tokens":
        raise ClassificationError("Claude's answer was cut off")
    if response.stop_reason == "pause_turn":
        raise ClassificationError("Claude did not finish within the step limit")

    texts = [block.text for block in response.content if block.type == "text"]
    if not texts:
        raise ClassificationError("Claude gave no answer")
    try:
        result = json.loads(texts[-1])
    except json.JSONDecodeError as err:
        raise ClassificationError(f"Claude's answer is not JSON: {err}") from err
    result["model"] = response.model
    return result
