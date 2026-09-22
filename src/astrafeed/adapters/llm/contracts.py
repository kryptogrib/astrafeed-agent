from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, PrivateAttr, ValidationInfo, field_validator, model_validator

from astrafeed.adapters.llm.prompts import SCORE_SYSTEM, SCORE_SYSTEM_V8
from astrafeed.domain import Route

ScoreVersion = Literal["score-v7", "score-v8"]


def record_anomaly(info: ValidationInfo, kind: str, external_id: str | None = None) -> None:
    """Append the verdict's external_id to ``kind`` on the per-call collector.
    A no-op when no collector is present — validators never raise."""
    ctx = info.context or {}
    anomalies = ctx.get("anomalies")
    if anomalies is None:
        return
    eid = external_id if external_id is not None else str(info.data.get("external_id", "?"))
    getattr(anomalies, kind).append(eid)


class _VerdictSchema(BaseModel):
    external_id: str
    route: Route
    matched_interests: list[str] = []
    summary: str = ""
    rationale: str = ""
    importance: int = 1
    urgent_candidate: bool = False
    urgent_interest: str = ""
    urgent_reason: str = ""
    # "actor|action|object" naming the event, normalized. A recall aid for report
    # dedup only — never a gate, so a missing or malformed key costs the item
    # nothing and both score contracts can carry it.
    event_key: str = ""

    @field_validator("event_key", mode="before")
    @classmethod
    def _normalize_event_key(cls, v: Any) -> str:
        if not isinstance(v, str):
            return ""
        parts = [" ".join(p.split()).casefold() for p in v.split("|") if p.strip()]
        if len(parts) < 2:  # a lone word names a topic, not an event
            return ""
        return "|".join(parts)

    @field_validator("urgent_candidate", mode="before")
    @classmethod
    def _coerce_urgent_candidate(cls, v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in {"true", "1", "yes"}
        return bool(v)

    @field_validator("urgent_interest", "urgent_reason", mode="before")
    @classmethod
    def _coerce_urgent_text(cls, v: Any) -> str:
        return v.strip() if isinstance(v, str) else ""

    @field_validator("external_id", mode="before")
    @classmethod
    def _coerce_external_id(cls, v: Any) -> str:
        # The LLM sometimes returns ids as numbers; ids are opaque strings here.
        return str(v)

    @field_validator("route", mode="before")
    @classmethod
    def _coerce_route(cls, v: Any, info: ValidationInfo) -> Any:
        # The cheap model only offers report/drop now. Any unknown or legacy
        # value — e.g. a stray "alert" from a cached prompt — maps to drop
        # defensively so one odd token can't fail the whole batch (ADR-0002).
        # Non-raising: record the coercion, never re-ask.
        if isinstance(v, str) and v in (Route.REPORT.value, Route.DROP.value):
            return v
        record_anomaly(info, "route_coerced")
        return Route.DROP.value

    @field_validator("importance", mode="before")
    @classmethod
    def _clamp_importance(cls, v: Any, info: ValidationInfo) -> int:
        # Clamp into the 1–5 scale without raising; record when out of range or
        # unparseable so the adapter can surface model drift in aggregate.
        try:
            n = int(v)
        except (TypeError, ValueError):
            record_anomaly(info, "importance_out_of_range")
            return 1
        if n < 1 or n > 5:
            record_anomaly(info, "importance_out_of_range")
            return max(1, min(5, n))
        return n

    @field_validator("matched_interests", mode="before")
    @classmethod
    def _coerce_matched_interests(cls, v: Any, info: ValidationInfo) -> Any:
        # Filter to the EFFECTIVE Interests threaded via validation context.
        # Configured Interests can themselves contain commas, so naive
        # comma-splitting is destructive: test the whole string for an exact
        # match FIRST, and only comma-split as a recorded fallback. Non-raising.
        configured = (info.context or {}).get("interests")
        if configured is None:
            # No effective-interest set in context: best-effort normalize only.
            if isinstance(v, str):
                return [part.strip() for part in v.split(",") if part.strip()]
            return v if isinstance(v, list) else []

        if isinstance(v, list):
            kept = [s for s in v if s in configured]
            if len(kept) != len(v):
                record_anomaly(info, "matched_interest_dropped")
            return kept

        if isinstance(v, str):
            if v in configured:  # exact whole-string match wins (commas intact)
                return [v]
            # Whole-string match failed → comma-split fallback (the model likely
            # ignored "return an array"); record the fallback, then filter.
            record_anomaly(info, "matched_interest_comma_fallback")
            parts = [part.strip() for part in v.split(",") if part.strip()]
            kept = [p for p in parts if p in configured]
            if len(kept) != len(parts):
                record_anomaly(info, "matched_interest_dropped")
            return kept

        return []


class _BatchV7(BaseModel):
    verdicts: list[_VerdictSchema]


class _VerdictSchemaV8(_VerdictSchema):
    _validation_failed: bool = PrivateAttr(default=False)
    new_fact: str = ""
    evidence: str = ""

    @model_validator(mode="after")
    def _require_new_fact(self, info: ValidationInfo) -> _VerdictSchemaV8:
        if self.route != Route.REPORT:
            return self
        texts = (info.context or {}).get("item_texts") or {}
        text = texts.get(self.external_id, "")
        if not (self.new_fact or "").strip():
            record_anomaly(info, "empty_new_fact", self.external_id)
            self._validation_failed = True
            self.route = Route.DROP
            return self
        evidence = (self.evidence or "").strip()
        if not evidence:
            record_anomaly(info, "evidence_missing", self.external_id)
            self._validation_failed = True
            self.route = Route.DROP
            return self
        if " ".join(evidence.split()) not in " ".join(text.split()):
            record_anomaly(info, "evidence_missing", self.external_id)
            self._validation_failed = True
            self.route = Route.DROP
        return self


class _BatchV8(BaseModel):
    verdicts: list[_VerdictSchemaV8]


@dataclass(frozen=True)
class ScoreContract:
    """System prompt + response schema + validators, selected at client creation."""

    version: ScoreVersion
    system: str
    verdict_schema: type[BaseModel]
    batch_schema: type[BaseModel]


SCORE_V7 = ScoreContract(
    version="score-v7",
    system=SCORE_SYSTEM,
    verdict_schema=_VerdictSchema,
    batch_schema=_BatchV7,
)

SCORE_V8 = ScoreContract(
    version="score-v8",
    system=SCORE_SYSTEM_V8,
    verdict_schema=_VerdictSchemaV8,
    batch_schema=_BatchV8,
)


def get_score_contract(version: str) -> ScoreContract:
    if version == SCORE_V7.version:
        return SCORE_V7
    if version == SCORE_V8.version:
        return SCORE_V8
    raise ValueError(f"unknown score_prompt_version: {version!r}")
