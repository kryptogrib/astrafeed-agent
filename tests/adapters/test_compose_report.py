from __future__ import annotations

import json

import pytest

from astrafeed.adapters.llm.openrouter import OpenRouterLLMClient
from astrafeed.report.dedup import MergedItem


class _Resp:
    def __init__(self, content):
        self.choices = [type("C", (), {"message": type("M", (), {"content": content})})]
        self.usage = type("U", (), {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.0})
        self.model = "strong"


class _Comp:
    def __init__(self, content):
        self._c = content
        self.seen = None

    async def create(self, **kw):
        self.seen = kw
        return _Resp(self._c)


class _Client:
    def __init__(self, content):
        self.completions = _Comp(content)
        self.chat = type("Chat", (), {"completions": self.completions})


def _m(imp, gist):
    return MergedItem(
        gist=gist,
        importance=imp,
        interests=("AI",),
        sources=(("h", "https://t.me/h/1"),),
        cluster_id=gist,
    )


@pytest.mark.asyncio
async def test_compose_report_returns_validated_plan():
    content = json.dumps(
        {
            "overview": "день AI",
            "groups": [
                {"title": "AI", "item_ids": ["0", "1"], "insight": None},
            ],
        }
    )
    llm = OpenRouterLLMClient(client=_Client(content), model="cheap", strong_model="strong")
    plan = await llm.compose_report([_m(5, "a"), _m(3, "b")], mode="format", language="ru")
    assert plan.overview == "день AI"
    assert plan.groups[0].item_ids == ["0", "1"]
    body = llm._client.completions.seen
    assert body["response_format"] == {"type": "json_object"}
    assert "https://t.me" not in json.dumps(body["messages"])
    assert "Language: ru" in body["messages"][1]["content"]
    assert "Prompt-Version: report-v2" in body["messages"][1]["content"]


@pytest.mark.asyncio
async def test_compose_report_malformed_json_raises_valueerror():
    llm = OpenRouterLLMClient(client=_Client("not json"), model="cheap", strong_model="strong")
    with pytest.raises(ValueError):
        await llm.compose_report([_m(5, "a")], mode="format", language="ru")


@pytest.mark.asyncio
async def test_compose_report_manifest_interests_is_json_array():
    captured: dict = {}

    class _C(_Comp):
        async def create(self, **kw):
            captured.update(kw)
            return _Resp(json.dumps({"overview": None, "groups": []}))

    client = _Client(json.dumps({"overview": None, "groups": []}))
    client.completions = _C(json.dumps({"overview": None, "groups": []}))
    client.chat = type("Chat", (), {"completions": client.completions})
    m = MergedItem(
        gist="g",
        importance=3,
        interests=("EU AI Act", "chips"),
        sources=(("h", "https://t.me/h/1"),),
        cluster_id="abc",
    )
    llm = OpenRouterLLMClient(client=client, model="cheap", strong_model="strong")
    await llm.compose_report([m], mode="format", language="ru")
    user_msg = captured["messages"][1]["content"]
    # interests must be a structured JSON array, not a comma-joined string
    assert '"interests":["EU AI Act","chips"]' in user_msg


@pytest.mark.asyncio
async def test_compose_report_manifest_escapes_interest_quotes():
    captured: dict = {}

    class _C(_Comp):
        async def create(self, **kw):
            captured.update(kw)
            return _Resp(json.dumps({"overview": None, "groups": []}))

    client = _Client(json.dumps({"overview": None, "groups": []}))
    client.completions = _C(json.dumps({"overview": None, "groups": []}))
    client.chat = type("Chat", (), {"completions": client.completions})
    m = MergedItem(
        gist="g",
        importance=3,
        interests=('AI "AGI"',),
        sources=(("h", "https://t.me/h/1"),),
        cluster_id="abc",
    )
    llm = OpenRouterLLMClient(client=client, model="cheap", strong_model="strong")
    await llm.compose_report([m], mode="format", language="ru")
    user_msg = captured["messages"][1]["content"]
    # the interests value must be valid JSON-escaped (contains backslash-escaped quote)
    assert '\\"AGI\\"' in user_msg
