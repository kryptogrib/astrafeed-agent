"""OKX.AI A2MCP endpoint: one POST tool over the agenda read API.

OKX lists an A2MCP service as a single HTTPS endpoint that "takes some
parameters and returns a clear result"; its review sends a bare POST and
expects 200. So an empty body answers with the agenda, `query` searches and
`story_id` opens a card. Every call reads the published snapshot only.
"""

from collections.abc import Awaitable, Callable
from html import escape
from typing import Annotated, Any, Literal

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

A2MCP_PATH = "/a2mcp/astrafeed"

# Empty POST must stay HTTP 200 + agenda for the OKX listing self-check.
# `usage` and `preview` sit above `result` so a glance at the first kilobyte
# is enough to call the next action without opening a README.
A2MCP_USAGE = {
    "actions": {
        "agenda": "Empty body. Optional: snapshot_id, since_snapshot_id, format=json|md",
        "search": '{"query":"HYPE"} plus optional snapshot_id, limit, format',
        "story": '{"story_id":"st-…","snapshot_id":"snap-…"} plus optional format',
    },
    "rules": [
        "One action per call: empty body, query, or story_id",
        "since_snapshot_id is agenda-only; a missing baseline returns the full agenda",
        "Read-only: the call never runs the collector or the LLM",
    ],
}


class AstraFeedRequest(BaseModel):
    query: str | None = Field(
        default=None, description="Search stories by title, entity, alias or claim text."
    )
    story_id: str | None = Field(default=None, description="Open one story card with its sources.")
    snapshot_id: str | None = Field(
        default=None, description="Pin the call to a snapshot returned by a previous call."
    )
    since_snapshot_id: str | None = Field(
        default=None,
        description=(
            "Agenda only: return new/updated cards and changes since this snapshot. "
            "A missing baseline returns the full agenda with baseline_unavailable."
        ),
    )
    limit: int = Field(default=10, ge=1, le=50)
    format: Literal["json", "md"] = "json"


def _preview(action: str, result: dict[str, Any]) -> dict[str, Any]:
    if action == "agenda":
        return {
            "snapshot_id": result.get("snapshot_id"),
            "stories": [
                {
                    "story_id": card.get("story_id"),
                    "title": card.get("title"),
                    "current_channels": card.get("current_channels"),
                    "growth": card.get("growth"),
                }
                for card in (result.get("stories") or [])[:3]
            ],
        }
    if action == "search":
        return {
            "snapshot_id": result.get("snapshot_id"),
            "query": result.get("query"),
            "hits": [
                {"story_id": hit.get("story_id"), "title": hit.get("title")}
                for hit in (result.get("hits") or [])[:3]
            ],
        }
    story = result.get("story") or {}
    return {
        "snapshot_id": result.get("snapshot_id"),
        "story_id": story.get("story_id"),
        "title": story.get("title"),
    }


def _landing_html(result: dict[str, Any]) -> str:
    items = (
        "".join(
            f"<li><b>{escape(str(card.get('title') or ''))}</b> — "
            f"{escape(str(card.get('current_channels') or 0))} channels</li>"
            for card in (result.get("stories") or [])[:3]
        )
        or "<li>No stories in this snapshot.</li>"
    )
    snapshot = escape(str(result.get("snapshot_id") or ""))
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>AstraFeed</title></head><body>"
        "<h1>AstraFeed</h1>"
        "<p>Live crypto Telegram agenda. POST this URL; an empty body returns JSON.</p>"
        f"<pre>curl -sS -X POST https://cutememe.lol{A2MCP_PATH} "
        "-H 'content-type: application/json' -d '{}'</pre>"
        f"<p>Now: {snapshot}</p><ol>{items}</ol>"
        "<p><a href='/agenda?format=html'>Readable agenda</a></p>"
        "</body></html>"
    )


def mount_a2mcp(
    app: FastAPI,
    call: Callable[..., Awaitable[dict[str, Any]]],
    agenda: Callable[..., Any],
    stories_search: Callable[..., Any],
    story: Callable[..., Any],
) -> None:
    """`call` is app.py's _call_async, so errors map to the same HTTP codes as REST."""

    @app.get(A2MCP_PATH, response_class=HTMLResponse)
    async def astrafeed_open() -> HTMLResponse:
        """Browser hit of the tool URL: show how to call it, not a 405."""
        result = await call(agenda)
        return HTMLResponse(_landing_html(result))

    @app.post(A2MCP_PATH, response_model=None)
    async def astrafeed(
        req: Annotated[AstraFeedRequest | None, Body()] = None,
    ) -> dict[str, Any] | PlainTextResponse:
        """AstraFeed Crypto Agenda: empty POST returns the live agenda."""
        req = req or AstraFeedRequest()
        if req.query and req.story_id:
            raise HTTPException(status_code=422, detail="pass query or story_id, not both")
        if req.since_snapshot_id is not None and (req.query or req.story_id):
            raise HTTPException(
                status_code=422, detail="since_snapshot_id is supported only for agenda requests"
            )
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
            kwargs = {"snapshot_id": req.snapshot_id}
            if req.since_snapshot_id is not None:
                kwargs["since_snapshot_id"] = req.since_snapshot_id
            result = await call(agenda, **kwargs)
        if req.format == "md":
            return PlainTextResponse(
                result["brief_markdown"], media_type="text/markdown; charset=utf-8"
            )
        return {
            "service": "astrafeed",
            "action": action,
            "usage": A2MCP_USAGE,
            "preview": _preview(action, result),
            "result": result,
        }
