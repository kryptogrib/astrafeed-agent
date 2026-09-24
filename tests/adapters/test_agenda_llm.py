from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrafeed.adapters.llm import agenda as agenda_llm
from astrafeed.domain.agenda import IndexedFragment


def test_assignment_payload_keeps_evidence_but_omits_embedding_vectors():
    fragment = IndexedFragment(
        publication_id="new:1",
        published_at=datetime(2026, 9, 24, tzinfo=UTC),
        fragment_index=0,
        text="Отток ETH ETF составил $120 млн.",
        entity_surfaces=("ETH ETF",),
        claim_text="Отток ETH ETF составил $120 млн.",
        vector=[0.123456789] * 1536,
    )
    candidate = IndexedFragment(
        publication_id="older:1",
        published_at=datetime(2026, 9, 23, tzinfo=UTC),
        fragment_index=0,
        text="Отток ETH ETF",
        entity_surfaces=("ETH ETF",),
        claim_text="Отток ETH ETF",
        vector=[0.987654321] * 1536,
    )

    payload = agenda_llm._assignment_user(fragment=fragment, candidates=[candidate])

    assert "Отток ETH ETF составил $120 млн." in payload
    assert "older:1" in payload
    assert "0.123456789" not in payload
    assert "0.987654321" not in payload
    assert "vector" not in payload


@pytest.mark.asyncio
async def test_agenda_chat_calls_disable_hidden_reasoning(monkeypatch):
    monkeypatch.setattr(agenda_llm, "_wrap_with_instructor", lambda client: client)
    extraction_call = AsyncMock(return_value=agenda_llm.ExtractionSchema())
    assignment_call = AsyncMock(
        return_value=agenda_llm.AssignmentSchema(story_decision="ambiguous")
    )
    extractor = agenda_llm.OpenRouterExtractor(
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=extraction_call))),
        "deepseek/deepseek-v4-flash",
    )
    assigner = agenda_llm.OpenRouterAssigner(
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=assignment_call))),
        "deepseek/deepseek-v4-flash",
    )

    await extractor.extract("Короткий пост")
    await assigner.assign(fragment="Короткий пост")

    for call in (extraction_call, assignment_call):
        assert call.await_args.kwargs["extra_body"]["reasoning"] == {"enabled": False}
    assert assignment_call.await_args.kwargs["extra_body"]["provider"] == {"sort": "throughput"}


@pytest.mark.asyncio
async def test_agenda_chat_calls_are_deterministic_and_fence_the_post(monkeypatch):
    monkeypatch.setattr(agenda_llm, "_wrap_with_instructor", lambda client: client)
    extraction_call = AsyncMock(return_value=agenda_llm.ExtractionSchema())
    assignment_call = AsyncMock(
        return_value=agenda_llm.AssignmentSchema(story_decision="ambiguous")
    )
    evidence_call = AsyncMock(return_value=agenda_llm.EvidenceSchema(supported=[True]))

    def client(call):
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=call)))

    await agenda_llm.OpenRouterExtractor(client(extraction_call), "m").extract("Короткий пост")
    await agenda_llm.OpenRouterAssigner(client(assignment_call), "m").assign(fragment="пост")
    story = SimpleNamespace(title_ru="Сюжет", boundary="граница")
    await agenda_llm.OpenRouterEvidenceVerifier(client(evidence_call), "m").verify(story, ["q"])

    for call in (extraction_call, assignment_call, evidence_call):
        assert call.await_args.kwargs["temperature"] == 0
    user = extraction_call.await_args.kwargs["messages"][1]["content"]
    assert user == "<post>\nКороткий пост\n</post>"


@pytest.mark.asyncio
async def test_batched_embeddings_follow_input_indices():
    create = AsyncMock(
        return_value=SimpleNamespace(
            data=[
                SimpleNamespace(index=1, embedding=[0.0, 1.0]),
                SimpleNamespace(index=0, embedding=[1.0, 0.0]),
            ]
        )
    )
    embedder = agenda_llm.OpenRouterEmbedder(
        SimpleNamespace(embeddings=SimpleNamespace(create=create))
    )

    vectors = await embedder.embed(["first", "second"])

    assert vectors == [[1.0, 0.0], [0.0, 1.0]]
