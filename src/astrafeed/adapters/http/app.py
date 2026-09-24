from collections.abc import Callable
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse

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


def _call(fn: Callable[..., dict[str, Any]], *args: Any) -> dict[str, Any]:
    try:
        return fn(*args)
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
) -> FastAPI:
    """info is added to /healthz as is (e.g. commit and data fingerprint of a demo run)."""
    app = FastAPI(title="AstraFeed Token Brief")

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
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

    return app
