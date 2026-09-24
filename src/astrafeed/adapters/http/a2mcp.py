"""OKX.AI A2MCP endpoint: one POST tool over the agenda read API.

OKX lists an A2MCP service as a single HTTPS endpoint that "takes some
parameters and returns a clear result"; its review sends a bare POST and
expects 200. So an empty body answers with the agenda, `query` searches and
`story_id` opens a card. Every call reads the published snapshot only.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

A2MCP_PATH = "/a2mcp/crowd-pulse"


class CrowdPulseRequest(BaseModel):
    query: str | None = Field(
        None, description="Search stories by title, entity, alias or claim text."
    )
    story_id: str | None = Field(None, description="Open one story card with its sources.")
    snapshot_id: str | None = Field(
        None, description="Pin the call to a snapshot returned by a previous call."
    )
    limit: int = Field(10, ge=1, le=50)
    format: Literal["json", "md"] = "json"


def mount_a2mcp(
    app: FastAPI,
    call: Callable[..., Awaitable[dict[str, Any]]],
    agenda: Callable[..., Any],
    stories_search: Callable[..., Any],
    story: Callable[..., Any],
) -> None:
    """`call` is app.py's _call_async, so errors map to the same HTTP codes as REST."""

    @app.post(A2MCP_PATH, response_model=None)
    async def crowd_pulse(
        req: Annotated[CrowdPulseRequest | None, Body()] = None,
    ) -> dict[str, Any] | PlainTextResponse:
        req = req or CrowdPulseRequest()
        if req.query and req.story_id:
            raise HTTPException(status_code=422, detail="pass query or story_id, not both")
        if req.story_id:
            action = "story"
            result = await call(story, story_id=req.story_id, snapshot_id=req.snapshot_id)
        elif req.query:
            action = "search"
            result = await call(
                stories_search,
                q=req.query,
                snapshot_id=req.snapshot_id,
                limit=req.limit,
                offset=0,
            )
        else:
            action = "agenda"
            result = await call(agenda, snapshot_id=req.snapshot_id)
        if req.format == "md":
            return PlainTextResponse(
                result["brief_markdown"], media_type="text/markdown; charset=utf-8"
            )
        return {"service": "crowd-pulse", "action": action, "result": result}
