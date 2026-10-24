import json

import httpx
import pytest

from src.plugin_api.llm import LLMConfig, OpenAIRequest

from backend import client as client_module
from backend.client import PLUGIN_ID, DeepSeekClient

BASE_URL = "https://api.deepseek.com"
AUTO = {"thinking": "auto", "reasoning_effort": "high"}
OFF = {"thinking": "off", "reasoning_effort": "high"}
TOOL = {"type": "function", "function": {"name": "list_presets", "parameters": {"type": "object", "properties": {}}}}
TOOL_CALL = {"id": "call_1", "type": "function", "function": {"name": "list_presets", "arguments": "{}"}}
PLAIN_HISTORY = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hello"}]
TOOL_HISTORY = PLAIN_HISTORY + [
    {"role": "assistant", "content": "", "tool_calls": [TOOL_CALL]},
    {"role": "tool", "content": "[]", "tool_call_id": "call_1"},
]
REPLY = {
    "choices": [{"message": {"content": "two presets"}, "finish_reason": "stop"}],
    "usage": {"total_tokens": 30, "prompt_tokens": 20, "completion_tokens": 10},
}


def request_with(messages, tools=None, **extra):
    params = {"temperature": 0.7, "max_completion_tokens": 4096, **extra}
    payload = {"model": "deepseek-flash", "messages": messages, **params}
    if tools:
        payload["tools"] = tools
    return OpenAIRequest(payload=payload, messages=messages, sampling_params=dict(params), headers={})


def config(**overrides):
    values = dict(
        id="cfg-1", name="DeepSeek", type="deepseek", enabled=True, base_url=BASE_URL, api_key="sk-test",
        model="deepseek-flash", system_message="SYS", max_tokens=4096, provider_options={"context_window": 1048576},
    )
    values.update(overrides)
    return LLMConfig(**values)


def adapt(settings, request):
    return DeepSeekClient(lambda: settings).adapt_request(request, config())


def test_a_request_without_tools_lets_deepseek_think_at_the_chosen_effort():
    request = adapt(AUTO, request_with(PLAIN_HISTORY))

    assert request.payload["thinking"] == {"type": "enabled"}
    assert request.payload["reasoning_effort"] == "high"


@pytest.mark.parametrize("settings, request_factory", [
    (AUTO, lambda: request_with(PLAIN_HISTORY, tools=[TOOL])),
    (AUTO, lambda: request_with(TOOL_HISTORY)),
    (OFF, lambda: request_with(PLAIN_HISTORY)),
])
def test_thinking_is_off_with_tools_a_tool_history_or_the_off_setting(settings, request_factory):
    request = adapt(settings, request_factory())

    assert request.payload["thinking"] == {"type": "disabled"}
    assert "reasoning_effort" not in request.payload


def test_a_reasoning_effort_already_in_the_request_gives_way_to_the_setting():
    assert adapt(AUTO, request_with(PLAIN_HISTORY, reasoning_effort="low")).payload["reasoning_effort"] == "high"
    assert "reasoning_effort" not in adapt(AUTO, request_with(PLAIN_HISTORY, [TOOL], reasoning_effort="low")).payload


def test_max_tokens_go_out_under_the_name_deepseek_reads_and_the_trace_says_the_same():
    request = adapt(AUTO, request_with(PLAIN_HISTORY))

    for params in (request.payload, request.sampling_params):
        assert params["max_tokens"] == 4096
        assert "max_completion_tokens" not in params
    assert request.sampling_params["thinking"] == request.payload["thinking"]


def test_the_rest_of_the_request_is_left_as_built():
    request = adapt(AUTO, request_with(PLAIN_HISTORY, tools=[TOOL]))

    assert (request.payload["model"], request.payload["messages"], request.payload["tools"]) == (
        "deepseek-flash", PLAIN_HISTORY, [TOOL],
    )
    assert request.payload["temperature"] == 0.7


def test_the_default_client_reads_this_plugins_settings(monkeypatch):
    asked = []
    monkeypatch.setattr(client_module, "plugin_settings", lambda plugin_id: asked.append(plugin_id) or OFF)

    request = DeepSeekClient().adapt_request(request_with(PLAIN_HISTORY), config())

    assert asked == [PLUGIN_ID]
    assert request.payload["thinking"] == {"type": "disabled"}


@pytest.fixture
def wire(monkeypatch):
    sent = []
    replies = []
    real_client = httpx.AsyncClient

    def handle(request):
        sent.append(request)
        return replies.pop(0)()

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handle)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return sent, replies


async def test_a_tool_turn_reaches_deepseek_with_thinking_off(wire):
    sent, replies = wire
    replies.append(lambda: httpx.Response(200, json=REPLY))

    response = await DeepSeekClient(lambda: AUTO).generate_with_tools(TOOL_HISTORY[1:], config(), "SYS", [TOOL])

    body = json.loads(sent[0].content)
    assert str(sent[0].url) == f"{BASE_URL}/chat/completions"
    assert sent[0].headers["authorization"] == "Bearer sk-test"
    assert body["thinking"] == {"type": "disabled"}
    assert body["max_tokens"] == 4096
    assert response.content == "two presets"


async def test_a_streamed_answer_without_tools_carries_deepseeks_reasoning(wire):
    sent, replies = wire
    events = [
        {"choices": [{"delta": {"reasoning_content": "The user greets me."}}]},
        {"choices": [{"delta": {"content": "Hello!"}, "finish_reason": "stop"}]},
    ]
    stream = "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"
    replies.append(lambda: httpx.Response(200, content=stream.encode(), headers={"content-type": "text/event-stream"}))

    received = [event async for event in DeepSeekClient(lambda: AUTO).stream_with_tools(PLAIN_HISTORY[1:], config(), "SYS")]

    assert json.loads(sent[0].content)["thinking"] == {"type": "enabled"}
    assert {"type": "thinking", "content": "The user greets me."} in received
    assert {"type": "token", "content": "Hello!"} in received
