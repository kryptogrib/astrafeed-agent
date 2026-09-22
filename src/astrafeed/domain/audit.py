from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

type JSON = None | bool | int | float | str | list[JSON] | dict[str, JSON]

AUDIT_EVENT_VERSION = 1


class AuditEventKind(str, Enum):
    EXECUTION_STARTED = "execution_started"
    EXECUTION_FINISHED = "execution_finished"
    STAGE_STARTED = "stage_started"
    STAGE_FINISHED = "stage_finished"
    ATTEMPT_STARTED = "attempt_started"
    ATTEMPT_FINISHED = "attempt_finished"
    LOGICAL_RESULT = "logical_result"
    MATERIAL_SNAPSHOT = "material_snapshot"
    REPORT_MEMBERSHIP = "report_membership"
    DISCUSSION_SNAPSHOT = "discussion_snapshot"
    RESEARCH_REUSE = "research_reuse"


class PayloadState(str, Enum):
    CAPTURED = "captured"
    REDACTED = "redacted"
    OMITTED_SIZE = "omitted_size"
    OMITTED_BUDGET = "omitted_budget"
    DISABLED = "disabled"
    EXPIRED = "expired"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class AuditContext:
    execution_id: str
    user_id: int
    stage_id: str
    logical_call_id: str | None = None


@dataclass(frozen=True)
class AuditEvent:
    id: str
    context: AuditContext
    kind: AuditEventKind
    occurred_at: datetime
    data: Mapping[str, JSON]
    version: int = field(default=AUDIT_EVENT_VERSION, init=False)


@dataclass(frozen=True)
class PayloadDescriptor:
    id: str
    state: PayloadState
    original_bytes: int
    stored_bytes: int
    sha256: str
    reason: str
    created_at: datetime
    expires_at: datetime
