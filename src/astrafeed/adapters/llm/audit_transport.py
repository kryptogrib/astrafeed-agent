from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import httpx

from astrafeed.application.audit import current_audit_context
from astrafeed.domain.audit import JSON, AuditEvent, AuditEventKind, PayloadState
from astrafeed.ports.audit import AuditSink

# Allowlisted response headers only — never the full header set (may carry
# provider auth echoes / rate-limit account identifiers).
_ALLOWED_RESPONSE_HEADERS = ("x-request-id",)


def safe_payload(
    body: bytes, secrets: Sequence[str], max_bytes: int
) -> tuple[PayloadState, JSON | None, int]:
    """Redact known secrets and bound what a caller may pass on to the audit sink.

    Returns (state, sanitized_json_or_None, original_bytes). ``captured`` carries a
    JSON-shaped body (parsed if valid JSON, else a raw-text wrapper); anything over
    ``max_bytes`` is entirely omitted, never truncated in place (a truncated JSON/API
    key fragment is worse than no capture).
    """
    original_bytes = len(body)
    if original_bytes > max_bytes:
        return PayloadState.OMITTED_SIZE, None, original_bytes
    text = body.decode("utf-8", errors="replace")
    redacted = False
    for secret in secrets:
        if secret and secret in text:
            text = text.replace(secret, "[REDACTED]")
            redacted = True
    try:
        parsed: JSON = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        parsed = {"raw_text": text}
    state = PayloadState.REDACTED if redacted else PayloadState.CAPTURED
    return state, parsed, original_bytes


def _response_headers(response: httpx.Response) -> dict[str, JSON]:
    return {
        key: value
        for key, value in response.headers.items()
        if key.lower() in _ALLOWED_RESPONSE_HEADERS
    }


class AuditTransport(httpx.AsyncBaseTransport):
    """Wraps every outbound HTTPX request (SDK retries included) with a best-effort audit trail.

    One transport attempt per physical HTTP call; a single logical LLM call (set by the
    caller via ``audit_scope``'s ``logical_call_id``) may span several attempts across
    SDK/Instructor retries. Never alters the inner transport's exception or response
    semantics, and never issues a network call of its own.
    """

    def __init__(
        self,
        inner: httpx.AsyncBaseTransport,
        sink: AuditSink,
        secrets: Sequence[str] = (),
        *,
        max_payload_bytes: int = 2 * 1024 * 1024,
    ) -> None:
        self._inner = inner
        self._sink = sink
        self._secrets = tuple(secrets)
        self._max_payload_bytes = max_payload_bytes

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        context = current_audit_context()
        attempt_id = str(uuid.uuid4())
        body = await request.aread()

        if context is not None:
            state, request_json, original_bytes = safe_payload(
                body, self._secrets, self._max_payload_bytes
            )
            await self._sink.begin_attempt(
                AuditEvent(
                    id=attempt_id,
                    context=context,
                    kind=AuditEventKind.ATTEMPT_STARTED,
                    occurred_at=datetime.now(UTC),
                    data={
                        "request_json": request_json,
                        "payload_state": state.value,
                        "original_bytes": original_bytes,
                    },
                )
            )

        try:
            response = await self._inner.handle_async_request(request)
        except asyncio.CancelledError:
            if context is not None:
                self._sink.emit(
                    AuditEvent(
                        id=f"{attempt_id}:finished",
                        context=context,
                        kind=AuditEventKind.ATTEMPT_FINISHED,
                        occurred_at=datetime.now(UTC),
                        data={"result": "cancelled", "error_class": "CancelledError"},
                    )
                )
            raise
        except httpx.TimeoutException as exc:
            if context is not None:
                self._sink.emit(
                    AuditEvent(
                        id=f"{attempt_id}:finished",
                        context=context,
                        kind=AuditEventKind.ATTEMPT_FINISHED,
                        occurred_at=datetime.now(UTC),
                        data={"result": "timeout", "error_class": type(exc).__name__},
                    )
                )
            raise
        except Exception as exc:
            if context is not None:
                self._sink.emit(
                    AuditEvent(
                        id=f"{attempt_id}:finished",
                        context=context,
                        kind=AuditEventKind.ATTEMPT_FINISHED,
                        occurred_at=datetime.now(UTC),
                        data={"result": "provider_error", "error_class": type(exc).__name__},
                    )
                )
            raise

        if context is None:
            return response

        # Bounded capture of the actual bytes returned to the caller; streaming
        # (v1: non-streaming completions only) is out of scope and marked unsupported.
        is_stream = "stream" in (response.headers.get("content-type") or "").lower()
        if is_stream:
            self._sink.emit(
                AuditEvent(
                    id=f"{attempt_id}:finished",
                    context=context,
                    kind=AuditEventKind.ATTEMPT_FINISHED,
                    occurred_at=datetime.now(UTC),
                    data={"result": "succeeded", "payload_state": PayloadState.UNAVAILABLE.value},
                )
            )
            return response

        # Read the inner response in place. Rebuilding a Response with the
        # original content-encoding (gzip) headers around already-decoded
        # bytes makes httpx gunzip JSON and raises DecodingError — which the
        # SDK then retries, adding paid calls. After aread(), _content is set
        # and the original object is safe to return to the caller.
        response_body = await response.aread()
        state, response_json, original_bytes = safe_payload(
            response_body, self._secrets, self._max_payload_bytes
        )
        http_ok = 200 <= response.status_code < 300
        self._sink.emit(
            AuditEvent(
                id=f"{attempt_id}:finished",
                context=context,
                kind=AuditEventKind.ATTEMPT_FINISHED,
                occurred_at=datetime.now(UTC),
                data={
                    "result": "succeeded" if http_ok else "http_error",
                    "status_code": response.status_code,
                    "response_json": response_json,
                    "payload_state": state.value,
                    "original_bytes": original_bytes,
                    "provider_headers": _response_headers(response),
                },
            )
        )
        return response

    async def aclose(self) -> None:
        await self._inner.aclose()
