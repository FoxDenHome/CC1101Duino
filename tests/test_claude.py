"""The request sent to Claude and how its answer is read, against a fake client."""

import json
from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.cc1101duino.claude import (
    RESULT_SCHEMA,
    ClassificationError,
    async_classify,
    build_prompt,
)

RECORD = {
    "count": 4,
    "transmissions": 3,
    "first_seen": "2026-09-29T10:00:00+00:00",
    "last_seen": "2026-09-29T10:01:00+00:00",
    "intervals": [30.5, 30.0],
    "samples": [
        {"time": "2026-09-29T10:00:00+00:00", "rssi": -56, "line": "^SMU;P0=640;D=00;"},
        {"time": "2026-09-29T10:00:30+00:00", "rssi": -60, "line": "^SMU;P0=650;D=00;"},
    ],
}

ANSWER = {key: "" for key in RESULT_SCHEMA["required"]} | {"is_noise": False, "decoded_samples": []}


class Block(SimpleNamespace):
    def to_dict(self) -> dict[str, Any]:
        return dict(vars(self))


def message(stop_reason: str, *content: Block) -> SimpleNamespace:
    return SimpleNamespace(
        id="msg_1", model="claude-opus-5-5", usage=None, stop_reason=stop_reason, content=content
    )


class FakeClient:
    def __init__(self, *responses: SimpleNamespace) -> None:
        self.requests: list[dict[str, Any]] = []
        self._responses = list(responses)
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kwargs):
        # Copy, as the messages list is appended to between requests
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        response = self._responses.pop(0)

        class Stream:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def get_final_message(self):
                return response

        return Stream()


def test_prompt() -> None:
    prompt = build_prompt(RECORD)
    assert "4 times in 3 separate transmissions" in prompt
    assert "30, 30" in prompt
    assert "1. 2026-09-29T10:00:30+00:00 RSSI=-60 ^SMU;P0=650;D=00;" in prompt


async def test_classify() -> None:
    client = FakeClient(
        message(
            "end_turn",
            Block(type="text", text="Decoding"),
            Block(type="text", text=json.dumps(ANSWER)),
        )
    )
    result = await async_classify(client, "claude-opus-5-5", RECORD)
    assert result == ANSWER | {"model": "claude-opus-5-5"}

    (request,) = client.requests
    assert request["model"] == "claude-opus-5-5"
    assert request["output_config"]["format"]["schema"] is RESULT_SCHEMA
    assert request["tools"] == [{"type": "code_execution_20260521", "name": "code_execution"}]
    assert request["extra_body"] == {"fallbacks": "default"}


async def test_classify_resumes_paused_turn() -> None:
    tool_use = Block(type="server_tool_use", id="srvtoolu_1", name="bash_code_execution")
    client = FakeClient(
        message("pause_turn", tool_use),
        message("end_turn", Block(type="text", text=json.dumps(ANSWER))),
    )
    await async_classify(client, "claude-opus-5-5", RECORD)
    assert len(client.requests) == 2
    assert client.requests[1]["messages"][1] == {"role": "assistant", "content": [vars(tool_use)]}


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (message("refusal"), "declined"),
        (message("max_tokens", Block(type="text", text="{")), "cut off"),
        (message("end_turn"), "no answer"),
        (message("end_turn", Block(type="text", text="not json")), "not JSON"),
    ],
)
async def test_classify_errors(response: SimpleNamespace, error: str) -> None:
    with pytest.raises(ClassificationError, match=error):
        await async_classify(FakeClient(response), "claude-opus-5-5", RECORD)
