"""Shared Instructor wrapper for agenda and legacy LLM adapters."""

from typing import Any

import instructor
import openai


def wrap_with_instructor(client: Any) -> Any:
    """Wrap an injected async OpenAI-compatible client using Instructor JSON mode."""
    if isinstance(client, openai.OpenAI | openai.AsyncOpenAI):
        return instructor.from_openai(client, mode=instructor.Mode.JSON)
    return instructor.AsyncInstructor(
        client=client,
        create=instructor.patch(create=client.chat.completions.create, mode=instructor.Mode.JSON),
        mode=instructor.Mode.JSON,
    )
