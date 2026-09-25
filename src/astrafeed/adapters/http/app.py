import inspect
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse

from astrafeed.adapters.http.a2mcp import mount_a2mcp
from astrafeed.application.agenda_html import render_agenda_html, render_story_html
from astrafeed.application.agenda_query import AgendaNotFound, AgendaPreparing

_FAVICON = Path(__file__).with_name("static") / "favicon.ico"

PulseFn = Callable[[str, str | None], dict[str, Any]]
"""Pulse(topic, window) -> payload.

Raises LookupError for an unknown topic, ValueError for a bad window.
"""

CompareFn = Callable[[str, str, str], dict[str, Any]]
"""Compare(topic, a, b) -> payload with "markdown"; same errors as PulseFn."""

NewsPulseFn = Callable[[str, str], dict[str, Any]]
"""News-first Pulse(topic, window) -> payload. Window is required.

Raises LookupError for a missing cached run, ValueError for a bad window.
HTTP must not call the network; the provider reads cache only.
"""

AgendaFn = Callable[..., dict[str, Any] | Awaitable[dict[str, Any]]]
SearchFn = Callable[..., dict[str, Any] | Awaitable[dict[str, Any]]]
StoryFn = Callable[..., dict[str, Any] | Awaitable[dict[str, Any]]]
HealthFn = Callable[..., dict[str, Any] | Awaitable[dict[str, Any]]]


def _call(fn: Callable[..., dict[str, Any]], *args: Any) -> dict[str, Any]:
    try:
        return fn(*args)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


async def _call_async(fn: Callable[..., Any], **kwargs: Any) -> dict[str, Any]:
    try:
        result = fn(**kwargs)
        if inspect.isawaitable(result):
            result = await result
        return result
    except AgendaPreparing:
        raise
    except AgendaNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


def _markdown(text: str) -> PlainTextResponse:
    return PlainTextResponse(text, media_type="text/markdown; charset=utf-8")


def create_app(
    pulse: PulseFn | None = None,
    compare: CompareFn | None = None,
    news_pulse: NewsPulseFn | None = None,
    info: dict[str, Any] | None = None,
    agenda: AgendaFn | None = None,
    stories_search: SearchFn | None = None,
    story: StoryFn | None = None,
    health: HealthFn | None = None,
) -> FastAPI:
    """info is added to /healthz as is (e.g. commit and data fingerprint of a demo run)."""
    app = FastAPI(title="AstraFeed")

    @app.exception_handler(AgendaPreparing)
    async def preparing_handler(_request: Request, _exc: AgendaPreparing) -> JSONResponse:
        return JSONResponse({"status": "preparing"}, status_code=503)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(_FAVICON, media_type="image/x-icon")

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        if health is not None:
            extra = health()
            if inspect.isawaitable(extra):
                extra = await extra
            return extra
        return {"status": "ok", **(info or {})}

    if pulse is not None:

        @app.get("/pulse", response_model=None)
        def get_pulse(
            topic: str, window: str | None = None, format: Literal["json", "md"] = "json"
        ) -> dict[str, Any] | PlainTextResponse:
            result = _call(pulse, topic, window)
            return _markdown(result["brief_markdown"]) if format == "md" else result

    if compare is not None:

        @app.get("/pulse/compare", response_model=None)
        def get_compare(
            topic: str, a: str, b: str, format: Literal["json", "md"] = "json"
        ) -> dict[str, Any] | PlainTextResponse:
            result = _call(compare, topic, a, b)
            return _markdown(result["markdown"]) if format == "md" else result

    if news_pulse is not None:

        @app.get("/news-pulse", response_model=None)
        def get_news_pulse(
            topic: str, window: str, format: Literal["json", "md"] = "json"
        ) -> dict[str, Any] | PlainTextResponse:
            result = _call(news_pulse, topic, window)
            return _markdown(result["brief_markdown"]) if format == "md" else result

    if agenda is not None:

        @app.get("/agenda", response_model=None)
        async def get_agenda(
            format: Literal["json", "md", "html"] = "json",
            snapshot_id: str | None = None,
            since_snapshot_id: str | None = None,
        ) -> dict[str, Any] | PlainTextResponse | HTMLResponse:
            kwargs = {"snapshot_id": snapshot_id}
            if since_snapshot_id is not None:
                kwargs["since_snapshot_id"] = since_snapshot_id
            result = await _call_async(agenda, **kwargs)
            if format == "html":
                return HTMLResponse(render_agenda_html(result))
            if format == "md":
                return _markdown(result["brief_markdown"])
            return result

    if stories_search is not None:

        @app.get("/stories/search", response_model=None)
        async def get_stories_search(
            q: str,
            format: Literal["json", "md"] = "json",
            snapshot_id: str | None = None,
            limit: int = 10,
            offset: int = 0,
        ) -> dict[str, Any] | PlainTextResponse:
            result = await _call_async(
                stories_search,
                q=q,
                snapshot_id=snapshot_id,
                limit=limit,
                offset=offset,
            )
            if format == "md":
                return _markdown(result["brief_markdown"])
            return result

    if story is not None:

        @app.get("/stories/{story_id}", response_model=None)
        async def get_story(
            story_id: str,
            format: Literal["json", "md", "html"] = "json",
            snapshot_id: str | None = None,
        ) -> dict[str, Any] | PlainTextResponse | HTMLResponse:
            result = await _call_async(story, story_id=story_id, snapshot_id=snapshot_id)
            if format == "html":
                return HTMLResponse(render_story_html(result))
            if format == "md":
                return _markdown(result["brief_markdown"])
            return result

    if agenda is not None and stories_search is not None and story is not None:
        mount_a2mcp(app, _call_async, agenda, stories_search, story)

    return app
