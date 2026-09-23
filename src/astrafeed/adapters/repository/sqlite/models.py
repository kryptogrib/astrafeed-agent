"""Fresh-schema SQLAlchemy models for source ingestion and the spend ceiling."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, TypeDecorator, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class UtcDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Base(DeclarativeBase):
    pass


class SourceRow(Base):
    __tablename__ = "source"
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(unique=True)


class RawItemRow(Base):
    __tablename__ = "raw_item"
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_raw_item_source_ext"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source.id"), index=True)
    external_id: Mapped[str]
    timestamp: Mapped[datetime] = mapped_column(UtcDateTime(), index=True)
    payload: Mapped[str]


class SourceIngestionStateRow(Base):
    __tablename__ = "source_ingestion_state"
    source_id: Mapped[int] = mapped_column(ForeignKey("source.id"), primary_key=True)
    last_seen: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)


class SourceCoverageRow(Base):
    __tablename__ = "source_coverage"
    __table_args__ = (
        UniqueConstraint("source_id", "start", "end", name="uq_source_coverage_window"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source.id"), index=True)
    start: Mapped[datetime] = mapped_column(UtcDateTime())
    end: Mapped[datetime] = mapped_column(UtcDateTime())
    complete: Mapped[bool]


class SpendReservationRow(Base):
    __tablename__ = "spend_reservation"
    __table_args__ = (Index("ix_spend_reservation_principal_day", "principal_id", "day"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    principal_id: Mapped[int]
    day: Mapped[str] = mapped_column(String)
    amount_micros: Mapped[int]
    settled: Mapped[bool] = mapped_column(default=False)


class CommentRow(Base):
    __tablename__ = "comment"
    comment_key: Mapped[str] = mapped_column(String, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source.id"), index=True)
    post_id: Mapped[str]
    comment_id: Mapped[str]
    parent_comment_id: Mapped[str | None] = mapped_column(default=None)
    ts: Mapped[datetime] = mapped_column(UtcDateTime(), index=True)
    edited_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), default=None)
    text: Mapped[str]
    link: Mapped[str]
    author_key: Mapped[str | None] = mapped_column(default=None)
    has_media: Mapped[bool] = mapped_column(default=False)
    # Flipped by the classifier; a re-fetched comment whose text changed is reset.
    classified: Mapped[bool] = mapped_column(default=False, index=True)


class ThreadStateRow(Base):
    __tablename__ = "thread_state"
    source_id: Mapped[int] = mapped_column(ForeignKey("source.id"), primary_key=True)
    post_id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str]
    reply_counter: Mapped[int | None] = mapped_column(default=None)
    comments_stored: Mapped[int] = mapped_column(default=0)
    possibly_truncated: Mapped[bool] = mapped_column(default=False)
    context_incomplete: Mapped[bool] = mapped_column(default=False)
    reason: Mapped[str] = mapped_column(default="")
    last_scan_at: Mapped[datetime] = mapped_column(UtcDateTime())
